#!/usr/bin/env bash
# gpu-remote.sh — Shell functions for orchestrating a headless GPU server
# Source this file: source gpu-remote.sh
# Requires: ssh, rsync, jq (optional for API mode)
set -euo pipefail

# --- Configuration ---
GPU_CONFIG="${HOME}/.config/gpu-remote/config.toml"
GPU_HOST="${GPU_HOST:-nuc-gpu}"
GPU_PORT="${GPU_PORT:-8420}"
GPU_MODE="${GPU_MODE:-ssh}"  # "ssh" or "api"
GPU_WORKDIR="${GPU_WORKDIR:-~/gpu-jobs}"
GPU_USER="${GPU_USER:-$(whoami)}"

# Load config if exists
if [[ -f "$GPU_CONFIG" ]]; then
  _parse_toml_value() { grep "^$1" "$GPU_CONFIG" 2>/dev/null | sed 's/.*= *"\(.*\)"/\1/' | head -1; }
  GPU_HOST="${GPU_HOST:-$(_parse_toml_value host)}"
  GPU_PORT="${GPU_PORT:-$(_parse_toml_value port)}"
  GPU_MODE="${GPU_MODE:-$(_parse_toml_value mode)}"
  GPU_WORKDIR="${GPU_WORKDIR:-$(_parse_toml_value workdir)}"
fi

# --- Helpers ---
_gpu_ssh() { ssh -o ConnectTimeout=10 "$GPU_HOST" "$@"; }

_gpu_api() {
  local method="$1" path="$2"; shift 2
  curl -s -X "$method" "http://${GPU_HOST}:${GPU_PORT}${path}" "$@"
}

_generate_job_id() { echo "job-$(date +%s)-$(head -c 4 /dev/urandom | xxd -p)"; }

_log() { echo "[gpu-remote] $*" >&2; }

# --- Core Commands ---

gpu-submit() {
  # Submit a command to run on the GPU server
  # Usage: gpu-submit "command" [--name NAME] [--workdir DIR] [--timeout SECS] [--download FILE]
  local cmd="" name="" workdir="$GPU_WORKDIR" timeout=3600 download="" gpu_id=0 branch=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --name) name="$2"; shift 2 ;;
      --workdir) workdir="$2"; shift 2 ;;
      --timeout) timeout="$2"; shift 2 ;;
      --download) download="$2"; shift 2 ;;
      --gpu) gpu_id="$2"; shift 2 ;;
      --branch) branch="$2"; shift 2 ;;
      --help)
        echo "Usage: gpu-submit COMMAND [--name NAME] [--workdir DIR] [--timeout SECS] [--download FILE] [--gpu ID] [--branch BRANCH]"
        return 0 ;;
      *) cmd="$1"; shift ;;
    esac
  done

  if [[ -z "$cmd" ]]; then echo "Error: no command provided"; return 1; fi

  local job_id
  job_id=$(_generate_job_id)
  [[ -n "$name" ]] && job_id="${name}-$(date +%s)"

  if [[ "$GPU_MODE" == "api" ]]; then
    _gpu_api POST /submit \
      -H "Content-Type: application/json" \
      -d "{\"command\":\"$cmd\",\"name\":\"${name:-$job_id}\",\"workdir\":\"$workdir\",\"timeout\":$timeout}"
    return
  fi

  # SSH mode
  local job_dir="${GPU_WORKDIR}/${job_id}"
  local branch_cmd=""
  [[ -n "$branch" ]] && branch_cmd="git checkout $branch 2>/dev/null || true; "

  _log "Submitting job: $job_id"
  _gpu_ssh "mkdir -p $job_dir && cat > ${job_dir}/run.sh" <<SCRIPT
#!/bin/bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=$gpu_id
cd $workdir
${branch_cmd}
echo \$\$ > ${job_dir}/pid
echo "running" > ${job_dir}/status
echo "\$(date -Iseconds)" > ${job_dir}/started

{
  timeout $timeout bash -c '$cmd'
  echo \$? > ${job_dir}/exitcode
  echo "completed" > ${job_dir}/status
} > ${job_dir}/stdout.log 2> ${job_dir}/stderr.log &

echo \$! > ${job_dir}/pid
disown
SCRIPT

  _gpu_ssh "chmod +x ${job_dir}/run.sh && nohup ${job_dir}/run.sh &>/dev/null &"
  _log "Job submitted: $job_id"
  echo "$job_id"

  # Auto-download on completion (background monitor)
  if [[ -n "$download" ]]; then
    (
      while true; do
        sleep 10
        status=$(_gpu_ssh "cat ${job_dir}/status 2>/dev/null" || echo "unknown")
        if [[ "$status" == "completed" ]]; then
          _log "Job $job_id completed, downloading $download"
          scp "${GPU_HOST}:${download}" "./"
          break
        elif [[ "$status" != "running" ]]; then
          break
        fi
      done
    ) &
  fi
}

gpu-status() {
  # Show GPU state and all jobs
  if [[ "$GPU_MODE" == "api" ]]; then
    _gpu_api GET /status | jq . 2>/dev/null || _gpu_api GET /status
    echo ""
    _gpu_api GET /jobs | jq . 2>/dev/null || _gpu_api GET /jobs
    return
  fi

  echo "=== GPU Status ==="
  _gpu_ssh "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader" 2>/dev/null || echo "nvidia-smi unavailable"

  echo ""
  echo "=== Jobs ==="
  _gpu_ssh "for d in ${GPU_WORKDIR}/job-* ${GPU_WORKDIR}/*-[0-9]*; do
    [ -d \"\$d\" ] || continue
    name=\$(basename \$d)
    status=\$(cat \$d/status 2>/dev/null || echo 'unknown')
    started=\$(cat \$d/started 2>/dev/null || echo 'n/a')
    printf '%-30s %-12s %s\n' \"\$name\" \"\$status\" \"\$started\"
  done" 2>/dev/null || echo "No jobs found"
}

gpu-logs() {
  # Stream logs from a job
  local job_id="${1:?Usage: gpu-logs JOB_ID}"
  local log_type="${2:-stdout}"  # stdout or stderr

  if [[ "$GPU_MODE" == "api" ]]; then
    _gpu_api GET "/jobs/${job_id}/logs"
    return
  fi

  _gpu_ssh "tail -f ${GPU_WORKDIR}/${job_id}/${log_type}.log 2>/dev/null || echo 'No logs yet'"
}

gpu-cancel() {
  # Cancel a running job
  local job_id="${1:?Usage: gpu-cancel JOB_ID}"

  if [[ "$GPU_MODE" == "api" ]]; then
    _gpu_api POST "/jobs/${job_id}/cancel"
    return
  fi

  local pid
  pid=$(_gpu_ssh "cat ${GPU_WORKDIR}/${job_id}/pid 2>/dev/null")
  if [[ -n "$pid" ]]; then
    _gpu_ssh "kill -TERM $pid 2>/dev/null; echo 'cancelled' > ${GPU_WORKDIR}/${job_id}/status"
    _log "Cancelled job $job_id (pid $pid)"
  else
    _log "No PID found for $job_id"
  fi
}

gpu-download() {
  # Download files from a job
  local job_id="${1:?Usage: gpu-download JOB_ID [FILE]}"
  local file="${2:-}"

  if [[ -n "$file" ]]; then
    scp "${GPU_HOST}:${file}" "./"
  else
    # Download all files from job directory
    local dest="./${job_id}-output"
    mkdir -p "$dest"
    scp -r "${GPU_HOST}:${GPU_WORKDIR}/${job_id}/" "$dest/"
    _log "Downloaded to $dest"
  fi
}

gpu-watch() {
  # Live GPU monitoring
  _gpu_ssh "watch -n 5 nvidia-smi" 2>/dev/null || \
    while true; do _gpu_ssh "nvidia-smi"; sleep 5; clear; done
}

gpu-claude() {
  # Start a Claude Code session on the NUC
  # Usage: gpu-claude "prompt" [--workdir DIR] [--branch BRANCH]
  local prompt="" workdir="" branch=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --workdir) workdir="$2"; shift 2 ;;
      --branch) branch="$2"; shift 2 ;;
      --help)
        echo "Usage: gpu-claude PROMPT [--workdir DIR] [--branch BRANCH]"
        return 0 ;;
      *) prompt="$1"; shift ;;
    esac
  done

  if [[ -z "$prompt" ]]; then echo "Error: no prompt provided"; return 1; fi

  local cd_cmd=""
  [[ -n "$workdir" ]] && cd_cmd="cd $workdir && "
  [[ -n "$branch" ]] && cd_cmd="${cd_cmd}git checkout $branch 2>/dev/null; "

  _log "Starting Claude Code session on $GPU_HOST"
  # Use ssh -t for interactive session
  ssh -t "$GPU_HOST" "${cd_cmd}claude --print '${prompt}'"
}

gpu-ssh() {
  # Interactive SSH to NUC
  ssh -t "$GPU_HOST" "${@:-bash}"
}

gpu-sync() {
  # Sync a directory to/from NUC
  # Usage: gpu-sync local_dir [remote_dir] [--from]
  local local_dir="${1:?Usage: gpu-sync LOCAL_DIR [REMOTE_DIR] [--from]}"
  local remote_dir="${2:-$local_dir}"
  local direction="to"

  [[ "${3:-}" == "--from" ]] && direction="from"

  local exclude_args="--exclude .git --exclude node_modules --exclude __pycache__ --exclude .venv --exclude target"

  if [[ "$direction" == "to" ]]; then
    rsync -avz --progress $exclude_args "$local_dir/" "${GPU_HOST}:${remote_dir}/"
  else
    rsync -avz --progress $exclude_args "${GPU_HOST}:${remote_dir}/" "$local_dir/"
  fi
}

gpu-tunnel() {
  # SSH tunnel a port from NUC to localhost
  local remote_port="${1:?Usage: gpu-tunnel REMOTE_PORT [LOCAL_PORT]}"
  local local_port="${2:-$remote_port}"

  _log "Tunneling ${GPU_HOST}:${remote_port} → localhost:${local_port}"
  ssh -N -L "${local_port}:localhost:${remote_port}" "$GPU_HOST"
}

# --- Initialization ---
_log "GPU remote functions loaded. Host: $GPU_HOST, Mode: $GPU_MODE"
_log "Commands: gpu-submit, gpu-status, gpu-logs, gpu-cancel, gpu-download, gpu-watch, gpu-claude, gpu-ssh, gpu-sync, gpu-tunnel"
