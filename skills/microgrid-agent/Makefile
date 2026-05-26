# =============================================================================
# microgrid-agent — Makefile
# =============================================================================
# Targets for development, testing, deployment, and operations.
# =============================================================================

.PHONY: test test-rust test-python test-cov test-one simulate sim shadow run \
        lint format typecheck \
        deploy-rpi install-service status-rpi logs-rpi \
        docker-build docker-run docker-test \
        kernel-build kernel-check \
        health install install-rpi dev clean distclean help \
        smoke check control-audit bstack-check

# Configuration
PYTHON       ?= python3
VENV         ?= .venv
PIP          := $(VENV)/bin/pip
PYTEST       := $(shell command -v $(VENV)/bin/pytest 2>/dev/null || echo pytest)
RUFF         := $(shell command -v $(VENV)/bin/ruff 2>/dev/null || echo ruff)
AGENT        := $(PYTHON)

# RPi deployment (set MICROGRID_HOST=user@hostname or legacy HOST=ip)
MICROGRID_HOST ?= $(if $(HOST),pi@$(HOST),pi@microgrid-001.local)
DEPLOY_PATH    ?= /opt/microgrid-agent
SERVICE_NAME   ?= microgrid-agent

# Docker
IMAGE_NAME   ?= microgrid-agent
IMAGE_TAG    ?= latest

# =============================================================================
# Development
# =============================================================================

## Install dependencies in virtual environment
install: $(VENV)/bin/activate
	$(PIP) install -e ".[dev,ingest]"

## Install with RPi hardware dependencies
install-rpi: $(VENV)/bin/activate
	$(PIP) install -e ".[dev,rpi]"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

## Set up development environment from scratch
dev: install
	@echo "Development environment ready."
	@echo "Activate with: source $(VENV)/bin/activate"

# =============================================================================
# Testing
# =============================================================================

## Run all tests (Rust + Python)
test: test-rust test-python

## Run Rust kernel tests
test-rust:
	cd kernel && cargo test

## Run Python reference tests
test-python:
	$(PYTEST) reference/tests/ -v --tb=short

## Run tests with coverage report
test-cov:
	$(PYTEST) reference/tests/ -v --tb=short --cov=prototype/src --cov-report=term-missing

## Run a single test file (usage: make test-one FILE=reference/tests/test_devices.py)
test-one:
	$(PYTEST) $(FILE) -v --tb=long

# =============================================================================
# Code Quality
# =============================================================================

## Run ruff linter
lint:
	$(RUFF) check reference/src/ reference/tests/ forecast/ simulation/

## Auto-format code with ruff
format:
	$(RUFF) format reference/src/ reference/tests/ forecast/ simulation/
	$(RUFF) check --fix reference/src/ reference/tests/ forecast/ simulation/

## Run mypy type checker
typecheck:
	$(VENV)/bin/mypy reference/src/ --ignore-missing-imports

## Check Rust kernel compiles
kernel-check:
	cd kernel && cargo check

## Build Rust kernel (release)
kernel-build:
	cd kernel && cargo build --release

# =============================================================================
# Running
# =============================================================================

## Run agent in simulation mode (no hardware required)
simulate:
	cd reference && $(PYTHON) main.py --config ../config/site.example.toml --simulate

## Run simulation comparison framework (3 sites × 3 controllers)
sim:
	$(PYTHON) -m simulation.run

## Run agent in shadow mode (read sensors, don't control)
shadow:
	$(AGENT) --config config/site.toml --shadow

## Run agent in active mode (production)
run:
	$(AGENT) --config config/site.toml

## Run health check
health:
	./scripts/health-check.sh

# =============================================================================
# Deployment — Raspberry Pi
# =============================================================================

## Deploy to connected RPi via SSH (set MICROGRID_HOST=user@host or HOST=ip)
deploy-rpi:
	@echo "Deploying to $(MICROGRID_HOST):$(DEPLOY_PATH)..."
	rsync -avz --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
		--exclude='*.pyc' --exclude='data/' \
		./ $(MICROGRID_HOST):$(DEPLOY_PATH)/
	ssh $(MICROGRID_HOST) "cd $(DEPLOY_PATH) && \
		python3 -m venv .venv && \
		.venv/bin/pip install -e '.[rpi]'"
	@echo "Restarting service..."
	ssh $(MICROGRID_HOST) "sudo systemctl restart $(SERVICE_NAME)"
	@echo "Deploy complete. Check status:"
	@echo "  ssh $(MICROGRID_HOST) sudo systemctl status $(SERVICE_NAME)"

## Install systemd service on RPi (run on the Pi itself)
install-service:
	sudo cp deploy/microgrid-agent.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	@echo "Service installed. Start with: sudo systemctl start $(SERVICE_NAME)"

## Check remote RPi status
status-rpi:
	ssh $(MICROGRID_HOST) "sudo systemctl status $(SERVICE_NAME); echo '---'; uptime; echo '---'; df -h /; echo '---'; free -h"

## View remote RPi logs
logs-rpi:
	ssh $(MICROGRID_HOST) "sudo journalctl -u $(SERVICE_NAME) -n 50 --no-pager"

# =============================================================================
# Docker (for CI and testing without RPi hardware)
# =============================================================================

## Build Docker test container
docker-build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) -f deploy/Dockerfile .

## Run agent in Docker (simulation mode)
docker-run:
	docker run --rm -it \
		-v $(PWD)/config:/app/config:ro \
		-v $(PWD)/data:/app/data \
		-p 8080:8080 \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		--config config/site.example.toml --simulate

## Run tests in Docker
docker-test:
	docker run --rm \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		pytest tests/ -v --tb=short

# =============================================================================
# Control Metalayer
# =============================================================================

## Quick smoke test (tests + kernel compiles)
smoke: test kernel-check

## Full quality check (tests + lint + kernel)
check: test lint kernel-check

## Control audit — verify metalayer compliance
control-audit:
	bash scripts/control/control-audit.sh

## bstack-check — full harness validation
bstack-check:
	bash scripts/control/bstack-check.sh

# =============================================================================
# Maintenance
# =============================================================================

## Clean build artifacts
clean:
	rm -rf __pycache__ reference/src/__pycache__ reference/tests/__pycache__ forecast/__pycache__ simulation/__pycache__ reference/__pycache__
	rm -rf .pytest_cache reference/.pytest_cache .mypy_cache .ruff_cache
	rm -rf *.egg-info dist build
	rm -rf htmlcov .coverage

## Deep clean (removes venv too)
distclean: clean
	rm -rf $(VENV)

# =============================================================================
# Help
# =============================================================================

## Show this help message
help:
	@echo "microgrid-agent — Available targets:"
	@echo ""
	@echo "  Development:"
	@echo "    make install       Install dependencies"
	@echo "    make install-rpi   Install with RPi hardware deps"
	@echo "    make dev           Full dev environment setup"
	@echo ""
	@echo "  Testing:"
	@echo "    make test          Run all tests (Rust + Python)"
	@echo "    make test-rust     Run Rust kernel tests only"
	@echo "    make test-python   Run Python reference tests only"
	@echo "    make test-cov      Run Python tests with coverage"
	@echo "    make lint          Run ruff linter"
	@echo "    make format        Auto-format code"
	@echo "    make typecheck     Run mypy type checker"
	@echo "    make kernel-check  Check Rust kernel compiles"
	@echo "    make kernel-build  Build Rust kernel (release)"
	@echo ""
	@echo "  Running:"
	@echo "    make simulate      Run reference agent in simulation mode"
	@echo "    make sim           Run simulation comparison (3 sites × 3 controllers)"
	@echo "    make shadow        Run in shadow mode (observe only)"
	@echo "    make run           Run in active mode (production)"
	@echo "    make health        Run health check"
	@echo ""
	@echo "  Deployment:"
	@echo "    make deploy-rpi    Deploy to RPi (set MICROGRID_HOST or HOST)"
	@echo "    make install-service  Install systemd service on RPi"
	@echo "    make status-rpi    Check RPi status"
	@echo "    make logs-rpi      View RPi logs"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-build  Build test container"
	@echo "    make docker-run    Run in Docker (simulation)"
	@echo "    make docker-test   Run tests in Docker"
	@echo ""
	@echo "  Control:"
	@echo "    make smoke         Quick smoke test (tests + kernel)"
	@echo "    make check         Full quality check (tests + lint + kernel)"
	@echo "    make control-audit Control metalayer compliance audit"
	@echo "    make bstack-check  Full bstack harness validation"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make clean         Remove build artifacts"
	@echo "    make distclean     Remove artifacts + venv"

.DEFAULT_GOAL := help
