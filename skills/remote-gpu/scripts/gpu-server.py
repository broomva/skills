#!/usr/bin/env python3
"""gpu-server.py — Lightweight job server for a headless GPU machine.

Run on the NUC/GPU server:
    pip install fastapi uvicorn psutil
    python gpu-server.py --port 8420 --workdir ~/gpu-jobs

Accepts job submissions via HTTP, manages a single-GPU queue, and serves results.
"""

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gpu-server")

# --- Models ---

class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class SubmitRequest(BaseModel):
    command: str
    name: Optional[str] = None
    workdir: Optional[str] = None
    timeout: int = 3600
    gpu_id: int = 0


@dataclass
class Job:
    id: str
    command: str
    name: str
    workdir: str
    timeout: int
    gpu_id: int
    status: JobStatus = JobStatus.queued
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    exit_code: Optional[int] = None
    process: Optional[asyncio.subprocess.Process] = None
    log_path: Optional[Path] = None


# --- Server ---

app = FastAPI(title="GPU Remote Server", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

JOBS: dict[str, Job] = {}
JOB_QUEUE: asyncio.Queue = asyncio.Queue()
WORKDIR: Path = Path.home() / "gpu-jobs"


def _gpu_info() -> dict:
    """Get GPU info via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            return {
                "name": parts[0],
                "memory_used_mb": int(parts[1]),
                "memory_total_mb": int(parts[2]),
                "utilization_pct": int(parts[3]),
                "temperature_c": int(parts[4]),
            }
    except Exception:
        pass
    return {"error": "nvidia-smi unavailable"}


def _disk_info() -> dict:
    total, used, free = shutil.disk_usage(WORKDIR)
    return {"total_gb": round(total / 1e9, 1), "used_gb": round(used / 1e9, 1), "free_gb": round(free / 1e9, 1)}


async def _run_job(job: Job):
    """Execute a job as a subprocess."""
    job.status = JobStatus.running
    job.started_at = time.time()

    job_dir = WORKDIR / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    job.log_path = job_dir

    stdout_log = open(job_dir / "stdout.log", "w")
    stderr_log = open(job_dir / "stderr.log", "w")

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(job.gpu_id)

    try:
        job.process = await asyncio.create_subprocess_shell(
            job.command,
            stdout=stdout_log,
            stderr=stderr_log,
            cwd=job.workdir if os.path.isdir(job.workdir) else str(WORKDIR),
            env=env,
        )

        try:
            job.exit_code = await asyncio.wait_for(job.process.wait(), timeout=job.timeout)
            job.status = JobStatus.completed if job.exit_code == 0 else JobStatus.failed
        except asyncio.TimeoutError:
            job.process.terminate()
            job.exit_code = -1
            job.status = JobStatus.failed
            log.warning(f"Job {job.id} timed out after {job.timeout}s")
    except Exception as e:
        job.status = JobStatus.failed
        job.exit_code = -1
        stderr_log.write(f"\nServer error: {e}\n")
        log.error(f"Job {job.id} failed: {e}")
    finally:
        stdout_log.close()
        stderr_log.close()
        job.finished_at = time.time()
        job.process = None
        log.info(f"Job {job.id} finished: {job.status.value} (exit={job.exit_code})")


async def _worker():
    """Process jobs from the queue one at a time."""
    while True:
        job_id = await JOB_QUEUE.get()
        job = JOBS.get(job_id)
        if job and job.status == JobStatus.queued:
            await _run_job(job)
        JOB_QUEUE.task_done()


@app.on_event("startup")
async def startup():
    WORKDIR.mkdir(parents=True, exist_ok=True)
    asyncio.create_task(_worker())
    log.info(f"GPU server started. Workdir: {WORKDIR}")


# --- Endpoints ---

@app.get("/status")
async def status():
    return {
        "gpu": _gpu_info(),
        "disk": _disk_info(),
        "active_jobs": sum(1 for j in JOBS.values() if j.status == JobStatus.running),
        "queued_jobs": sum(1 for j in JOBS.values() if j.status == JobStatus.queued),
        "total_jobs": len(JOBS),
    }


@app.post("/submit")
async def submit(req: SubmitRequest):
    job_id = f"{req.name or 'job'}-{uuid.uuid4().hex[:8]}"
    job = Job(
        id=job_id,
        command=req.command,
        name=req.name or job_id,
        workdir=req.workdir or str(WORKDIR),
        timeout=req.timeout,
        gpu_id=req.gpu_id,
    )
    JOBS[job_id] = job
    await JOB_QUEUE.put(job_id)
    log.info(f"Job submitted: {job_id} — {req.command[:80]}")
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs")
async def list_jobs():
    return [
        {
            "id": j.id, "name": j.name, "status": j.status.value,
            "created_at": j.created_at, "started_at": j.started_at,
            "finished_at": j.finished_at, "exit_code": j.exit_code,
        }
        for j in sorted(JOBS.values(), key=lambda x: x.created_at, reverse=True)
    ]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": job.id, "name": job.name, "command": job.command,
        "status": job.status.value, "workdir": job.workdir,
        "created_at": job.created_at, "started_at": job.started_at,
        "finished_at": job.finished_at, "exit_code": job.exit_code,
    }


@app.get("/jobs/{job_id}/logs")
async def get_logs(job_id: str, stream: str = "stdout"):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    log_file = WORKDIR / job_id / f"{stream}.log"
    if not log_file.exists():
        return {"logs": "", "status": job.status.value}

    return {"logs": log_file.read_text(), "status": job.status.value}


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.process and job.status == JobStatus.running:
        job.process.terminate()
        job.status = JobStatus.cancelled
        job.finished_at = time.time()
        return {"status": "cancelled"}

    if job.status == JobStatus.queued:
        job.status = JobStatus.cancelled
        return {"status": "cancelled"}

    return {"status": job.status.value, "message": "Job not running"}


@app.get("/jobs/{job_id}/files")
async def list_files(job_id: str):
    job_dir = WORKDIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Job directory not found")

    files = []
    for f in job_dir.iterdir():
        if f.is_file():
            files.append({"name": f.name, "size_bytes": f.stat().st_size})
    return files


@app.get("/jobs/{job_id}/files/{filename}")
async def download_file(job_id: str, filename: str):
    file_path = WORKDIR / job_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(file_path, filename=filename)


# --- Main ---

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="GPU Remote Server")
    parser.add_argument("--port", type=int, default=8420, help="Server port (default: 8420)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--workdir", default=str(Path.home() / "gpu-jobs"), help="Job working directory")
    args = parser.parse_args()

    WORKDIR = Path(args.workdir)
    WORKDIR.mkdir(parents=True, exist_ok=True)

    uvicorn.run(app, host=args.host, port=args.port)
