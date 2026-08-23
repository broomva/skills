#!/usr/bin/env bash
#
# deploy-render.sh - preflight, create and deploy the Parallax hub on Render.
#
# SAFE BY DEFAULT. With no flags this script changes NOTHING: it validates the
# Blueprint against the live Render API, checks that the entrypoint the
# Blueprint names actually exists, looks the service up, and prints what would
# happen. You have to ask for a mutation explicitly.
#
#   ./scripts/deploy-render.sh                 preflight only (read-only)
#   ./scripts/deploy-render.sh --create        create the service if absent
#   ./scripts/deploy-render.sh --deploy        trigger a deploy and tail it
#   ./scripts/deploy-render.sh --create --deploy
#
# FLAGS
#   --create        Create the service if it does not exist. No-op if it does.
#   --deploy        Trigger a deploy of the current branch tip and stream build
#                   and runtime logs until the deploy settles.
#   --clear-cache   With --deploy, clear the build cache first.
#   --no-wait       With --deploy, fire and return instead of streaming.
#   -h, --help      This text.
#
# EXIT CODES
#   0  ready, or the requested action succeeded
#   1  a real failure (no CLI, not logged in, invalid Blueprint, deploy failed)
#   3  the service does not exist yet and --create was not passed. This is a
#      state, not an error: it tells you the next command to run.
#
# ON SECRETS
#   This script NEVER reads, prints, copies or passes ~/.render/cli.yaml, and
#   never echoes RENDER_API_KEY. Authentication is left entirely to the render
#   CLI, which reads its own config. There is deliberately no `set -x` anywhere
#   here, because tracing would print any token that happened to be in the
#   environment. If you add debugging, use `set -x` around a narrow block and
#   turn it off again, or you will leak a key into a terminal scrollback.
#
# IDEMPOTENCY
#   Preflight and --create are idempotent: --create checks for the service by
#   name first and skips if it is already there. --deploy is convergent rather
#   than strictly idempotent - each invocation starts one deploy of the current
#   branch tip, and Render supersedes an in-flight deploy with the newer one.
#   Running it twice in a row is harmless; it just costs build minutes.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# The directory above this script is the SERVICE root, and it is no longer the
# repository root: this runtime lives inside broomva/skills. Everything Render
# builds is relative to render.yaml's rootDir, which must name the same place.
SERVICE_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BLUEPRINT="$SERVICE_ROOT/render.yaml"

DO_CREATE=0
DO_DEPLOY=0
CLEAR_CACHE=0
WAIT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --create)      DO_CREATE=1 ;;
    --deploy)      DO_DEPLOY=1 ;;
    --clear-cache) CLEAR_CACHE=1 ;;
    --no-wait)     WAIT=0 ;;
    # Print the header block above, stopping at the first non-comment line.
    # Deliberately not a hardcoded line range: a range silently starts spilling
    # source code into --help the moment anyone edits the header.
    -h|--help)
      awk 'NR==1 {next} /^#/ {sub(/^#[[:space:]]?/, ""); print; next} {exit}' "${BASH_SOURCE[0]}"
      exit 0 ;;
    *) echo "unknown flag: $1 (try --help)" >&2; exit 1 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
ok()   { printf '   ok    %s\n' "$*"; }
bad()  { printf '   FAIL  %s\n' "$*" >&2; }
note() { printf '   note  %s\n' "$*"; }

die() { bad "$*"; exit 1; }

# Read a scalar out of render.yaml. Comment lines are stripped first so that
# prose in the header (which mentions several of these key names) cannot be
# mistaken for configuration. Good enough for this file's known flat shape;
# it is not a general YAML parser.
yaml_val() {
  sed 's/[[:space:]]*#.*$//' "$BLUEPRINT" \
    | grep -E "^[[:space:]]*$1:[[:space:]]*[^[:space:]]" \
    | head -1 \
    | sed -E "s/^[[:space:]]*$1:[[:space:]]*//; s/^\"(.*)\"$/\1/; s/[[:space:]]+$//"
}

# ---------------------------------------------------------------- preflight --

step "Preflight"

command -v render >/dev/null 2>&1 \
  || die "render CLI not found. Install: brew install render (or see https://render.com/docs/cli)"
ok "render CLI $(render --version 2>/dev/null | head -1)"

command -v jq >/dev/null 2>&1 || die "jq not found. Install: brew install jq"

[ -f "$BLUEPRINT" ] || die "no render.yaml at $BLUEPRINT"

# Authentication check. Prints the workspace NAME and id - never the key.
WS_JSON="$(render workspace current --output json 2>/dev/null || true)"
[ -n "$WS_JSON" ] || die "not logged in to Render. Run: render login"
WS_NAME="$(printf '%s' "$WS_JSON" | jq -r '.name // empty')"
WS_ID="$(printf '%s' "$WS_JSON" | jq -r '.id // empty')"
[ -n "$WS_ID" ] || die "could not resolve the active Render workspace. Run: render login"
ok "workspace $WS_NAME ($WS_ID)"

SERVICE_NAME="$(yaml_val name)"
PLAN="$(yaml_val plan)"
REGION="$(yaml_val region)"
BRANCH="$(yaml_val branch)"
REPO_URL="$(yaml_val repo)"
RUNTIME="$(yaml_val runtime)"
BUILD_CMD="$(yaml_val buildCommand)"
START_CMD="$(yaml_val startCommand)"
HEALTH_PATH="$(yaml_val healthCheckPath)"

[ -n "$SERVICE_NAME" ] || die "could not read 'name' out of render.yaml"
ok "blueprint declares service '$SERVICE_NAME' ($RUNTIME, $PLAN, $REGION, branch $BRANCH)"

# Validate against the LIVE Render API. The CLI exits 0 even when the blueprint
# is invalid, so the exit code is useless here - the JSON's .valid field is the
# only trustworthy signal. Reading $? instead would report a clean preflight on
# a broken file.
VALIDATION="$(render blueprints validate "$BLUEPRINT" --output json --confirm 2>&1 || true)"
if [ "$(printf '%s' "$VALIDATION" | jq -r '.valid // false' 2>/dev/null)" != "true" ]; then
  bad "render.yaml did not validate:"
  printf '%s\n' "$VALIDATION" >&2
  exit 1
fi
ok "render.yaml validates against the live Render API"

# rootDir and this checkout must name the same directory. They can disagree
# silently, and the failure is not legible: a wrong rootDir builds the repository
# root, finds no bun.lock there, and fails with an error that reads as a missing
# binary rather than a misplaced service root.
ROOT_DIR="$(yaml_val rootDir)"
GIT_TOP="$(git -C "$SERVICE_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$GIT_TOP" ]; then
  REL="${SERVICE_ROOT#"$GIT_TOP"/}"
  [ "$REL" = "$SERVICE_ROOT" ] && REL=""
  if [ "$ROOT_DIR" != "$REL" ]; then
    die "render.yaml rootDir is '$ROOT_DIR' but this checkout puts the service at '$REL'"
  fi
  ok "rootDir '$ROOT_DIR' is where this checkout puts the service"
else
  note "not inside a git checkout; render.yaml rootDir '$ROOT_DIR' was not cross-checked"
fi

# The Bun gate. Render only puts Bun in the image when the SERVICE ROOT carries
# a bun.lock / bun.lockb, a .bun-version, or a BUN_VERSION env var. If someone
# gitignores the lockfile, `bun install` fails at build time with an error that
# looks like a missing binary rather than a missing lockfile.
if git -C "$SERVICE_ROOT" ls-files --error-unmatch bun.lock >/dev/null 2>&1; then
  ok "bun.lock is tracked at the service root ${REL:-.} (Bun will be present in the image)"
elif grep -qE '^[[:space:]]*-[[:space:]]*key:[[:space:]]*BUN_VERSION' "$BLUEPRINT"; then
  note "bun.lock is NOT tracked, but BUN_VERSION is pinned in render.yaml, which"
  note "is on its own enough to put Bun in the image."
else
  die "bun.lock is not tracked and BUN_VERSION is not set. Render will build without Bun."
fi

# The build command is `bun install --frozen-lockfile`, which REFUSES to resolve
# if package.json has drifted from bun.lock. That is the behaviour we want on a
# deploy, but it means adding a dependency without committing the regenerated
# lockfile turns into a failed Render build several minutes in. Catch it here,
# where it costs milliseconds.
if [ -n "${BUILD_CMD##*--frozen-lockfile*}" ]; then
  note "build command does not use --frozen-lockfile; skipping lockfile drift check"
elif command -v bun >/dev/null 2>&1; then
  if (cd "$SERVICE_ROOT" && bun install --frozen-lockfile --dry-run) >/dev/null 2>&1; then
    ok "bun.lock is in sync with package.json (--frozen-lockfile will resolve)"
  else
    bad "package.json and bun.lock have drifted, so the build command"
    bad "  $BUILD_CMD"
    bad "will FAIL on Render. Someone added or changed a dependency without"
    bad "committing the regenerated lockfile. Fix with: bun install"
    exit 1
  fi
else
  note "bun not on PATH locally; skipping lockfile drift check"
fi

# The cross-agent guard. The Blueprint names an entrypoint; if the hub lands at
# a different path, the Blueprint still VALIDATES (the validator checks schema,
# not that the entrypoint resolves) and the failure only shows up as a dead
# service after a full build. Catch it here instead.
ENTRY="$(printf '%s' "$START_CMD" | tr ' ' '\n' | grep -E '\.ts$' | head -1 || true)"
if [ -n "$ENTRY" ]; then
  if [ -f "$SERVICE_ROOT/$ENTRY" ]; then
    ok "start command entrypoint exists: $ENTRY"
  else
    bad "render.yaml startCommand is '$START_CMD' but $ENTRY DOES NOT EXIST."
    bad "A deploy would build fine and then fail its health check for 15 minutes"
    bad "before Render cancels it. Either land that file, or point startCommand"
    bad "at the real hub entrypoint in render.yaml and re-run this script."
    exit 1
  fi
else
  SCRIPT_KEY="$(printf '%s' "$START_CMD" | awk '{print $NF}')"
  if jq -e --arg k "$SCRIPT_KEY" '.scripts[$k] // empty' "$SERVICE_ROOT/package.json" >/dev/null 2>&1; then
    ok "start command resolves to package.json script '$SCRIPT_KEY'"
  else
    die "startCommand '$START_CMD' names neither an existing .ts file nor a package.json script"
  fi
fi

case "$HEALTH_PATH" in
  /*) ok "healthCheckPath $HEALTH_PATH" ;;
  "") note "no healthCheckPath set - deploys will go live without being probed" ;;
  *)  die "healthCheckPath '$HEALTH_PATH' must start with '/'. Render's Blueprint
      validator does NOT enforce this, so it passes validation and then silently
      never passes a health check." ;;
esac

# ------------------------------------------------------------ service lookup --

step "Service lookup"

SERVICES_JSON="$(render services --output json --confirm 2>/dev/null || echo '[]')"
SERVICE_ID="$(printf '%s' "$SERVICES_JSON" \
  | jq -r --arg n "$SERVICE_NAME" '[.[].service | select(.name == $n)][0].id // empty')"

if [ -n "$SERVICE_ID" ]; then
  SERVICE_URL="$(printf '%s' "$SERVICES_JSON" \
    | jq -r --arg n "$SERVICE_NAME" '[.[].service | select(.name == $n)][0].serviceDetails.url // empty')"
  ok "service exists: $SERVICE_NAME ($SERVICE_ID)"
  [ -n "$SERVICE_URL" ] && ok "url $SERVICE_URL"
else
  say "   service '$SERVICE_NAME' does not exist in this workspace yet."
fi

# ----------------------------------------------------------------- creation --

print_create_paths() {
  cat <<EOF

   There are two ways to create it, and they are NOT equivalent.

   A) BLUEPRINT (recommended - render.yaml stays the source of truth)
      The CLI cannot do this: 'render blueprints' only has a 'validate'
      subcommand, there is no launch/apply. It is a dashboard flow:

        1. https://dashboard.render.com/
        2. "New +"  ->  "Blueprint"
        3. Connect the repo:  broomva/skills
        4. Render looks for render.yaml at the REPOSITORY ROOT. This one is at
           skills/simulation/parallax/runtime/render.yaml, so the Blueprint flow
           will not find it unless a root-level render.yaml points here.
        5. Name the blueprint, then "Apply" / "Create Resources"

      A Blueprint that Render can read syncs on every later edit. This file is
      not at the repository root, so until that is resolved it describes the
      service rather than driving it - which is exactly the drift path B warns
      about.

   B) CLI (scriptable, but NOT linked to render.yaml)
      Re-run this script with --create, which runs:

        render services create --name $SERVICE_NAME --type web_service \\
          --repo $REPO_URL --branch $BRANCH --runtime $RUNTIME \\
          --plan $PLAN --region $REGION \\
          --build-command "$BUILD_CMD" \\
          --start-command "$START_CMD" \\
          --health-check-path "$HEALTH_PATH" \\
          --env-var BUN_VERSION=1.3.14 --env-var NODE_ENV=production \\
          --output json --confirm

      This creates the same service, but as a standalone service rather than a
      Blueprint instance. render.yaml then becomes documentation only: later
      edits to it will NOT reach Render, and drift has to be applied by hand
      with 'render services update'. Pick A unless you specifically want a
      service that is not managed by the Blueprint.

      It also does not carry render.yaml's rootDir across: the create call above
      passes no root directory, so the build runs at the repository root, where
      there is no package.json and no bun.lock. Set the service's root directory
      to $ROOT_DIR in the dashboard before the first deploy, or that deploy fails
      on a missing Bun.
EOF
}

if [ -z "$SERVICE_ID" ]; then
  if [ "$DO_CREATE" != "1" ]; then
    print_create_paths
    say ""
    say "   Preflight is clean. Nothing was created or deployed."
    exit 3
  fi

  step "Creating service (path B - standalone, not Blueprint-linked)"
  note "render.yaml will NOT be linked to this service. See --help / path A above."
  note "This create does not set a root directory. Set it to $ROOT_DIR in the"
  note "dashboard before deploying, or the build runs at the repository root."

  CREATE_JSON="$(render services create \
    --name "$SERVICE_NAME" \
    --type web_service \
    --repo "$REPO_URL" \
    --branch "$BRANCH" \
    --runtime "$RUNTIME" \
    --plan "$PLAN" \
    --region "$REGION" \
    --build-command "$BUILD_CMD" \
    --start-command "$START_CMD" \
    --health-check-path "$HEALTH_PATH" \
    --env-var BUN_VERSION=1.3.14 \
    --env-var NODE_ENV=production \
    --output json --confirm)" || die "service creation failed (output above)"

  SERVICE_ID="$(printf '%s' "$CREATE_JSON" | jq -r '.service.id // .id // empty')"
  [ -n "$SERVICE_ID" ] || { printf '%s\n' "$CREATE_JSON" >&2; die "created, but could not parse the service id"; }
  ok "created $SERVICE_NAME ($SERVICE_ID)"
  note "creating a service also starts its first deploy"
fi

# ------------------------------------------------------------------- deploy --

if [ "$DO_DEPLOY" != "1" ]; then
  step "Done (read-only)"
  say "   Service:  $SERVICE_NAME ($SERVICE_ID)"
  say "   Deploy:   ./scripts/deploy-render.sh --deploy"
  say "   Logs:     render logs $SERVICE_ID --tail"
  exit 0
fi

step "Deploying $SERVICE_NAME ($SERVICE_ID)"

DEPLOY_ARGS=("$SERVICE_ID" --output text --confirm)
[ "$CLEAR_CACHE" = "1" ] && DEPLOY_ARGS+=(--clear-cache)
# --wait streams until the deploy settles and exits non-zero if it failed, so a
# failed deploy fails this script rather than being reported as a success.
[ "$WAIT" = "1" ] && DEPLOY_ARGS+=(--wait)

if ! render deploys create "${DEPLOY_ARGS[@]}"; then
  bad "deploy did not succeed."
  bad "Logs: render logs $SERVICE_ID --tail"
  exit 1
fi

step "Deployed"

SERVICE_URL="$(render services --output json --confirm 2>/dev/null \
  | jq -r --arg n "$SERVICE_NAME" '[.[].service | select(.name == $n)][0].serviceDetails.url // empty')"

if [ -n "$SERVICE_URL" ] && [ -n "$HEALTH_PATH" ]; then
  say "   Probing $SERVICE_URL$HEALTH_PATH"
  # On the free plan a cold instance takes about a minute to answer, so a slow
  # first response is not evidence of failure. Hence the generous timeout.
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 120 "$SERVICE_URL$HEALTH_PATH" || echo 000)"
  if [ "$CODE" = "200" ]; then
    ok "health check 200"
  else
    note "health check returned $CODE (a free instance can take ~60s to wake)"
  fi
  say ""
  say "   Landing:  $SERVICE_URL/"
  say "   Health:   $SERVICE_URL$HEALTH_PATH"
fi

say "   Logs:     render logs $SERVICE_ID --tail"
