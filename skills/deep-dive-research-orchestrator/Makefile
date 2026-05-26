.PHONY: smoke check test research-audit control-audit ci

# Fast sanity check - verify agents and dependencies exist
smoke:
	@echo "=== Smoke Check ==="
	@test -f SKILL.md && echo "[PASS] SKILL.md exists" || echo "[FAIL] SKILL.md missing"
	@test -f AGENTS.md && echo "[PASS] AGENTS.md exists" || echo "[FAIL] AGENTS.md missing"
	@test -f CLAUDE.md && echo "[PASS] CLAUDE.md exists" || echo "[FAIL] CLAUDE.md missing"
	@test -f PLANS.md && echo "[PASS] PLANS.md exists" || echo "[FAIL] PLANS.md missing"
	@test -f .claude/agents/research-orchestrator.md && echo "[PASS] research-orchestrator agent exists" || echo "[FAIL] research-orchestrator agent missing"
	@test -f .claude/agents/financial-researcher.md && echo "[PASS] financial-researcher agent exists" || echo "[FAIL] financial-researcher agent missing"
	@test -f .claude/agents/competitive-analyst.md && echo "[PASS] competitive-analyst agent exists" || echo "[FAIL] competitive-analyst agent missing"
	@test -f .claude/agents/market-product-analyst.md && echo "[PASS] market-product-analyst agent exists" || echo "[FAIL] market-product-analyst agent missing"
	@test -f .claude/agents/governance-auditor.md && echo "[PASS] governance-auditor agent exists" || echo "[FAIL] governance-auditor agent missing"
	@echo "=== Smoke Check Complete ==="

# Static quality gates - validate frontmatter and structure
check:
	@echo "=== Static Checks ==="
	@grep -q "^version:" SKILL.md && echo "[PASS] SKILL.md has version" || echo "[FAIL] SKILL.md missing version"
	@grep -q "^context: fork" SKILL.md && echo "[PASS] SKILL.md has context: fork" || echo "[FAIL] SKILL.md missing context: fork"
	@grep -q "^agent:" SKILL.md && echo "[PASS] SKILL.md has agent field" || echo "[FAIL] SKILL.md missing agent field"
	@grep -q "^dependencies:" SKILL.md && echo "[PASS] SKILL.md has dependencies" || echo "[FAIL] SKILL.md missing dependencies"
	@grep -q "financial-deep-research" skills.lock && echo "[PASS] skills.lock has financial-deep-research" || echo "[FAIL] skills.lock missing financial-deep-research"
	@grep -q "competitor-intel" skills.lock && echo "[PASS] skills.lock has competitor-intel" || echo "[FAIL] skills.lock missing competitor-intel"
	@grep -q "app-store-optimization" skills.lock && echo "[PASS] skills.lock has app-store-optimization" || echo "[FAIL] skills.lock missing app-store-optimization"
	@grep -q "agent-control-metalayer-skill" skills.lock && echo "[PASS] skills.lock has agent-control-metalayer-skill" || echo "[FAIL] skills.lock missing agent-control-metalayer-skill"
	@grep -q "harness-engineering-skill" skills.lock && echo "[PASS] skills.lock has harness-engineering-skill" || echo "[FAIL] skills.lock missing harness-engineering-skill"
	@for f in .claude/agents/*.md; do \
		grep -q "^name:" "$$f" && echo "[PASS] $$f has name" || echo "[FAIL] $$f missing name"; \
		grep -q "^description:" "$$f" && echo "[PASS] $$f has description" || echo "[FAIL] $$f missing description"; \
	done
	@echo "=== Static Checks Complete ==="

# Full verification - validate complete skill structure
test: smoke check
	@echo "=== Full Verification ==="
	@echo "Verifying SKILL.md frontmatter fields..."
	@grep -q "allowed-tools:" SKILL.md && echo "[PASS] allowed-tools defined" || echo "[FAIL] allowed-tools missing"
	@echo "Verifying agent-skill alignment..."
	@grep -q "financial-deep-research" .claude/agents/financial-researcher.md && echo "[PASS] financial-researcher references correct skill" || echo "[FAIL] financial-researcher skill mismatch"
	@grep -q "competitor-intel" .claude/agents/competitive-analyst.md && echo "[PASS] competitive-analyst references correct skill" || echo "[FAIL] competitive-analyst skill mismatch"
	@grep -q "app-store-optimization" .claude/agents/market-product-analyst.md && echo "[PASS] market-product-analyst references correct skill" || echo "[FAIL] market-product-analyst skill mismatch"
	@grep -q "agent-control-metalayer-skill" .claude/agents/governance-auditor.md && echo "[PASS] governance-auditor references correct skill" || echo "[FAIL] governance-auditor skill mismatch"
	@echo "=== Full Verification Complete ==="

# Research output audit - validate research quality
research-audit:
	@echo "=== Research Audit ==="
	@echo "Check research outputs for source citations, data freshness, and information gaps."
	@echo "This is a manual review step - invoke governance-auditor agent for automated audit."
	@echo "=== Research Audit Complete ==="

# Governance and compliance check
control-audit:
	@echo "=== Control Audit ==="
	@echo "Verifying governance artifacts..."
	@test -f AGENTS.md && echo "[PASS] AGENTS.md present" || echo "[FAIL] AGENTS.md missing"
	@test -f PLANS.md && echo "[PASS] PLANS.md present" || echo "[FAIL] PLANS.md missing"
	@test -f CLAUDE.md && echo "[PASS] CLAUDE.md present" || echo "[FAIL] CLAUDE.md missing"
	@grep -q "Constraints" AGENTS.md && echo "[PASS] AGENTS.md has constraints" || echo "[FAIL] AGENTS.md missing constraints"
	@grep -q "Escalation" AGENTS.md && echo "[PASS] AGENTS.md has escalation policy" || echo "[FAIL] AGENTS.md missing escalation policy"
	@grep -q "Observability" AGENTS.md && echo "[PASS] AGENTS.md has observability" || echo "[FAIL] AGENTS.md missing observability"
	@grep -q "Control Policy" AGENTS.md && echo "[PASS] AGENTS.md has control policy" || echo "[FAIL] AGENTS.md missing control policy"
	@echo "=== Control Audit Complete ==="

# CI-equivalent local run
ci: smoke check test control-audit
	@echo "=== CI Complete ==="
