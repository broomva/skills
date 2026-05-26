# Deep-Dive Research Orchestrator

**Comprehensive multi-dimensional research using coordinated AI specialists**

Conduct professional-grade research on any subject (companies, products, markets, technologies) using coordinated AI research specialists. Synthesizes data from financial, competitive, and product analysis to produce 15,000+ word professional reports with full citations.

## Features

✨ **Multi-Dimensional Analysis**
- Financial & funding analysis
- Competitive intelligence
- Market & product research
- Technology & infrastructure assessment
- Strategic & organizational insights

⏱️ **Fast & Efficient**
- 2-3 hours for comprehensive research
- $0 cost (uses pre-installed skills)
- Parallel multi-agent execution
- Professional quality output

📊 **Professional Reports**
- 15,000-20,000+ words of analysis
- Executive summaries
- Deep-dive sections
- Full source documentation
- 20+ verified references

🎯 **Flexible & Customizable**
- Lightweight to comprehensive scope
- Focus on specific dimensions
- Multiple output formats
- Adapt to any research need

## ⚠️ Required Dependencies

This skill **requires** three dependent skills to function:

| Skill | Purpose | Status | Install |
|-------|---------|--------|---------|
| **financial-deep-research** | Financial analysis & funding | Required | `npx skills add eng0ai/eng0-template-skills@financial-deep-research -g` |
| **competitor-intel** | Competitive intelligence | Required | `npx skills add ognjengt/founder-skills@competitor-intel -g` |
| **app-store-optimization** | Product & market metrics | Required | `npx skills add sickn33/antigravity-awesome-skills@app-store-optimization -g` |
| **agent-control-metalayer-skill** | Governance & policy enforcement | Optional | `npx skills add broomva/agent-control-metalayer-skill -g` |
| **harness-engineering-skill** | Deterministic workflows & safety | Optional | `npx skills add broomva/harness-engineering-skill -g` |

📖 **[See full installation guide →](INSTALLATION.md)**

## Quick Start

### Installation (All-in-One)

```bash
# Install all dependencies + orchestrator skill in one command
npx skills add eng0ai/eng0-template-skills@financial-deep-research ognjengt/founder-skills@competitor-intel sickn33/antigravity-awesome-skills@app-store-optimization broomva/agent-control-metalayer-skill broomva/harness-engineering-skill broomva/deep-dive-research-skill -g -y
```

**Or follow [INSTALLATION.md](INSTALLATION.md) for step-by-step setup**

### Basic Usage

```
Conduct research on [SUBJECT] for [PURPOSE].

Include analysis of:
- Financial metrics
- Competitive positioning
- Market opportunity
- Strategic insights

Generate professional reports with citations.
```

### Research Examples

**Investment Due Diligence:**
```
Research [Company] for Series A investment evaluation.

Analyze: financials, market opportunity, product traction,
team capability, competitive advantages, and key risks.
```

**Market Opportunity:**
```
Market research on [Market/Segment].

Provide: market size and growth, competitive landscape,
customer needs, technology requirements, and barriers to entry.
```

**Competitive Analysis:**
```
Competitive intelligence: How does [Subject] compare to [Alternatives]?

Compare: positioning, technology, pricing, user satisfaction,
market reach, and likely competitive response.
```

**Technology Assessment:**
```
Technical deep-dive on [Subject].

Analyze: technology stack, infrastructure, scalability,
security, performance, and development practices.
```

## What You Get

### Output Package Includes

1. **Executive Summary** - Key findings and conclusions
2. **Financial Analysis** - Funding, revenue, valuation (if applicable)
3. **Market & Competitive** - Position, TAM, benchmarking
4. **Product & User Metrics** - Performance, engagement, satisfaction
5. **Technical Capabilities** - Stack, architecture, infrastructure
6. **Strategic Assessment** - Opportunities, risks, recommendations
7. **Navigation Guide** - How to use the reports

### Quality Standards

- ✅ Minimum 3+ sources per major claim
- ✅ All metrics include source links
- ✅ Data freshness documented
- ✅ Information gaps explicitly noted
- ✅ Professional formatting
- ✅ Methodology transparent

## Use Cases

Perfect for:
- Investment due diligence
- Competitive analysis
- Market research
- Partnership evaluation
- Acquisition assessment
- Strategic planning
- Product strategy
- Technology decisions

## How It Works

The skill runs in an isolated Explore agent context (`context: fork`) with restricted tools for optimal research performance. It coordinates five specialized agents defined in `.claude/agents/`:

```
Research Request
      ↓
┌─────────────────────────────────────────────────┐
│  research-orchestrator (opus)                   │  Coordinates all agents
├─────────────────────────────────────────────────┤
│  financial-researcher (sonnet)                  │  Funding, revenue, valuation
├─────────────────────────────────────────────────┤
│  competitive-analyst (sonnet)                   │  Team, tech, positioning
├─────────────────────────────────────────────────┤
│  market-product-analyst (sonnet)                │  Metrics, TAM, engagement
├─────────────────────────────────────────────────┤
│  governance-auditor (haiku)                     │  Quality & compliance
└─────────────────────────────────────────────────┘
      ↓
Synthesized Professional Reports
```

## Time Breakdown

| Phase | Time |
|-------|------|
| Research Planning | 15 min |
| Specialist Deployment | 30 min |
| Parallel Research | 45 min |
| Synthesis & Analysis | 30 min |
| Report Generation | 15 min |
| **Total** | **2.5 hours** |

## Customization

### Scope Options
- **Lightweight** (1 hour): Quick summary
- **Standard** (2 hours): Comprehensive
- **Deep** (3+ hours): Ultra-detailed

### Focus Areas
- Investment & Financials
- Competitive & Market Position
- Product & User Traction
- Technical & Infrastructure
- Strategic & Partnership
- Organization & Team

### Output Formats
- Markdown (default)
- HTML (presentation)
- JSON (integration)

## Prerequisites

### Required
- Web search access
- Claude Code or compatible agent
- 2-3 hours for research

### Recommended
- Clear research objectives
- Pre-installed skills:
  - financial-deep-research
  - competitor-intel
  - app-store-optimization

## Limitations

Not ideal for:
- Private/bootstrapped subjects (limited data)
- Very early stage subjects (minimal footprint)
- Secretive/stealth mode (restricted info)
- Specialized domains (may need domain skills)
- Real-time data needs (2-3 hour lag)

## Documentation

- **SKILL.md** - Complete skill specification
- **METHODOLOGY.md** - Research workflow details
- **examples/** - Sample research requests
- **docs/** - Additional documentation

## Installation Methods

### Option 1: From Registry (Recommended)
```bash
npx skills add broomva/deep-dive-research-skill -g
```

### Option 2: From GitHub
```bash
npx skills add github:broomva/deep-dive-research-skill -g
```

### Option 3: Local Development
```bash
npx skills add ./deep-dive-research-skill -l
```

## License

MIT License - Free to use, modify, and distribute

## Contributing

Contributions welcome! Open issues or PRs for:
- Bug reports
- Feature requests
- Documentation improvements
- Example research requests
- Enhancement ideas

## Support

- 📖 Check [SKILL.md](SKILL.md) for comprehensive documentation
- 🔍 Review [examples/](examples/) for usage patterns
- 💬 Create an issue for questions or problems
- 📝 Contribute improvements via pull requests

## Author

Created by Claude Code
Built on coordinated AI research specialist framework

---

**Status:** Production Ready ✅
**Version:** 1.1.0
**Last Updated:** February 2025

Ready to research? Install and try it out! 🚀
