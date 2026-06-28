#!/usr/bin/env bash
# Run CaP-Bench evaluation sweep across models and tiers
# Usage: ./run-benchmark.sh [--model MODEL] [--tier TIER] [--task TASK] [--trials N]

set -euo pipefail

CAPX_DIR="${CAPX_DIR:-$(pwd)}"
MODEL="${MODEL:-openai/gpt-5.2}"
TIER="${TIER:-S1}"
TASK="${TASK:-all}"
TRIALS="${TRIALS:-100}"
OUTPUT_DIR="${CAPX_DIR}/results"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)  MODEL="$2"; shift 2 ;;
        --tier)   TIER="$2"; shift 2 ;;
        --task)   TASK="$2"; shift 2 ;;
        --trials) TRIALS="$2"; shift 2 ;;
        *)        echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

TASKS=("cube_lift" "cube_stack" "spill_wipe" "peg_insertion" "cube_restack" "two_arm_lift" "two_arm_handover")

if [[ "$TASK" != "all" ]]; then
    TASKS=("$TASK")
fi

echo "CaP-Bench Evaluation"
echo "  Model:  $MODEL"
echo "  Tier:   $TIER"
echo "  Tasks:  ${TASKS[*]}"
echo "  Trials: $TRIALS"
echo "  Output: $OUTPUT_DIR"
echo ""

for task in "${TASKS[@]}"; do
    echo "=== $task ($TIER) ==="
    python3 scripts/eval.py \
        --task "$task" \
        --model "$MODEL" \
        --tier "$TIER" \
        --num_trials "$TRIALS" \
        --output "$OUTPUT_DIR/${task}_${TIER}_$(echo "$MODEL" | tr '/' '_').json"
    echo ""
done

echo "Done. Results in $OUTPUT_DIR/"
