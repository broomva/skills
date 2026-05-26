#!/usr/bin/env bash
# Start all CaP-X perception microservices
# Requires: CUDA GPU, Python 3.10+, CaP-X installed

set -euo pipefail

CAPX_DIR="${CAPX_DIR:-$(pwd)}"
LOG_DIR="${CAPX_DIR}/logs/perception"
mkdir -p "$LOG_DIR"

echo "Starting CaP-X perception services..."
echo "  CAPX_DIR: $CAPX_DIR"
echo "  LOG_DIR:  $LOG_DIR"

# Check CUDA availability
if ! python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    echo "ERROR: CUDA not available. Perception services require GPU."
    exit 1
fi

# SAM3 Segmentation (port 8114)
echo "  [1/5] SAM3 segmentation → port 8114"
python3 -m capx.perception.sam3_server \
    --port 8114 \
    > "$LOG_DIR/sam3.log" 2>&1 &
SAM3_PID=$!

# ContactGraspNet (port 8115)
echo "  [2/5] ContactGraspNet grasps → port 8115"
python3 -m capx.perception.grasp_server \
    --port 8115 \
    > "$LOG_DIR/grasp.log" 2>&1 &
GRASP_PID=$!

# PyRoKi IK solver (port 8116)
echo "  [3/5] PyRoKi IK solver → port 8116"
python3 -m capx.perception.ik_server \
    --port 8116 \
    > "$LOG_DIR/ik.log" 2>&1 &
IK_PID=$!

# Molmo 2 pointing (port 8117)
echo "  [4/5] Molmo 2 pointing → port 8117"
python3 -m capx.perception.molmo_server \
    --port 8117 \
    > "$LOG_DIR/molmo.log" 2>&1 &
MOLMO_PID=$!

# OWL-ViT detection (port 8118)
echo "  [5/5] OWL-ViT detection → port 8118"
python3 -m capx.perception.owlvit_server \
    --port 8118 \
    > "$LOG_DIR/owlvit.log" 2>&1 &
OWLVIT_PID=$!

echo ""
echo "All services starting. PIDs:"
echo "  SAM3:             $SAM3_PID"
echo "  ContactGraspNet:  $GRASP_PID"
echo "  PyRoKi:           $IK_PID"
echo "  Molmo:            $MOLMO_PID"
echo "  OWL-ViT:          $OWLVIT_PID"
echo ""
echo "Logs: $LOG_DIR/"
echo "Health check: curl http://localhost:{8114,8115,8116,8117,8118}/health"

# Wait for all services
wait
