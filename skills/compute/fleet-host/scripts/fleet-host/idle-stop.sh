#!/bin/bash
# GCP fleet host idle stop (BRO-3651). Run as root by fleet-idle-stop.timer every 5 min.
# Records an idle sample only when no T3 run is active, no heavy slot lock is held, load1 < 0.5 and no
# agent ssh session (interactive or not) is open. After IDLE_SAMPLES consecutive idle samples it powers
# off; Compute Engine treats a guest shutdown as a stop (TERMINATED, disk kept).
set -u
STATE=/var/lib/fleet/idle-count
IDLE_SAMPLES=${IDLE_SAMPLES:-9}
DB=/home/agent/.t3/userdata/statev2.sqlite
busy=""

# An active run, by the same query fleet_census.py uses. An unreadable DB counts as busy (fail safe:
# never stop on missing evidence).
if [ -f "$DB" ]; then
  running=$(sqlite3 "file:$DB?mode=ro" \
    "SELECT count(*) FROM orchestration_v2_projection_runs WHERE status IN ('running','starting','preparing','queued','waiting');" 2>/dev/null) \
    || running=unknown
  [ "$running" = "0" ] || busy="t3:$running"
fi
# A heavy slot is busy only while its lock is held. The .owner file is for humans and can outlive a
# SIGKILLed holder, so it is not evidence (P20 r1 #6).
for lock in /var/lib/fleet/heavy/slot-*.lock; do
  [ -e "$lock" ] || continue
  flock -n "$lock" true || busy="$busy heavy:$(basename "$lock")"
done
awk '{exit !($1 < 0.5)}' /proc/loadavg || busy="$busy load"
# Any agent ssh session, including non-interactive commands (`who` sees only ones with a tty).
pgrep -u agent -f '^sshd: agent' >/dev/null && busy="$busy ssh"

if [ -n "$busy" ]; then
  echo 0 > "$STATE"
  logger -t fleet-idle-stop "busy:$busy"
  exit 0
fi
n=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STATE"
logger -t fleet-idle-stop "idle sample $n/$IDLE_SAMPLES"
if [ "$n" -ge "$IDLE_SAMPLES" ]; then
  echo 0 > "$STATE"
  logger -t fleet-idle-stop "idle for $IDLE_SAMPLES samples; powering off"
  systemctl poweroff
fi
