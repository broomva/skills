"""Autonomous operator — a self-dogfooding control loop for the trading bridge.

The operator is a controller in the RCS sense:
  - Plant:      broker positions + bridge pipeline state
  - Controller: the multi-rate tick loop (sense -> verify -> decide -> act)
  - Shields:    policy.yaml gates (paper-only, dogfood-must-pass, position caps)
  - Feedback:   continuous self-dogfood canary + bookkeeping journal

The safety heart is the **dogfood-as-precondition interlock**: if the
self-dogfood canary fails, the operator halts all position management. You
never manage money on a pipeline you cannot confirm works.

Modules:
  state      — OperatorState, filesystem-persisted (P12 cross-context)
  canary     — CanaryProbe: the self-dogfood roundtrip check
  positions  — PositionManager: net positions + drift from the order ledger
  report     — journal each tick to structured log + bookkeeping
  loop       — OperatorLoop: multi-rate tick + the interlock
  cli        — `operate` entry point (tick / run / status / positions / reset)
"""

from .canary import CanaryProbe, CanaryResult
from .loop import OperatorLoop
from .positions import Drift, PositionManager, Reconciliation
from .report import report_tick
from .state import CanarySnapshot, OperatorState

__all__ = [
    "CanaryProbe",
    "CanaryResult",
    "CanarySnapshot",
    "Drift",
    "OperatorLoop",
    "OperatorState",
    "PositionManager",
    "Reconciliation",
    "report_tick",
]
