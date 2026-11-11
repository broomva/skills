#!/bin/bash
# GCP fleet host startup script (BRO-3651, docs/fleet/gcp-host-template.md §1).
# Instance metadata `startup-script`; runs as root on every boot. Every step checks before it acts,
# so a reboot or a partial first boot re-converges. It never prints a secret.
#
# Security model: agentic-vps (the box IS the sandbox). The agent keeps full capability (passwordless
# sudo, docker, open egress, Claude bypassPermissions). Containment comes from the perimeter (no public
# ingress at all: GCE firewall allows only IAP; access is Tailscale), a disposable VM with a provisioned
# snapshot, per-host revocable credentials, and no long-lived secret in any environment.
set -euo pipefail
umask 022
MD=http://metadata.google.internal/computeMetadata/v1
md() { curl -sf -H 'Metadata-Flavor: Google' "$MD/$1"; }
attr() { md "instance/attributes/$1" || true; }
log() { echo "fleet-startup: $*"; logger -t fleet-startup "$*" || true; }
export DEBIAN_FRONTEND=noninteractive

NAME=$(attr fleet-host-name)
TS_TAG=$(attr fleet-tailscale-tag); case "$TS_TAG" in tag:[a-z0-9-]*) ;; *) TS_TAG=tag:fleet-gcp ;; esac
PROJECT=$(md project/project-id)
HEAVY_SLOTS=$(attr fleet-heavy-slots); case "$HEAVY_SLOTS" in ''|*[!0-9]*) HEAVY_SLOTS=1 ;; esac
A=/home/agent
AGENT_PATH="$A/.local/bin:$A/.bun/bin:$A/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Run as agent with the full PATH. Values are passed as positional args, never spliced into the script.
as_agent() { local s="$1"; shift; sudo -u agent -H env PATH="$AGENT_PATH" bash -c "$s" bash "$@"; }

# 1. agent user: passwordless sudo + docker (agentic-vps: capability preserved), lingering user services.
if ! id agent >/dev/null 2>&1; then
  useradd --create-home --uid 1001 --shell /bin/bash --comment "Coding agent" agent
  log "created user agent"
fi
echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-agent
chmod 440 /etc/sudoers.d/90-agent
visudo -cf /etc/sudoers.d/90-agent >/dev/null
loginctl enable-linger agent
install -d -m 0700 -o agent -g agent $A/.ssh
pub=$(attr fleet-ssh-pubkey)
if [ -n "$pub" ] && ! grep -qxF "$pub" $A/.ssh/authorized_keys 2>/dev/null; then
  echo "$pub" >> $A/.ssh/authorized_keys
  chown agent:agent $A/.ssh/authorized_keys; chmod 0600 $A/.ssh/authorized_keys
fi
# Key-only ssh. sshd listens on all addresses: the GCE firewall admits nothing but IAP (35.235.240.0/20),
# and Tailscale arrives over tailscale0. Binding to the tailnet IP would race tailscaled at boot and can
# lock the host out (Ubuntu 24.04 socket activation), so the firewall is the boundary (P20 r1 #7).
cat > /etc/ssh/sshd_config.d/10-fleet.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
rm -f /etc/ssh/sshd_config.d/20-fleet-listen.conf
sshd -t && { systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true; }

# 2. PATH for every kind of session: PAM (ssh, incl. non-interactive commands), the user's systemd manager
#    (t3code.service), and above Ubuntu's non-interactive guard in .bashrc (P20 r1 BLOCKER 3).
if ! grep -q "^PATH=\"$A/.local/bin" /etc/environment; then
  sed -i '/^PATH=/d' /etc/environment
  echo "PATH=\"$AGENT_PATH\"" >> /etc/environment
fi
install -d -m 0755 -o agent -g agent $A/.config $A/.config/environment.d
echo "PATH=$AGENT_PATH" > $A/.config/environment.d/10-fleet-path.conf
chown agent:agent $A/.config/environment.d/10-fleet-path.conf
if ! grep -q 'fleet host PATH (BRO-3651)' $A/.bashrc 2>/dev/null; then
  { echo "# fleet host PATH (BRO-3651)"; echo "export PATH=\"$AGENT_PATH\""; cat $A/.bashrc 2>/dev/null; } > $A/.bashrc.tmp
  mv $A/.bashrc.tmp $A/.bashrc; chown agent:agent $A/.bashrc
fi

# 3. Tailscale: single-use tagged key from Secret Manager, read with the VM service account.
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if ! tailscale status >/dev/null 2>&1; then
  tok=$(md "instance/service-accounts/default/token" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
  key=$(curl -sf -H "Authorization: Bearer $tok" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT/secrets/fleet-$NAME-ts-authkey/versions/latest:access" \
    | python3 -c 'import base64,json,sys;print(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())') || key=""
  unset tok
  if [ -n "$key" ]; then
    # The key goes through a 0600 file, never argv (visible in ps) or the log.
    kd=$(umask 077; mktemp -d); printf '%s' "$key" > "$kd/k"; unset key
    rc=0; tailscale up --auth-key="file:$kd/k" --hostname="$NAME" --advertise-tags="$TS_TAG" --ssh=false || rc=$?
    rm -rf "$kd"; [ "$rc" = 0 ] || exit "$rc"
    log "joined tailnet as $NAME"
  else
    log "tailscale auth key not readable yet; retry on next boot or fleet_host.py add"
  fi
fi
# agent runs T3, and `t3 pair --tailscale` publishes it with Tailscale Serve (the Mac links over HTTPS).
tailscale status >/dev/null 2>&1 && tailscale set --operator=agent

# 4. Toolchain (apt), as in agentic-vps provision.sh plus psql 18 and sqlite3.
if [ ! -f /var/lib/fleet/apt-done ]; then
  install -d /var/lib/fleet
  apt-get update -q
  apt-get install -yq git build-essential pkg-config libssl-dev jq sqlite3 tmux htop ripgrep fd-find \
    bubblewrap socat python3 python3-venv curl wget ca-certificates gnupg unzip
  install -d /usr/share/postgresql-common/pgdg /etc/apt/keyrings
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release; echo "$VERSION_CODENAME")-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get update -q
  apt-get install -yq postgresql-client-18 gh nodejs docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  touch /var/lib/fleet/apt-done
fi
usermod -aG docker agent
systemctl enable --now docker

# 5. Host-survival caps (agentic-vps: generous, not a throttle), sized to this machine.
mem_gib=$(awk '/MemTotal/ {print int($2/1048576)}' /proc/meminfo)
install -d /etc/systemd/system/user-1001.slice.d /etc/systemd/system/ssh.service.d
cat > /etc/systemd/system/user-1001.slice.d/50-agent-caps.conf <<EOF
[Slice]
MemoryHigh=$((mem_gib - 5))G
MemoryMax=$((mem_gib - 3))G
TasksMax=16384
EOF
printf '[Service]\nOOMScoreAdjust=-900\n' > /etc/systemd/system/ssh.service.d/oom.conf
cat > /etc/security/limits.d/90-agent.conf <<'EOF'
agent  soft  nproc   8192
agent  hard  nproc   16384
agent  soft  nofile  65536
agent  hard  nofile  65536
agent  hard  core    0
EOF
systemctl daemon-reload
systemctl enable --now systemd-oomd 2>/dev/null || true

# 6. Per-user tools as agent (bun, uv, CLIs without credentials, claude, codex).
as_agent 'command -v bun >/dev/null || curl -fsSL https://bun.sh/install | bash'
as_agent 'command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh'
as_agent 'for p in neonctl vercel @schpet/linear-cli @googleworkspace/cli @openai/codex; do
  bun pm ls -g 2>/dev/null | grep -q "$p@" || bun add -g "$p"; done'
claude_version=$(attr fleet-claude-version)
case "$claude_version" in ''|stable|latest|[0-9]*.[0-9]*.[0-9]*) ;; *) claude_version=stable ;; esac
as_agent 'command -v claude >/dev/null || curl -fsSL https://claude.ai/install.sh | bash -s "$1"' "${claude_version:-stable}"
# Claude Code: autonomy (agentic-vps). The installer writes its own settings.json first, so merge:
# set only the keys that are missing and keep everything else the file already has.
as_agent "python3 - <<'PY'
import json, os
p = os.path.expanduser('~/.claude/settings.json'); os.makedirs(os.path.dirname(p), exist_ok=True)
d = json.load(open(p)) if os.path.exists(p) else {}
d.setdefault('permissions', {}).setdefault('defaultMode', 'bypassPermissions')
d.setdefault('sandbox', {'enabled': False, 'filesystem': {'denyRead': [
    '~/.ssh', '~/.config/fleet', '~/.config/gcloud', '~/.aws', '~/.kube']}})
json.dump(d, open(p + '.tmp', 'w'), indent=2); os.replace(p + '.tmp', p)
PY"

# 6b. An LLM with no login (BRO-3666): Gemini CLI on Vertex through the VM service account. No key file:
#     with GOOGLE_APPLICATION_CREDENTIALS unset, ADC falls back to the metadata server. The CLI home is
#     isolated and pinned to vertex-ai, so a later personal `gemini` login can never take over (the T3
#     probe trap seen on the Mac, 2026-10-28). `gemini-vertex` is for shells; `-acp` is T3's provider.
gv_version=$(attr fleet-gemini-cli-version); gv_location=$(attr fleet-vertex-location)
case "$gv_version" in [0-9]*.[0-9]*.[0-9]*) ;; *) gv_version="" ;; esac
case "$gv_location" in ''|*[!a-z0-9-]*) gv_location="" ;; esac
if [ -n "$gv_version" ] && [ -n "$gv_location" ]; then
  [ "$(gemini --version 2>/dev/null)" = "$gv_version" ] || npm install -g --no-fund --no-audit "@google/gemini-cli@$gv_version"
  GV=$A/.local/share/broomva/gemini-vertex
  as_agent 'mkdir -p "$1/bin" "$1/home/.gemini" "$HOME/.local/bin"
    printf "%s\n" "{\"security\":{\"auth\":{\"selectedType\":\"vertex-ai\"}},\"general\":{\"enableAutoUpdate\":false},\"privacy\":{\"usageStatisticsEnabled\":false}}" > "$1/home/.gemini/settings.json"
    for mode in acp cli; do
      f="$1/bin/gemini-vertex-$mode"; [ "$mode" = cli ] && f="$HOME/.local/bin/gemini-vertex"
      { echo "#!/bin/sh"
        echo "# Gemini CLI on Vertex via the VM service account (fleet host, BRO-3666). Written by startup.sh."
        echo "unset GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_APPLICATION_CREDENTIALS"
        echo "export GEMINI_CLI_HOME=\"$1/home\" GOOGLE_GENAI_USE_VERTEXAI=true GEMINI_CLI_TRUST_WORKSPACE=true"
        echo "export GOOGLE_CLOUD_PROJECT=\"$2\" GOOGLE_CLOUD_QUOTA_PROJECT=\"$2\" GOOGLE_CLOUD_LOCATION=\"$3\""
        if [ "$mode" = acp ]; then echo "exec gemini --acp \"\$@\""; else echo "exec gemini \"\$@\""; fi
      } > "$f.tmp" && chmod 0755 "$f.tmp" && mv "$f.tmp" "$f"
    done' "$GV" "$PROJECT" "$gv_location"
else  # Vertex off in the template: no wrappers left behind (the T3 provider is removed by the t3 step)
  rm -f "$A/.local/share/broomva/gemini-vertex/bin/gemini-vertex-acp" "$A/.local/bin/gemini-vertex"
fi

# 7. Heavy semaphore and idle stop. The lock directory belongs to agent (heavy-run runs as agent);
#    root's idle check only probes the locks.
install -d -m 0755 -o agent -g agent /var/lib/fleet/heavy
[ -e /var/lib/fleet/awake-until ] || install -m 0644 -o agent -g agent /dev/null /var/lib/fleet/awake-until  # agent holds the host awake
install -d /etc/fleet
echo "$HEAVY_SLOTS" > /etc/fleet/heavy-slots
attr fleet-heavy-run > /usr/local/bin/fleet-heavy-run; chmod 0755 /usr/local/bin/fleet-heavy-run
attr fleet-idle-stop > /usr/local/sbin/fleet-idle-stop; chmod 0700 /usr/local/sbin/fleet-idle-stop
echo 0 > /var/lib/fleet/idle-count  # a fresh boot starts a fresh idle window
cat > /etc/systemd/system/fleet-idle-stop.service <<'EOF'
[Unit]
Description=Fleet host idle stop sample (BRO-3651)
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/fleet-idle-stop
EOF
cat > /etc/systemd/system/fleet-idle-stop.timer <<'EOF'
[Unit]
Description=Fleet host idle stop every 5 min (BRO-3651)
[Timer]
OnBootSec=15min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now fleet-idle-stop.timer

# 8. Git identity from the Mac (metadata), never a placeholder. Values are arguments, not script text.
gname=$(attr fleet-git-name); gmail=$(attr fleet-git-email)
case "$gmail" in *@example.com|"") log "git identity missing or placeholder; not set" ;;
  *) as_agent 'git config --global user.name "$1"; git config --global user.email "$2"; git config --global init.defaultBranch main' "$gname" "$gmail" ;;
esac

# 9. Ready marker. Repos, provider logins, T3 and secrets are fleet_host.py steps over ssh.
as_agent 'python3 - <<EOF
import json,shutil,subprocess
def v(c):
    try: return subprocess.run(c,capture_output=True,text=True,timeout=20).stdout.strip().splitlines()[0]
    except Exception: return None
tools={t:shutil.which(t) is not None for t in ["bun","git","gh","node","psql","neonctl","vercel","linear","gws","uv","python3","claude","codex","tailscale","sqlite3","docker"]}
import os
if os.path.exists(os.path.expanduser("~/.local/share/broomva/gemini-vertex/bin/gemini-vertex-acp")): tools["gemini-vertex"]=shutil.which("gemini") is not None
print(json.dumps({"tools":tools,"psql":v(["psql","--version"]),"node":v(["node","--version"]),"bun":v(["bun","--version"])}))
EOF' > /var/lib/fleet/ready.json.tmp && mv /var/lib/fleet/ready.json.tmp /var/lib/fleet/ready.json
log "ready"
