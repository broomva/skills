#!/usr/bin/env python3
"""
ltx-server.py — FastAPI server for LTX-2.3 video generation on a GPU machine.

Accepts HTTP requests to generate videos, manages a single-GPU job queue,
and serves completed videos for download.

Usage:
    uvicorn ltx-server:app --host 0.0.0.0 --port 8420
    # or
    python ltx-server.py --host 0.0.0.0 --port 8420

Environment variables:
    LTX_REPO_DIR    — Path to cloned LTX-2 repo (default: ./LTX-2)
    LTX_OUTPUT_DIR  — Where to store generated videos (default: ./output)
    LTX_MODELS_DIR  — Where models are stored (default: ./models)
    LTX_DEFAULT_CONFIG — Default YAML config (default: distilled 2-stage)
"""

from __future__ import annotations

import asyncio
import base64
import enum
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LTX_REPO_DIR = Path(os.environ.get("LTX_REPO_DIR", "./LTX-2")).resolve()
LTX_OUTPUT_DIR = Path(os.environ.get("LTX_OUTPUT_DIR", "./output")).resolve()
LTX_MODELS_DIR = Path(os.environ.get("LTX_MODELS_DIR", "./models")).resolve()
LTX_DEFAULT_CONFIG = os.environ.get(
    "LTX_DEFAULT_CONFIG",
    "configs/ltx-2.3-22b-distilled-2stage.yaml",
)

LTX_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ltx-server")

# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    prompt: str
    height: int
    width: int
    num_frames: int
    config: str
    quantization: str
    conditioning_image_path: Optional[str]
    enhance_prompt: bool
    seed: Optional[int]
    status: JobStatus = JobStatus.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    progress: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "height": self.height,
            "width": self.width,
            "num_frames": self.num_frames,
            "config": self.config,
            "quantization": self.quantization,
            "enhance_prompt": self.enhance_prompt,
            "seed": self.seed,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_path": self.output_path,
            "error": self.error,
            "progress": self.progress,
        }


# ---------------------------------------------------------------------------
# Job store and queue
# ---------------------------------------------------------------------------

jobs: dict[str, Job] = {}
job_queue: asyncio.Queue[str] = asyncio.Queue()
current_job_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt describing the video to generate")
    height: int = Field(704, description="Video height in pixels (must be divisible by 32)")
    width: int = Field(1216, description="Video width in pixels (must be divisible by 32)")
    num_frames: int = Field(97, description="Number of frames (must be 8n+1, e.g. 33, 65, 97)")
    config: Optional[str] = Field(None, description="YAML config path relative to LTX-2 repo")
    quantization: str = Field("fp8-cast", description="Quantization mode (fp8-cast, fp8-scaled-mm, none)")
    conditioning_image: Optional[str] = Field(None, description="Base64-encoded conditioning image for image-to-video")
    enhance_prompt: bool = Field(True, description="Auto-enhance prompt with Gemma 3")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# GPU info helper
# ---------------------------------------------------------------------------


def get_gpu_info() -> dict:
    """Query nvidia-smi for GPU status."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()}

        gpus = []
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_used_mb": int(parts[2]),
                    "memory_free_mb": int(parts[3]),
                    "utilization_pct": int(parts[4]),
                    "temperature_c": int(parts[5]),
                })
        return {"gpus": gpus}
    except FileNotFoundError:
        return {"error": "nvidia-smi not found — is this a GPU machine?"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Video generation worker
# ---------------------------------------------------------------------------


async def run_generation(job: Job) -> None:
    """Execute LTX-2 inference as a subprocess."""
    global current_job_id
    current_job_id = job.id
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc).isoformat()
    job.progress = "Starting generation..."

    output_filename = f"{job.id}.mp4"
    output_path = LTX_OUTPUT_DIR / output_filename

    # Build the command as a list (no shell interpretation)
    cmd = [
        sys.executable, "-m", "ltx_pipelines.run",
        "--config", job.config,
        "--prompt", job.prompt,
        "--height", str(job.height),
        "--width", str(job.width),
        "--num_frames", str(job.num_frames),
        "--output", str(output_path),
    ]

    if job.quantization and job.quantization != "none":
        cmd.extend(["--quantization", job.quantization])

    if job.conditioning_image_path:
        cmd.extend(["--conditioning_image", job.conditioning_image_path])

    if job.enhance_prompt:
        cmd.extend(["--enhance_prompt"])

    if job.seed is not None:
        cmd.extend(["--seed", str(job.seed)])

    logger.info("[%s] Running: %s", job.id, " ".join(cmd))
    job.progress = "Model loading and inference in progress..."

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(LTX_REPO_DIR),
        )

        output_lines: list[str] = []
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                output_lines.append(decoded)
                # Update progress with last meaningful line
                if any(kw in decoded.lower() for kw in ["step", "progress", "loading", "sampling", "%"]):
                    job.progress = decoded[-200:]  # Keep last 200 chars
                logger.info("[%s] %s", job.id, decoded)

        await process.wait()

        if process.returncode == 0 and output_path.exists():
            job.status = JobStatus.COMPLETED
            job.output_path = str(output_path)
            job.progress = "Generation complete"
            logger.info("[%s] Completed: %s", job.id, output_path)
        else:
            job.status = JobStatus.FAILED
            job.error = "\n".join(output_lines[-20:]) if output_lines else "Process exited with no output"
            job.progress = "Generation failed"
            logger.error("[%s] Failed (exit code %s)", job.id, process.returncode)

    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.progress = "Generation failed with exception"
        logger.exception("[%s] Exception during generation", job.id)

    finally:
        job.completed_at = datetime.now(timezone.utc).isoformat()
        current_job_id = None

        # Clean up temporary conditioning image
        if job.conditioning_image_path and job.conditioning_image_path.startswith(tempfile.gettempdir()):
            try:
                os.unlink(job.conditioning_image_path)
            except OSError:
                pass


async def queue_worker() -> None:
    """Background worker that processes jobs one at a time."""
    logger.info("Job queue worker started")
    while True:
        job_id = await job_queue.get()
        job = jobs.get(job_id)
        if job and job.status == JobStatus.QUEUED:
            await run_generation(job)
        job_queue.task_done()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LTX-2.3 Video Generation Server",
    description="GPU-backed video generation server using LTX-2.3 (Lightricks)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(queue_worker())
    logger.info("LTX Server started")
    logger.info("  Repo dir:    %s", LTX_REPO_DIR)
    logger.info("  Output dir:  %s", LTX_OUTPUT_DIR)
    logger.info("  Models dir:  %s", LTX_MODELS_DIR)
    logger.info("  Default cfg: %s", LTX_DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    """Submit a video generation job. Returns immediately with a job ID."""

    # Validate resolution
    if req.height % 32 != 0:
        raise HTTPException(400, f"height must be divisible by 32 (got {req.height})")
    if req.width % 32 != 0:
        raise HTTPException(400, f"width must be divisible by 32 (got {req.width})")
    if (req.num_frames - 1) % 8 != 0:
        raise HTTPException(400, f"num_frames must be 8n+1 (got {req.num_frames}). Try: 33, 65, 97, 129, 257")

    # Handle conditioning image
    conditioning_image_path = None
    if req.conditioning_image:
        try:
            img_data = base64.b64decode(req.conditioning_image)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(img_data)
            tmp.close()
            conditioning_image_path = tmp.name
        except Exception as e:
            raise HTTPException(400, f"Invalid base64 conditioning_image: {e}")

    # Determine config
    config = req.config or LTX_DEFAULT_CONFIG

    # Create job
    job_id = str(uuid.uuid4())[:12]
    job = Job(
        id=job_id,
        prompt=req.prompt,
        height=req.height,
        width=req.width,
        num_frames=req.num_frames,
        config=config,
        quantization=req.quantization,
        conditioning_image_path=conditioning_image_path,
        enhance_prompt=req.enhance_prompt,
        seed=req.seed,
    )
    jobs[job_id] = job
    await job_queue.put(job_id)

    queue_size = job_queue.qsize()
    message = f"Job queued (position {queue_size} in queue)" if queue_size > 0 else "Job queued, starting now"

    logger.info("[%s] Created: prompt=%s...", job_id, req.prompt[:80])
    return GenerateResponse(job_id=job_id, status="queued", message=message)


@app.get("/status")
async def status() -> JSONResponse:
    """Server status, GPU info, and current job overview."""
    gpu_info = get_gpu_info()

    active_jobs = sum(1 for j in jobs.values() if j.status == JobStatus.RUNNING)
    queued_jobs = sum(1 for j in jobs.values() if j.status == JobStatus.QUEUED)
    completed_jobs = sum(1 for j in jobs.values() if j.status == JobStatus.COMPLETED)
    failed_jobs = sum(1 for j in jobs.values() if j.status == JobStatus.FAILED)

    return JSONResponse({
        "status": "running",
        "gpu": gpu_info,
        "current_job": current_job_id,
        "jobs": {
            "active": active_jobs,
            "queued": queued_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
            "total": len(jobs),
        },
        "config": {
            "repo_dir": str(LTX_REPO_DIR),
            "output_dir": str(LTX_OUTPUT_DIR),
            "models_dir": str(LTX_MODELS_DIR),
            "default_config": LTX_DEFAULT_CONFIG,
        },
    })


@app.get("/jobs")
async def list_jobs(
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> JSONResponse:
    """List all jobs, optionally filtered by status."""
    result = []
    for job in sorted(jobs.values(), key=lambda j: j.created_at, reverse=True):
        if status_filter and job.status.value != status_filter:
            continue
        result.append(job.to_dict())
        if len(result) >= limit:
            break
    return JSONResponse({"jobs": result, "total": len(jobs)})


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    """Get the status and details of a specific job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return JSONResponse(job.to_dict())


@app.get("/jobs/{job_id}/download")
async def download_job(job_id: str) -> FileResponse:
    """Download the completed video for a job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(400, f"Job {job_id} is {job.status.value}, not completed")
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(500, f"Output file missing for job {job_id}")

    return FileResponse(
        path=job.output_path,
        media_type="video/mp4",
        filename=f"ltx-{job_id}.mp4",
    )


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> JSONResponse:
    """Delete a job and its output file."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job.status == JobStatus.RUNNING:
        raise HTTPException(400, "Cannot delete a running job")

    # Remove output file
    if job.output_path and Path(job.output_path).exists():
        try:
            os.unlink(job.output_path)
        except OSError:
            pass

    del jobs[job_id]
    return JSONResponse({"message": f"Job {job_id} deleted"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="LTX-2.3 Video Generation Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8420, help="Port (default: 8420)")
    parser.add_argument("--repo-dir", default=None, help="Path to LTX-2 repo")
    parser.add_argument("--output-dir", default=None, help="Output directory for videos")
    parser.add_argument("--models-dir", default=None, help="Models directory")
    args = parser.parse_args()

    if args.repo_dir:
        LTX_REPO_DIR = Path(args.repo_dir).resolve()
    if args.output_dir:
        LTX_OUTPUT_DIR = Path(args.output_dir).resolve()
        LTX_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.models_dir:
        LTX_MODELS_DIR = Path(args.models_dir).resolve()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
