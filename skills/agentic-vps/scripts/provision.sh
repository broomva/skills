#!/usr/bin/env bash
# =============================================================================
# agentic-vps — provision a fresh Ubuntu host into an autonomous-agent dev box
# =============================================================================
# Capability-preserving model: the box IS the sandbox. Full agent autonomy
# inside it, contained by isolation — NOT by restricting the agent.
#
# Idempotent. Run as root over SSH:
#   ssh root@<host> 'AGENT_USER=agent bash -s' < provision.sh
#
# Env knobs (all optional):
#   AGENT_USER=agent          # non-root user the agent runs as
#   GIT_NAME / GIT_EMAIL      # git identity for the agent user
#   MEM_MAX=7G  TASKS_MAX=8192  MEM_HIGH=6500M   # resource caps (host-survival)
#   INSTALL_RUST=1 INSTALL_BUN=1 INSTALL_DOCKER=1 INSTALL_NODE=1  # toolchain toggles
#
# Out-of-band by design (NOT done here): provider snapshot, Tailscale auth,
# CLI login, public :22 close, edge firewall. See SKILL.md phases 0/2/3.
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

AGENT_USER="${AGENT_USER:-agent}"
MEM_MAX="${MEM_MAX:-7G}"; MEM_HIGH="${MEM_HIGH:-6500M}"; TASKS_MAX="${TASKS_MAX:-8192}"
INSTALL_NODE="${INSTALL_NODE:-1}"; INSTALL_RUST="${INSTALL_RUST:-1}"
INSTALL_BUN="${INSTALL_BUN:-1}"; INSTALL_DOCKER="${INSTALL_DOCKER:-1}"
GIT_NAME="${GIT_NAME:-}"; GIT_EMAIL="${GIT_EMAIL:-}"

log(){ printf '\n\033[1;36m==== %s ====\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }

log "1. Non-root agent user '$AGENT_USER' (passwordless sudo + docker = autonomy)"
id "$AGENT_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --comment "Coding agent" "$AGENT_USER"
usermod -aG sudo "$AGENT_USER"
echo "$AGENT_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$AGENT_USER"
chmod 440 "/etc/sudoers.d/90-$AGENT_USER"
visudo -cf "/etc/sudoers.d/90-$AGENT_USER"
AGENT_HOME="$(getent passwd "$AGENT_USER" | cut -d: -f6)"
install -d -m 700 -o "$AGENT_USER" -g "$AGENT_USER" "$AGENT_HOME/.ssh"
if [ -f /root/.ssh/authorized_keys ]; then
  cp /root/.ssh/authorized_keys "$AGENT_HOME/.ssh/authorized_keys"
  chown "$AGENT_USER:$AGENT_USER" "$AGENT_HOME/.ssh/authorized_keys"
  chmod 600 "$AGENT_HOME/.ssh/authorized_keys"
fi

log "2. Base dev packages"
apt-get update -qq
apt-get install -y -qq build-essential pkg-config libssl-dev git curl wget jq unzip \
  ca-certificates gnupg ripgrep fd-find bubblewrap socat tmux htop

if [ "$INSTALL_NODE" = 1 ] && ! command -v node >/dev/null 2>&1; then
  log "3. Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -qq nodejs
fi

if ! command -v gh >/dev/null 2>&1; then
  log "4. GitHub CLI"
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list
  apt-get update -qq && apt-get install -y -qq gh
fi

if [ "$INSTALL_DOCKER" = 1 ] && ! command -v docker >/dev/null 2>&1; then
  log "5. Docker CE"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
command -v docker >/dev/null 2>&1 && { usermod -aG docker "$AGENT_USER"; systemctl enable --now docker; }

log "6. Claude Code + sandbox-runtime"
command -v claude >/dev/null 2>&1 || npm install -g @anthropic-ai/claude-code @anthropic-ai/sandbox-runtime

if [ "$INSTALL_RUST" = 1 ]; then
  log "7a. Rust (rustup) for $AGENT_USER"
  su - "$AGENT_USER" -c 'command -v cargo >/dev/null 2>&1 || { curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path; grep -q cargo/env ~/.bashrc || echo "source \$HOME/.cargo/env" >> ~/.bashrc; }'
fi
if [ "$INSTALL_BUN" = 1 ]; then
  log "7b. Bun for $AGENT_USER"
  su - "$AGENT_USER" -c '[ -x ~/.bun/bin/bun ] || curl -fsSL https://bun.sh/install | bash'
fi

log "8. Generous resource caps (host-survival, NOT throttle) + ulimits"
AGENT_UID="$(id -u "$AGENT_USER")"
# Persistent drop-in on the user slice — survives reboot AND applies even though the
# slice is a transient unit with no live session at provision time. `systemctl show`
# reads this, so the verify gate sees the caps without an active session.
mkdir -p "/etc/systemd/system/user-$AGENT_UID.slice.d"
cat >"/etc/systemd/system/user-$AGENT_UID.slice.d/50-agent-caps.conf" <<CAPS
[Slice]
MemoryHigh=$MEM_HIGH
MemoryMax=$MEM_MAX
TasksMax=$TASKS_MAX
CAPS
systemctl daemon-reload
# also apply at runtime if a session is already live (non-fatal under set -e if not)
systemctl set-property "user-$AGENT_UID.slice" "MemoryHigh=$MEM_HIGH" "MemoryMax=$MEM_MAX" "TasksMax=$TASKS_MAX" 2>/dev/null || true
mkdir -p /etc/systemd/system/ssh.service.d
printf '[Service]\nOOMScoreAdjust=-900\n' > /etc/systemd/system/ssh.service.d/oom.conf
systemctl daemon-reload
systemctl enable --now systemd-oomd || true
cat >"/etc/security/limits.d/90-$AGENT_USER.conf" <<LIMITS
$AGENT_USER  soft  nproc   4096
$AGENT_USER  hard  nproc   8192
$AGENT_USER  soft  nofile  16384
$AGENT_USER  hard  nofile  32768
$AGENT_USER  hard  core    0
LIMITS

log "9. Claude Code settings (autonomy; denyRead applies only if sandbox enabled)"
su - "$AGENT_USER" -c 'mkdir -p ~/.claude ~/workspace'
# idempotent: never clobber settings the user customized after first provision.
# NOTE: the real secrets protection is "no long-lived secret in env" (interactive
# OAuth login) — denyRead only takes effect if you later flip sandbox.enabled=true.
if su - "$AGENT_USER" -c 'test -f ~/.claude/settings.json'; then
  echo "settings.json already present — left as-is (idempotent)"
else
  su - "$AGENT_USER" -c 'cat > ~/.claude/settings.json' <<'SETTINGS'
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": { "defaultMode": "bypassPermissions" },
  "sandbox": {
    "enabled": false,
    "filesystem": { "denyRead": ["~/.ssh", "~/.aws", "~/.config/gcloud", "~/.kube", "~/.azure"] }
  }
}
SETTINGS
fi

if [ -n "$GIT_NAME" ]; then su - "$AGENT_USER" -c "git config --global user.name \"$GIT_NAME\""; fi
if [ -n "$GIT_EMAIL" ]; then su - "$AGENT_USER" -c "git config --global user.email \"$GIT_EMAIL\""; fi
su - "$AGENT_USER" -c 'git config --global init.defaultBranch main'

log "10. Tailscale (auth is interactive)"
command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | bash
echo "NEXT (manual): tailscale up --hostname=<name>  → authorize URL"
echo "THEN: verify 'ssh $AGENT_USER@<tailnet-ip>' in a 2nd session BEFORE closing public :22"
log "PROVISION COMPLETE — run scripts/verify.py to confirm invariants"
