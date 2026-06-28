#!/usr/bin/env python3
"""
ltx-client.py — CLI client for the LTX-2.3 video generation server.

Connects to a remote ltx-server instance to submit video generation jobs,
monitor progress, and download completed videos.

Usage:
    python ltx-client.py status
    python ltx-client.py generate --prompt "A cat in space" --wait
    python ltx-client.py jobs
    python ltx-client.py job <job_id>
    python ltx-client.py download <job_id> -o video.mp4

Dependencies: httpx (pip install httpx)

Environment variables:
    LTX_SERVER_URL — Server base URL (default: http://localhost:8420)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)

DEFAULT_SERVER = "http://localhost:8420"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_client(args: argparse.Namespace) -> httpx.Client:
    """Create an httpx client with the configured server URL."""
    base_url = getattr(args, "server", None) or DEFAULT_SERVER
    return httpx.Client(base_url=base_url, timeout=30.0)


def print_json(data: dict, indent: int = 2) -> None:
    """Pretty-print JSON data."""
    print(json.dumps(data, indent=indent))


def format_duration(start: str, end: str | None) -> str:
    """Format duration between two ISO timestamps."""
    if not end:
        return "in progress"
    from datetime import datetime, timezone
    t0 = datetime.fromisoformat(start)
    t1 = datetime.fromisoformat(end)
    delta = t1 - t0
    total_secs = int(delta.total_seconds())
    mins, secs = divmod(total_secs, 60)
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def print_job_summary(job: dict) -> None:
    """Print a concise job summary."""
    status_icons = {
        "queued": "[QUEUED]",
        "running": "[RUNNING]",
        "completed": "[DONE]",
        "failed": "[FAILED]",
    }
    icon = status_icons.get(job["status"], "[?]")
    prompt_short = job["prompt"][:60] + ("..." if len(job["prompt"]) > 60 else "")
    duration = ""
    if job.get("started_at"):
        duration = f" ({format_duration(job['started_at'], job.get('completed_at'))})"

    print(f"  {icon} {job['id']}  {job['width']}x{job['height']} {job['num_frames']}f  {prompt_short}{duration}")
    if job.get("progress") and job["status"] == "running":
        print(f"         Progress: {job['progress']}")
    if job.get("error"):
        error_short = job["error"].split("\n")[-1][:100]
        print(f"         Error: {error_short}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> None:
    """Show server status and GPU info."""
    with get_client(args) as client:
        try:
            resp = client.get("/status")
            resp.raise_for_status()
        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to server at {args.server}")
            print("       Is the server running? Start with: python ltx-server.py")
            sys.exit(1)

        data = resp.json()

    print("=== LTX-2.3 Server Status ===")
    print(f"Status: {data['status']}")
    print()

    # GPU info
    gpu = data.get("gpu", {})
    if "error" in gpu:
        print(f"GPU: {gpu['error']}")
    elif "gpus" in gpu:
        for i, g in enumerate(gpu["gpus"]):
            print(f"GPU {i}: {g['name']}")
            print(f"  Memory: {g['memory_used_mb']} / {g['memory_total_mb']} MB ({g['memory_free_mb']} MB free)")
            print(f"  Utilization: {g['utilization_pct']}%  |  Temperature: {g['temperature_c']}C")
    print()

    # Job counts
    j = data.get("jobs", {})
    print(f"Jobs: {j.get('active', 0)} active, {j.get('queued', 0)} queued, "
          f"{j.get('completed', 0)} completed, {j.get('failed', 0)} failed")

    if data.get("current_job"):
        print(f"Current job: {data['current_job']}")
    print()

    # Config
    cfg = data.get("config", {})
    print(f"Config: {cfg.get('default_config', '?')}")
    print(f"Output: {cfg.get('output_dir', '?')}")


def cmd_generate(args: argparse.Namespace) -> None:
    """Submit a video generation job."""
    payload = {
        "prompt": args.prompt,
        "height": args.height,
        "width": args.width,
        "num_frames": args.num_frames,
        "quantization": args.quantization,
        "enhance_prompt": not args.no_enhance,
    }

    if args.config:
        payload["config"] = args.config

    if args.seed is not None:
        payload["seed"] = args.seed

    # Handle conditioning image
    if args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"ERROR: Image not found: {args.image}")
            sys.exit(1)
        img_data = image_path.read_bytes()
        payload["conditioning_image"] = base64.b64encode(img_data).decode("ascii")
        print(f"Attached conditioning image: {args.image} ({len(img_data)} bytes)")

    with get_client(args) as client:
        try:
            resp = client.post("/generate", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to server at {args.server}")
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            print(f"ERROR: {e.response.json().get('detail', e.response.text)}")
            sys.exit(1)

        data = resp.json()

    job_id = data["job_id"]
    print(f"Job submitted: {job_id}")
    print(f"  Status: {data['status']}")
    print(f"  {data['message']}")
    print(f"  Prompt: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  Resolution: {args.width}x{args.height}, {args.num_frames} frames")
    print()

    if args.wait:
        print("Waiting for completion (polling every 5s)...")
        _poll_until_done(args, job_id)


def _poll_until_done(args: argparse.Namespace, job_id: str) -> None:
    """Poll job status until it completes or fails."""
    last_progress = ""
    with get_client(args) as client:
        while True:
            try:
                resp = client.get(f"/jobs/{job_id}")
                resp.raise_for_status()
                job = resp.json()
            except httpx.ConnectError:
                print("  Connection lost, retrying...")
                time.sleep(5)
                continue

            status = job["status"]
            progress = job.get("progress", "")

            # Show progress updates
            if progress and progress != last_progress:
                print(f"  [{status.upper()}] {progress}")
                last_progress = progress

            if status == "completed":
                print()
                print(f"Video ready! Download with:")
                print(f"  python ltx-client.py download {job_id}")
                print(f"  # or")
                print(f"  curl -o ltx-{job_id}.mp4 {args.server}/jobs/{job_id}/download")

                # Auto-download if output specified
                if args.output:
                    print()
                    _do_download(client, job_id, args.output)
                return

            if status == "failed":
                print()
                print(f"Job failed!")
                if job.get("error"):
                    print(f"Error: {job['error'][-500:]}")
                sys.exit(1)

            time.sleep(5)


def _do_download(client: httpx.Client, job_id: str, output_path: str) -> None:
    """Download a video from the server."""
    print(f"Downloading to {output_path}...")
    with client.stream("GET", f"/jobs/{job_id}/download") as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(output_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = (downloaded / total) * 100
                    mb = downloaded / (1024 * 1024)
                    print(f"\r  {mb:.1f} MB ({pct:.0f}%)", end="", flush=True)
    print()
    print(f"Saved: {output_path}")


def cmd_jobs(args: argparse.Namespace) -> None:
    """List all jobs on the server."""
    with get_client(args) as client:
        try:
            params = {}
            if args.filter:
                params["status_filter"] = args.filter
            resp = client.get("/jobs", params=params)
            resp.raise_for_status()
        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to server at {args.server}")
            sys.exit(1)

        data = resp.json()

    job_list = data.get("jobs", [])
    total = data.get("total", 0)

    if not job_list:
        print("No jobs found.")
        return

    print(f"=== Jobs ({len(job_list)}/{total}) ===")
    for job in job_list:
        print_job_summary(job)


def cmd_job(args: argparse.Namespace) -> None:
    """Show details for a specific job."""
    with get_client(args) as client:
        try:
            resp = client.get(f"/jobs/{args.job_id}")
            resp.raise_for_status()
        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to server at {args.server}")
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print(f"Job {args.job_id} not found")
                sys.exit(1)
            raise

        data = resp.json()

    if args.json:
        print_json(data)
    else:
        print(f"=== Job {data['id']} ===")
        print(f"  Status:   {data['status']}")
        print(f"  Prompt:   {data['prompt']}")
        print(f"  Size:     {data['width']}x{data['height']}")
        print(f"  Frames:   {data['num_frames']}")
        print(f"  Config:   {data['config']}")
        print(f"  Quant:    {data['quantization']}")
        print(f"  Enhance:  {data['enhance_prompt']}")
        if data.get("seed") is not None:
            print(f"  Seed:     {data['seed']}")
        print(f"  Created:  {data['created_at']}")
        if data.get("started_at"):
            print(f"  Started:  {data['started_at']}")
        if data.get("completed_at"):
            duration = format_duration(data["started_at"], data["completed_at"])
            print(f"  Finished: {data['completed_at']} ({duration})")
        if data.get("progress"):
            print(f"  Progress: {data['progress']}")
        if data.get("error"):
            print(f"  Error:    {data['error'][-300:]}")


def cmd_download(args: argparse.Namespace) -> None:
    """Download a completed video."""
    output = args.output or f"ltx-{args.job_id}.mp4"
    with get_client(args) as client:
        try:
            # Check job status first
            resp = client.get(f"/jobs/{args.job_id}")
            resp.raise_for_status()
            job = resp.json()

            if job["status"] != "completed":
                print(f"Job {args.job_id} is {job['status']}, not completed yet.")
                if job["status"] == "running":
                    print("Use --wait with generate, or poll with: python ltx-client.py job <id>")
                sys.exit(1)

            _do_download(client, args.job_id, output)

        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to server at {args.server}")
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            detail = e.response.json().get("detail", e.response.text) if e.response.headers.get("content-type", "").startswith("application/json") else e.response.text
            print(f"ERROR: {detail}")
            sys.exit(1)


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a job and its output."""
    with get_client(args) as client:
        try:
            resp = client.delete(f"/jobs/{args.job_id}")
            resp.raise_for_status()
            data = resp.json()
            print(data.get("message", "Deleted"))
        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to server at {args.server}")
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            detail = e.response.json().get("detail", e.response.text) if e.response.headers.get("content-type", "").startswith("application/json") else e.response.text
            print(f"ERROR: {detail}")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import os
    default_server = os.environ.get("LTX_SERVER_URL", DEFAULT_SERVER)

    parser = argparse.ArgumentParser(
        description="CLI client for the LTX-2.3 video generation server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s status                                    Check server & GPU status
  %(prog)s generate -p "A cat floating in space"     Submit generation job
  %(prog)s generate -p "Motion..." --wait -o out.mp4 Submit, wait, and download
  %(prog)s jobs                                      List all jobs
  %(prog)s job abc123def456                          Check specific job
  %(prog)s download abc123def456 -o video.mp4        Download completed video
  %(prog)s delete abc123def456                       Delete job and video
""",
    )
    parser.add_argument(
        "-s", "--server",
        default=default_server,
        help=f"Server URL (default: {default_server}, env: LTX_SERVER_URL)",
    )

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # --- status ---
    sub.add_parser("status", help="Show server status and GPU info")

    # --- generate ---
    gen = sub.add_parser("generate", help="Submit a video generation job")
    gen.add_argument("-p", "--prompt", required=True, help="Text prompt for video generation")
    gen.add_argument("--height", type=int, default=704, help="Video height (default: 704, must be divisible by 32)")
    gen.add_argument("--width", type=int, default=1216, help="Video width (default: 1216, must be divisible by 32)")
    gen.add_argument("--num-frames", type=int, default=97, help="Frame count (default: 97, must be 8n+1)")
    gen.add_argument("--config", default=None, help="Config YAML path (default: distilled 2-stage)")
    gen.add_argument("--quantization", default="fp8-cast", help="Quantization: fp8-cast, fp8-scaled-mm, none (default: fp8-cast)")
    gen.add_argument("--image", default=None, help="Path to conditioning image for image-to-video")
    gen.add_argument("--no-enhance", action="store_true", help="Disable automatic prompt enhancement")
    gen.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    gen.add_argument("--wait", action="store_true", help="Wait for job to complete (polls every 5s)")
    gen.add_argument("-o", "--output", default=None, help="Download output to this path when done (requires --wait)")

    # --- jobs ---
    jobs_cmd = sub.add_parser("jobs", help="List all jobs")
    jobs_cmd.add_argument("-f", "--filter", choices=["queued", "running", "completed", "failed"], help="Filter by status")

    # --- job ---
    job_cmd = sub.add_parser("job", help="Show details for a specific job")
    job_cmd.add_argument("job_id", help="Job ID to inspect")
    job_cmd.add_argument("--json", action="store_true", help="Output raw JSON")

    # --- download ---
    dl = sub.add_parser("download", help="Download a completed video")
    dl.add_argument("job_id", help="Job ID to download")
    dl.add_argument("-o", "--output", default=None, help="Output file path (default: ltx-<job_id>.mp4)")

    # --- delete ---
    rm = sub.add_parser("delete", help="Delete a job and its output file")
    rm.add_argument("job_id", help="Job ID to delete")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "status": cmd_status,
        "generate": cmd_generate,
        "jobs": cmd_jobs,
        "job": cmd_job,
        "download": cmd_download,
        "delete": cmd_delete,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
