#!/usr/bin/env bash
# setup-nuc.sh — Bootstrap a headless GPU server (NUC or similar) from Mac
# Usage: bash setup-nuc.sh SSH_HOST [--with-ltx] [--with-claude] [--with-autoany]
set -euo pipefail

SSH_HOST="${1:?Usage: setup-nuc.sh SSH_HOST [--with-ltx] [--with-claude] [--with-autoany]}"
shift

INSTALL_LTX=false
INSTALL_CLAUDE=false
INSTALL_AUTOANY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --with-ltx) INSTALL_LTX=true; shift ;;
    --with-claude) INSTALL_CLAUDE=true; shift ;;
    --with-autoany) INSTALL_AUTOANY=true; shift ;;
    --all) INSTALL_LTX=true; INSTALL_CLAUDE=true; INSTALL_AUTOANY=true; shift ;;
    --help)
      echo "Usage: setup-nuc.sh SSH_HOST [--with-ltx] [--with-claude] [--with-autoany] [--all]"
      echo ""
      echo "Bootstraps a headless GPU server with:"
      echo "  Base: gpu-server.py, Python deps, nvidia drivers check"
      echo "  --with-ltx     Install LTX-2 video generation"
      echo "  --with-claude   Install Claude Code CLI"
      echo "  --with-autoany  Install autoany + Rust toolchain"
      echo "  --all          Install everything"
      exit 0 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

log() { echo "[setup-nuc] $*"; }

# --- Preflight ---
log "Testing SSH connection to $SSH_HOST..."
ssh -o ConnectTimeout=10 "$SSH_HOST" "echo 'SSH OK'" || { log "ERROR: Cannot SSH to $SSH_HOST"; exit 1; }

log "Checking GPU..."
ssh "$SSH_HOST" "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" || { log "WARNING: nvidia-smi failed — GPU drivers may not be installed"; }

# --- Base Setup ---
log "=== Installing base dependencies ==="
ssh "$SSH_HOST" << 'REMOTE'
set -euo pipefail

# Ensure Python 3.12+
if ! python3 -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
  echo "Installing Python 3.12..."
  sudo apt-get update -qq && sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip 2>/dev/null || {
    echo "WARNING: Could not install Python 3.12 via apt. Please install manually."
  }
fi

# Install uv
if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Install server deps
pip install --quiet fastapi uvicorn psutil httpx 2>/dev/null || \
  pip3 install --quiet fastapi uvicorn psutil httpx

# Create workdir
mkdir -p ~/gpu-jobs

echo "Base setup complete"
REMOTE

# --- Copy gpu-server.py ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
log "Copying gpu-server.py to $SSH_HOST..."
scp "$SCRIPT_DIR/gpu-server.py" "${SSH_HOST}:~/gpu-server.py"

# --- Create systemd service ---
log "Setting up gpu-server as systemd service..."
ssh "$SSH_HOST" << 'REMOTE'
cat > /tmp/gpu-server.service << 'SERVICE'
[Unit]
Description=GPU Remote Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=%h
ExecStart=/usr/bin/python3 %h/gpu-server.py --port 8420
Restart=always
RestartSec=5
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
SERVICE

# Replace $USER with actual username
sed -i "s/\$USER/$(whoami)/g" /tmp/gpu-server.service
sudo cp /tmp/gpu-server.service /etc/systemd/system/gpu-server.service 2>/dev/null || {
  echo "WARNING: Could not install systemd service (not running systemd or no sudo)."
  echo "Start manually: python3 ~/gpu-server.py --port 8420 &"
}
sudo systemctl daemon-reload 2>/dev/null
sudo systemctl enable gpu-server 2>/dev/null
sudo systemctl start gpu-server 2>/dev/null
echo "gpu-server service installed and started"
REMOTE

# --- Optional: LTX-2 ---
if $INSTALL_LTX; then
  log "=== Installing LTX-2 ==="
  ssh "$SSH_HOST" << 'REMOTE'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

if [ ! -d ~/LTX-2 ]; then
  git clone https://github.com/Lightricks/LTX-2.git ~/LTX-2
fi

cd ~/LTX-2
uv sync --frozen
echo "LTX-2 installed. Download models with:"
echo "  huggingface-cli download Lightricks/LTX-2.3 ltx-2.3-22b-distilled.safetensors --local-dir models/"
REMOTE
fi

# --- Optional: Claude Code ---
if $INSTALL_CLAUDE; then
  log "=== Installing Claude Code ==="
  ssh "$SSH_HOST" << 'REMOTE'
if ! command -v claude &>/dev/null; then
  npm install -g @anthropic-ai/claude-code 2>/dev/null || {
    echo "Installing Node.js first..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - 2>/dev/null
    sudo apt-get install -y nodejs 2>/dev/null
    npm install -g @anthropic-ai/claude-code
  }
fi
echo "Claude Code installed: $(claude --version 2>/dev/null || echo 'check PATH')"
REMOTE
fi

# --- Optional: Autoany + Rust ---
if $INSTALL_AUTOANY; then
  log "=== Installing Rust + Autoany ==="
  ssh "$SSH_HOST" << 'REMOTE'
set -euo pipefail

# Install Rust
if ! command -v rustup &>/dev/null; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  source "$HOME/.cargo/env"
fi

# Clone autoany if not present
if [ ! -d ~/autoany ]; then
  git clone https://github.com/broomva/autoany.git ~/autoany
fi

cd ~/autoany
cargo build --release
echo "Autoany installed"
REMOTE
fi

# --- Configure local Mac ---
log "=== Configuring local Mac ==="
mkdir -p ~/.config/gpu-remote
cat > ~/.config/gpu-remote/config.toml << EOF
[server]
host = "$SSH_HOST"
port = 8420
mode = "ssh"

[defaults]
workdir = "~/gpu-jobs"
timeout = 3600
gpu_id = 0

[sync]
exclude = [".git", "node_modules", "__pycache__", ".venv", "target"]
EOF

log ""
log "=== Setup Complete ==="
log ""
log "Usage from Mac:"
log "  source $(dirname "$SCRIPT_DIR")/scripts/gpu-remote.sh"
log "  gpu-status                          # Check GPU and jobs"
log "  gpu-submit 'python train.py'        # Submit a job"
log "  gpu-claude 'Fix tests' --workdir ~  # Remote Claude session"
log ""
log "Or use the HTTP API:"
log "  curl http://${SSH_HOST}:8420/status"
