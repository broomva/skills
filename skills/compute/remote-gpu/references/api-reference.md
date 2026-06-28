# GPU Remote Server — API Reference

## Base URL

```
http://NUC_HOST:8420
```

## Authentication

None by default. Bind to localhost and use SSH tunnel for security:
```bash
ssh -L 8420:localhost:8420 nuc-gpu
# Then access at http://localhost:8420
```

## Endpoints

### GET /status

Server and GPU health check.

**Response:**
```json
{
  "gpu": {
    "name": "NVIDIA GeForce RTX 4090",
    "memory_used_mb": 1024,
    "memory_total_mb": 12288,
    "utilization_pct": 45,
    "temperature_c": 62
  },
  "disk": {
    "total_gb": 500.0,
    "used_gb": 120.5,
    "free_gb": 379.5
  },
  "active_jobs": 1,
  "queued_jobs": 2,
  "total_jobs": 15
}
```

### POST /submit

Submit a job for execution.

**Request:**
```json
{
  "command": "python train.py --epochs 10",
  "name": "training-v2",
  "workdir": "/home/user/project",
  "timeout": 3600,
  "gpu_id": 0
}
```

**Response:**
```json
{
  "job_id": "training-v2-a1b2c3d4",
  "status": "queued"
}
```

### GET /jobs

List all jobs, newest first.

**Response:**
```json
[
  {
    "id": "training-v2-a1b2c3d4",
    "name": "training-v2",
    "status": "running",
    "created_at": 1711500000.0,
    "started_at": 1711500001.0,
    "finished_at": null,
    "exit_code": null
  }
]
```

### GET /jobs/{job_id}

Get detailed job info.

### GET /jobs/{job_id}/logs?stream=stdout

Get job output logs. Use `stream=stderr` for error output.

**Response:**
```json
{
  "logs": "Epoch 1/10: loss=0.45\nEpoch 2/10: loss=0.32\n",
  "status": "running"
}
```

### POST /jobs/{job_id}/cancel

Cancel a running or queued job.

### GET /jobs/{job_id}/files

List output files in the job directory.

### GET /jobs/{job_id}/files/{filename}

Download a specific file from the job directory.

## Job Lifecycle

```
queued → running → completed (exit 0)
                 → failed (exit != 0 or timeout)
       → cancelled (user cancelled)
```

## Common Patterns

### Submit LTX-2 video generation
```bash
curl -X POST http://localhost:8420/submit \
  -H "Content-Type: application/json" \
  -d '{
    "command": "cd ~/LTX-2 && source .venv/bin/activate && python -m ltx_pipelines.run --config configs/ltx-2.3-22b-distilled-2stage.yaml --quantization fp8-cast --prompt \"Mountains at dawn\" --output ~/gpu-jobs/output.mp4",
    "name": "ltx-mountains",
    "timeout": 600
  }'
```

### Submit training run
```bash
curl -X POST http://localhost:8420/submit \
  -H "Content-Type: application/json" \
  -d '{
    "command": "cd ~/project && python train.py --config config.yaml",
    "name": "lora-training",
    "workdir": "/home/user/project",
    "timeout": 7200
  }'
```

### Poll until complete
```bash
JOB_ID="training-v2-a1b2c3d4"
while true; do
  STATUS=$(curl -s "http://localhost:8420/jobs/$JOB_ID" | jq -r .status)
  echo "Status: $STATUS"
  [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]] && break
  sleep 10
done
```
