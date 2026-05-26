# Installation Guide

## Prerequisites

Before installing the Deep-Dive Research Orchestrator skill, you need to have:

- ✅ Claude Code or compatible agent (Cursor, Cline, Windsurf, etc.)
- ✅ NPX skills CLI available
- ✅ Internet access for skill installation
- ✅ 5-10 minutes for initial setup

## Required Dependencies

The Deep-Dive Research Orchestrator **requires** three skills to function:

### 1. **financial-deep-research**
- **Source:** `eng0ai/eng0-template-skills@financial-deep-research`
- **Purpose:** Financial analysis, funding research, revenue metrics
- **Required:** ✅ Yes

### 2. **competitor-intel**
- **Source:** `ognjengt/founder-skills@competitor-intel`
- **Purpose:** Competitive intelligence, market positioning, tech analysis
- **Required:** ✅ Yes

### 3. **app-store-optimization**
- **Source:** `sickn33/antigravity-awesome-skills@app-store-optimization`
- **Purpose:** App metrics, product analysis, user engagement metrics
- **Required:** ✅ Yes

## Optional Dependencies

These skills enhance governance and reliability but are not required for core research:

### 4. **agent-control-metalayer-skill**
- **Source:** `broomva/agent-control-metalayer-skill`
- **Purpose:** Governance framework, policy enforcement, audit trails
- **Required:** ❌ Optional (enhances governance)

### 5. **harness-engineering-skill**
- **Source:** `broomva/harness-engineering-skill`
- **Purpose:** Deterministic workflows, test harness validation, safety checks
- **Required:** ❌ Optional (enhances reliability)

## Installation Methods

### Method 1: Quick Install (Recommended) ⚡

Install all dependencies + skill in one command:

```bash
# Install all dependencies (required + optional) and the orchestrator skill
npx skills add eng0ai/eng0-template-skills@financial-deep-research ognjengt/founder-skills@competitor-intel sickn33/antigravity-awesome-skills@app-store-optimization broomva/agent-control-metalayer-skill broomva/harness-engineering-skill broomva/deep-dive-research-skill -g -y
```

**Time:** ~2 minutes
**Result:** Full setup ready to use

### Method 2: Step-by-Step Installation

Install each dependency separately:

```bash
# Step 1: Install financial analysis skill (required)
npx skills add eng0ai/eng0-template-skills@financial-deep-research -g -y

# Step 2: Install competitive intelligence skill (required)
npx skills add ognjengt/founder-skills@competitor-intel -g -y

# Step 3: Install product analysis skill (required)
npx skills add sickn33/antigravity-awesome-skills@app-store-optimization -g -y

# Step 4: Install governance framework (optional)
npx skills add broomva/agent-control-metalayer-skill -g -y

# Step 5: Install harness engineering (optional)
npx skills add broomva/harness-engineering-skill -g -y

# Step 6: Install the orchestrator skill
npx skills add broomva/deep-dive-research-skill -g -y
```

**Time:** ~5 minutes
**Result:** Full setup with feedback after each step

### Method 3: Local Testing

Test locally before global installation:

```bash
# Clone the repository
git clone https://github.com/broomva/deep-dive-research-skill
cd deep-dive-research-skill

# Install dependencies globally
npx skills add eng0ai/eng0-template-skills@financial-deep-research -g
npx skills add ognjengt/founder-skills@competitor-intel -g
npx skills add sickn33/antigravity-awesome-skills@app-store-optimization -g

# Install orchestrator locally
npx skills add . -l
```

**Time:** ~5-10 minutes
**Result:** Local testing setup

## Verification

After installation, verify all skills are properly installed:

```bash
# Check installed skills
npx skills list

# Or look for these in the list:
# - financial-deep-research
# - competitor-intel
# - app-store-optimization
# - deep-dive-research-skill (or orchestrator skill name)
```

## Troubleshooting

### Skill Not Found Error

**Error:** `Skill not found`

**Solution:**
1. Verify NPX is updated: `npx -v`
2. Check skill name spelling
3. Try re-installing: `npx skills add ... --force`
4. Check GitHub organization and repo name

### Installation Fails

**Error:** `Installation failed`

**Solution:**
1. Ensure internet connection is active
2. Verify GitHub repository is public
3. Check your Node.js version (14+)
4. Try installing to local directory first (`-l` flag)

### Skill Not Appearing in Claude Code

**Error:** Installed skill not showing up

**Solution:**
1. Restart Claude Code or your editor
2. Verify global installation: `npx skills list -g`
3. Check installation location: `~/.agents/skills/`
4. Re-run installation with `-g` flag

### Dependencies Not Found

**Error:** Orchestrator says required skills are missing

**Solution:**
1. Install each dependency: See Method 2 above
2. Verify each skill installed: `npx skills list | grep -E "(financial|competitor|optimization)`
3. Use one-liner installation: See Method 1 above

### Port/Access Issues

**Error:** Connection or access errors

**Solution:**
1. Check internet connection
2. Verify firewall allows NPX
3. Try on different network if available
4. Check GitHub status page

## Uninstallation

To remove all skills:

```bash
# Remove individual skills
npx skills remove financial-deep-research
npx skills remove competitor-intel
npx skills remove app-store-optimization
npx skills remove deep-dive-research-skill
```

Or remove all locally installed skills:

```bash
# WARNING: This removes ALL locally installed skills
rm -rf ~/.agents/skills/
```

## Updating

To update to newer versions:

```bash
# Re-install (will update if newer version available)
npx skills add broomva/deep-dive-research-skill -g -y

# Or update all skills
npx skills update
```

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Node.js | 14.0.0 | 18.0.0+ |
| NPX | 6.0.0 | 9.0.0+ |
| Disk Space | 100 MB | 500 MB |
| RAM | 2 GB | 4 GB+ |
| Internet | Yes | Yes |

## Skills.lock File

The `skills.lock` file (in this repo) documents:
- All required dependencies
- Installation commands
- Dependency versions
- Installation status tracking

Use this for reference or integration with other systems.

## After Installation

Once installed, you're ready to use the skill:

1. Open Claude Code (or your agent)
2. Make a research request:
   ```
   Research [Subject] using the Deep-Dive Research Orchestrator.

   Include: [research dimensions]
   Generate: professional reports with citations
   ```
3. The skill will coordinate all three specialist skills automatically
4. Receive comprehensive reports in 2-3 hours

## Getting Help

If you encounter issues:

1. **Check documentation:** [README.md](README.md), [SKILL.md](SKILL.md)
2. **Review examples:** [examples/](examples/RESEARCH_REQUESTS.md)
3. **Check methodology:** [METHODOLOGY.md](METHODOLOGY.md)
4. **Open an issue:** [GitHub Issues](https://github.com/broomva/deep-dive-research-skill/issues)

## Security & Privacy

- ✅ All skills use public information only
- ✅ No sensitive data storage
- ✅ No credentials required
- ✅ Local execution
- ✅ Open source and auditable

## Next Steps

After successful installation:

1. Read [SKILL.md](SKILL.md) to understand capabilities
2. Review [examples/RESEARCH_REQUESTS.md](examples/) for sample requests
3. Make your first research request
4. Get comprehensive analysis reports

---

**Installation Guide Version:** 1.1
**Last Updated:** February 2025
