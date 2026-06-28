#!/usr/bin/env bash
# dogfood.sh — CLI wrapper for the broomva/dogfood skill (P11 reflex trigger)
#
# Subcommands:
#   detect              echo the detected tech stack for cwd
#   plan [opts]         emit a six-row Dogfood Plan template
#   explore [opts]      emit the per-stack execution recipe (web: agent-browser
#                       session workflow; tauri: cliclick + screencapture;
#                       expo-rn: xcrun simctl; rest-api: curl+jq; etc.)
#   receipt [opts]      emit a Dogfood Receipt scaffold from a plan
#   help                show usage
#
# Options for plan / receipt / explore:
#   --stack=<name>      override stack detection
#   --ticket=<id>       anchor evidence to a Linear / GitHub ticket id
#   --plan=<path>       (receipt only) path to plan file to fill receipt against
#   --evidence-dir=<p>  where to anchor evidence paths (default: ./dogfood-output/<slug> for explore;
#                                                    /tmp/dogfood-<ts> for plan/receipt)
#   --url=<url>         (explore only) target URL for web stacks (forces web mode)
#   --session=<name>    (explore only) named agent-browser session (default: slug of URL)
#
# Composition: the explore subcommand for web stacks composes the agent-browser
# workflow from the pre-existing dogfood skill at ~/.agents/skills/dogfood/.
# See references/bstack-inheritance.md for attribution + the upstream.
#
# Inherits stack detection from bstack/scripts/doctor.sh §13. Falls back to a
# minimum surfaces table if bstack isn't installed.

set -uo pipefail

cmd="${1:-help}"
shift 2>/dev/null || true

STACK=""
TICKET=""
PLAN_PATH=""
EVIDENCE_DIR=""
URL=""
SESSION=""

for arg in "$@"; do
    case "$arg" in
        --stack=*)         STACK="${arg#*=}" ;;
        --ticket=*)        TICKET="${arg#*=}" ;;
        --plan=*)          PLAN_PATH="${arg#*=}" ;;
        --evidence-dir=*)  EVIDENCE_DIR="${arg#*=}" ;;
        --url=*)           URL="${arg#*=}" ;;
        --session=*)       SESSION="${arg#*=}" ;;
        *) ;;
    esac
done

detect_stack() {
    local ws="${BROOMVA_WORKSPACE:-$PWD}"

    if [ -f "$ws/Cargo.toml" ] && [ -d "$ws/src-tauri" ]; then
        echo "tauri-sidecar"
    elif [ -d "$ws/app/src-tauri" ] || compgen -G "$ws/*/src-tauri" > /dev/null 2>&1; then
        echo "tauri-sidecar"
    elif compgen -G "$ws/next.config.*" > /dev/null 2>&1; then
        echo "nextjs"
    elif [ -f "$ws/app.json" ] && grep -q '"expo"' "$ws/app.json" 2>/dev/null; then
        echo "expo-rn"
    elif [ -f "$ws/Cargo.toml" ]; then
        echo "rust-cli"
    elif compgen -G "$ws/openapi.*" > /dev/null 2>&1; then
        echo "rest-api"
    elif [ -f "$ws/mcp.json" ] || [ -f "$ws/mcp.yaml" ]; then
        echo "mcp-server"
    elif [ -f "$ws/package.json" ] && grep -qE '"(fastapi|hono|axum|express)"' "$ws/package.json" 2>/dev/null; then
        echo "rest-api"
    else
        echo "unknown"
    fi
}

usage() {
    sed -n '2,28p' "$0" | sed 's/^# \?//'
    exit 0
}

slug_url() {
    # Slugify a URL into a session-name-safe string
    echo "$1" | sed -E 's|^https?://||; s|/.*$||; s|[^a-zA-Z0-9-]|-|g' | tr '[:upper:]' '[:lower:]'
}

case "$cmd" in
    detect)
        detect_stack
        ;;

    plan)
        if [ -z "$STACK" ]; then
            STACK=$(detect_stack)
        fi
        if [ -z "$EVIDENCE_DIR" ]; then
            EVIDENCE_DIR="/tmp/dogfood-$(date +%s)"
        fi
        ticket_line=""
        [ -n "$TICKET" ] && ticket_line=", ticket: $TICKET"

        cat <<EOF
**Dogfood Plan** (stack: $STACK$ticket_line)

- **Entry surface**: <URL / window / CLI command the user touches>
- **Driver**: <see surfaces for stack: $STACK below>
- **Evidence**: <paths under $EVIDENCE_DIR>
- **Smoke**: <one-line "didn't obviously break" check>
- **End-to-end**: <multi-step user flow that catches regression a smoke test misses>
- **Receipt anchor**: <PR comment / file / message-id where the receipt lives>

<!-- Surfaces for stack: $STACK -->
EOF
        case "$STACK" in
            tauri-sidecar) cat <<EOF
<!-- curl+jq engine API (state assertions)
     cliclick + screencapture (WebView UI flow)
     Interceptor at :1420 (React DOM, network log; mandatory for visual verification) -->
EOF
            ;;
            nextjs) cat <<EOF
<!-- Dev server log-tail via run_in_background
     Interceptor for authenticated flows (mandatory for visual verification)
     curl + jq for API routes / server actions
     before-and-after skill for visible-change PRs
     Vercel preview URL → Interceptor for deploy verification -->
EOF
            ;;
            expo-rn) cat <<EOF
<!-- expo start --ios; xcrun simctl io booted screenshot for visual evidence
     Reactotron / async-storage CLI for state assertions
     Detox (if wired) for automated E2E -->
EOF
            ;;
            rust-cli) cat <<EOF
<!-- Direct invocation: cargo run -- <args> (dev) ; ./target/release/<bin> <args> (release)
     trycmd / assert_cmd for repeatable CLI scenarios
     insta for output-format regression snapshots
     --help smoke + script / asciinema rec for TUI flows -->
EOF
            ;;
            rest-api) cat <<EOF
<!-- curl + jq for endpoint behavior
     run_in_background tail of dev server stdout
     OpenAPI schema diff for public-contract regression
     DB snapshot before/after for side-effect verification -->
EOF
            ;;
            mcp-server) cat <<EOF
<!-- npx @modelcontextprotocol/inspector <server-cmd> for tool discovery
     Direct LLM invocation in a fresh session for realistic tool use
     Bridge / conversation log grep for what model actually did
     Server log tail for what the tool saw -->
EOF
            ;;
            *)
                echo "<!-- stack: unknown — agent declares surfaces explicitly in plan -->"
                ;;
        esac
        ;;

    receipt)
        if [ -z "$PLAN_PATH" ]; then
            echo "error: receipt requires --plan=<path>" >&2
            exit 2
        fi
        if [ ! -f "$PLAN_PATH" ]; then
            echo "error: plan file not found: $PLAN_PATH" >&2
            exit 2
        fi
        ticket_line=""
        [ -n "$TICKET" ] && ticket_line=" — $TICKET"
        date_line=$(date -u +%Y-%m-%d)

        cat <<EOF
**Dogfood Receipt**$ticket_line · $date_line

| Plan row | Executed | Evidence |
|---|---|---|
| Smoke | <✅/⊘> | <evidence: path / output line> |
| End-to-end | <✅/⊘> | <screenshot paths or recording> |
| API contract | <✅/⊘> | <response captured where> |
| Side-effect | <✅/⊘> | <DB / log / state assertion> |
| Deploy preview | <✅/⊘> | <preview URL + Interceptor screenshot path> |

**Anti-rationalization check**: did I actually click the app like a user would? <yes/no>
**Surfaces driven**: <Interceptor / cliclick / curl / etc.>
**Time-to-receipt**: <duration> from first write to receipt complete.

<!-- Source plan: $PLAN_PATH -->
EOF
        ;;

    explore)
        # If --url was passed, force web mode regardless of stack
        if [ -n "$URL" ]; then
            STACK="${STACK:-web-explicit}"
        elif [ -z "$STACK" ]; then
            STACK=$(detect_stack)
        fi
        if [ -z "$EVIDENCE_DIR" ]; then
            # web sessions get a stable per-slug path; non-web fall back to /tmp/dogfood-<ts>
            if [ -n "$URL" ]; then
                EVIDENCE_DIR="./dogfood-output/$(slug_url "$URL")"
            else
                EVIDENCE_DIR="/tmp/dogfood-$(date +%s)"
            fi
        fi
        if [ -z "$SESSION" ] && [ -n "$URL" ]; then
            SESSION=$(slug_url "$URL")
        fi
        [ -z "$SESSION" ] && SESSION="dogfood-$(date +%s)"

        cat <<EOF
# Dogfood Explore — stack: $STACK
# Evidence dir: $EVIDENCE_DIR
# Session: $SESSION
${TICKET:+# Ticket: $TICKET
}
EOF
        case "$STACK" in
            nextjs|web-explicit|rest-api)
                # Web stacks → compose with the agent-browser exploratory workflow.
                # Attribution: workflow adapted from the dogfood skill at
                # ~/.agents/skills/dogfood/. See references/bstack-inheritance.md.
                if [ -z "$URL" ]; then
                    echo "# (no --url passed; running against the dev server is implied — set URL below)"
                    URL="http://localhost:3000"
                fi
                cat <<EOF

# 1. Initialize
mkdir -p "$EVIDENCE_DIR/screenshots" "$EVIDENCE_DIR/videos"
cp "\$(dirname "\$(readlink -f "\$0" 2>/dev/null || echo "\$0")")/../templates/exploratory-report.md" "$EVIDENCE_DIR/report.md" || \\
    echo "(adapt templates/exploratory-report.md → $EVIDENCE_DIR/report.md manually)"

# 2. Start session
agent-browser --session $SESSION open $URL
agent-browser --session $SESSION wait --load networkidle

# 3. Orient
agent-browser --session $SESSION screenshot --annotate "$EVIDENCE_DIR/screenshots/initial.png"
agent-browser --session $SESSION snapshot -i

# 4. Explore (read references/exploratory-issue-taxonomy.md first)
#    For each page / feature:
agent-browser --session $SESSION snapshot -i
agent-browser --session $SESSION screenshot --annotate "$EVIDENCE_DIR/screenshots/<page-name>.png"
agent-browser --session $SESSION errors
agent-browser --session $SESSION console

# 5. Document Issues (Repro-First) — see exploratory-report.md
#    Interactive issues need video + step-by-step screenshots:
agent-browser --session $SESSION record start "$EVIDENCE_DIR/videos/issue-001-repro.webm"
#    ... walk through steps, screenshot each ...
agent-browser --session $SESSION record stop

# 6. Wrap up — close session, update report totals
agent-browser --session $SESSION close

# Evidence dir: $EVIDENCE_DIR/report.md (becomes the parent Dogfood Plan's Evidence row)
EOF
                ;;
            tauri-sidecar)
                cat <<EOF

# Tauri+sidecar exploration recipe (WebView opaque to AppleScript; hybrid drivers)
mkdir -p "$EVIDENCE_DIR/screenshots"

# Engine state assertions (curl + jq against the engine sidecar port)
PORT=\$(jq -r '.port' ~/.dev-<app>/engine.json)
TOKEN=\$<TOKEN_VAR>
curl -sS -H "Authorization: Bearer \$TOKEN" "http://127.0.0.1:\$PORT/v1/health" | jq

# UI flow via cliclick + screencapture (drives the Tauri window)
osascript -e 'tell application "<AppName>" to activate'
sleep 1
screencapture -x -t png -R x,y,w,h "$EVIDENCE_DIR/screenshots/initial.png"
cliclick c:X,Y t:"input text" kp:return
sleep 1
screencapture -x -t png -R x,y,w,h "$EVIDENCE_DIR/screenshots/after-input.png"

# React DOM via Interceptor on the vite dev server (:1420)
# (Inject window.__APP_ENGINE__ = { baseUrl, token } before reload, then use Interceptor read/act/inspect)
EOF
                ;;
            expo-rn)
                cat <<EOF

# Expo/RN exploration recipe (iOS simulator drive)
mkdir -p "$EVIDENCE_DIR/screenshots"
expo start --ios &
# Wait for simulator boot, then capture baseline
sleep 5
xcrun simctl io booted screenshot "$EVIDENCE_DIR/screenshots/baseline.png"
# For each tap / scroll, screenshot:
xcrun simctl io booted screenshot "$EVIDENCE_DIR/screenshots/<state>.png"
# For flow recording: xcrun simctl io booted recordVideo "$EVIDENCE_DIR/videos/flow.mov"
EOF
                ;;
            rust-cli)
                cat <<EOF

# Rust CLI exploration recipe (direct invocation + script capture)
mkdir -p "$EVIDENCE_DIR/logs"
# Smoke
./target/release/<bin> --version
./target/release/<bin> --help | tee "$EVIDENCE_DIR/logs/help.txt"
# Capture a real-args session
script -q "$EVIDENCE_DIR/logs/session.log" ./target/release/<bin> <real-args>
EOF
                ;;
            mcp-server)
                cat <<EOF

# MCP-server exploration recipe (inspector + direct LLM invocation)
mkdir -p "$EVIDENCE_DIR/logs"
# Tool discovery + manual invocation
npx @modelcontextprotocol/inspector <server-cmd> &
INSPECTOR_PID=\$!
# In a fresh Claude/GPT session, invoke each affected tool with realistic prompts
# Capture: tool response + server log + conversation transcript
EOF
                ;;
            *)
                cat <<EOF

# Stack: $STACK (no canned exploration recipe — agent picks driver from cookbook)
# Reference: bstack/references/dogfood-patterns.md
# Manual steps:
#   1. Identify the user-facing surface (URL / window / CLI / endpoint)
#   2. Pick the driver from the cookbook (Interceptor / curl / cliclick / xcrun simctl / ...)
#   3. Capture multi-modal evidence in $EVIDENCE_DIR
#   4. Run \`dogfood receipt --plan=<path>\` when done
EOF
                ;;
        esac
        ;;

    help|--help|-h|"")
        usage
        ;;

    *)
        echo "dogfood: unknown subcommand: $cmd" >&2
        echo "Run: $0 help" >&2
        exit 2
        ;;
esac
