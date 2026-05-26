# Health skill — make targets
# Run from skills/Health/

SHELL := /usr/bin/env bash
PY := python3
UV := uv

.PHONY: help install dev test lint typecheck format check doctor sync status clean

help:  ## list targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / { printf "  %-15s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install:  ## editable install (uv)
	$(UV) pip install -e .

dev:  ## install dev extras
	$(UV) pip install -e ".[dev]"

test:  ## run unit tests
	$(UV) run pytest -q

test-e2e:  ## run e2e tests (requires BROOMVA_HEALTH_E2E=1 and real Garmin creds)
	BROOMVA_HEALTH_E2E=1 $(UV) run pytest -q -m e2e

lint:  ## ruff
	$(UV) run ruff check src tests

format:  ## ruff format
	$(UV) run ruff format src tests

typecheck:  ## mypy
	$(UV) run mypy src

check: lint typecheck test  ## full pre-push validation

doctor:  ## diagnostic — verifies install + paths
	$(UV) run health doctor

sync:  ## sync default source
	$(UV) run health sync

status:  ## reflex snapshot
	$(UV) run health status

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
