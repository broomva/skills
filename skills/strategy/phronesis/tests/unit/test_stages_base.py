"""StageBase contract tests."""

from __future__ import annotations

import abc

import pytest

from stages.base import StageBase

pytestmark = pytest.mark.unit


class TestStageBase:
    def test_is_abstract_base_class(self):
        assert issubclass(StageBase, abc.ABC)

    def test_cannot_instantiate_without_methods(self):
        with pytest.raises(TypeError):
            StageBase()  # type: ignore[abstract]
