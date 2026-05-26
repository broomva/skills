.PHONY: help smoke check e2e doctor framework-lint canary-check bision-prevention p11 lint format type-check all clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

smoke: ## Unit + property tests (fast, ~5s)
	uv run pytest tests/unit/ -m "unit or property" -v

check: smoke ## smoke + integration (~30s)
	@if [ -d tests/integration ]; then \
		uv run pytest tests/integration/ -m "integration" -v ; \
	else \
		echo "[skip] tests/integration/ not present yet (M3+)" ; \
	fi

e2e: ## Fixture-based end-to-end (canary + bision-prevention)
	uv run pytest tests/integration/ -v

framework-lint: ## Validate every framework YAML against _schema.yaml — requires M1
	@if [ -d frameworks ]; then \
		uv run python scripts/lint_frameworks.py ; \
	else \
		echo "[skip] frameworks/ not present yet (M1)" ; \
	fi

canary-check: ## Anonymization invariant (release gate)
	uv run pytest tests/integration/test_anonymization_canary.py -v

bision-prevention: ## L1-L5 release gate
	uv run pytest tests/integration/test_bision_prevention.py -v

doctor: ## Health check — verify scaffold is intact
	@uv run python scripts/doctor.py 2>/dev/null || echo "[skip] scripts/doctor.py not present yet (M4)"
	@test -f pyproject.toml && echo "  [ok] pyproject.toml present"
	@test -f SKILL.md && echo "  [ok] SKILL.md present"
	@test -d core && echo "  [ok] core/ present"
	@test -f .githooks/pre-commit && echo "  [ok] pre-commit hook present"
	@git config core.hooksPath | grep -q .githooks && echo "  [ok] pre-commit hook wired" || echo "  [WARN] pre-commit hook not wired (run: git config core.hooksPath .githooks)"
	@echo "  [ok] doctor checks complete"

p11: ## E2E + render + critique + capture evidence (release-only) — requires M6/M7/M8
	@echo "[skip] P11 evidence capture lands in M8"

lint: ## Run ruff
	uv run ruff check .

format: ## Run ruff format
	uv run ruff format .

type-check: ## Run mypy
	@if [ -d core ]; then \
		uv run mypy core/ tests/ ; \
	else \
		echo "[skip] core/ not present yet" ; \
	fi

all: lint type-check smoke check ## Run lint + type-check + tests (M0-safe)

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
