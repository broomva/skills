"""Pytest integration wrapper for tests/mutation_proof_v2.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutation_proof_v2  # noqa: E402


def test_mutation_proof_pad_tail_gate():
    assert "KILLED" in mutation_proof_v2.prove_pad_tail_gate()


def test_mutation_proof_punch_in_scale_gate():
    assert "KILLED" in mutation_proof_v2.prove_punch_in_scale_gate()


def test_mutation_proof_caption_safe_area_gate():
    assert "KILLED" in mutation_proof_v2.prove_caption_safe_area_gate()


def test_mutation_proof_unheard_min_gap_gate():
    assert "KILLED" in mutation_proof_v2.prove_unheard_min_gap_gate()


def test_mutation_proof_unheard_adaptive_floor_gate():
    assert "KILLED" in mutation_proof_v2.prove_unheard_adaptive_floor_gate()
