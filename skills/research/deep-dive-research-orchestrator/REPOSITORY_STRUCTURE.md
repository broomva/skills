# Repository Structure

## File Organization

```
deep-dive-research-orchestrator/
│
├── 📄 README.md
│   └── Main documentation, quick start, features
│
├── 📄 SKILL.md ⭐ [CORE FILE]
│   └── Complete skill specification with metadata
│   └── Used by skills registry
│   └── Defines all capabilities and dependencies
│
├── 📄 INSTALLATION.md
│   └── Step-by-step installation guide
│   └── Dependency information
│   └── Troubleshooting guide
│   └── System requirements
│
├── 📄 METHODOLOGY.md
│   └── Research workflow details
│   └── How specialists coordinate
│   └── Quality assurance standards
│   └── Research dimensions
│
├── 📄 CONTRIBUTING.md
│   └── How to contribute
│   └── Areas for contribution
│   └── Code of conduct
│
├── 📄 LICENSE
│   └── MIT License
│
├── 📄 package.json
│   └── NPM package metadata
│   └── Dependencies and scripts
│
├── 📄 skills.lock
│   └── Dependencies lock file
│   └── Installation commands
│   └── Status tracking
│
├── 📄 REPOSITORY_STRUCTURE.md
│   └── This file
│
├── 📁 examples/
│   └── RESEARCH_REQUESTS.md
│       ├── Investment due diligence examples
│       ├── Competitive analysis examples
│       ├── Market research examples
│       ├── Partnership evaluation examples
│       ├── Technology assessment examples
│       ├── And 5+ more example use cases
│
├── 📁 docs/ (future)
│   └── Additional documentation
│   └── Advanced usage guides
│   └── API documentation
│
├── .gitignore
│   └── Git ignore rules
│
└── README files linked in README:
    ├── [SKILL.md](SKILL.md) - Capabilities
    ├── [INSTALLATION.md](INSTALLATION.md) - Setup
    ├── [METHODOLOGY.md](METHODOLOGY.md) - How it works
    ├── [CONTRIBUTING.md](CONTRIBUTING.md) - Contribute
```

## Key Files Explained

### SKILL.md ⭐ (Core)
**What it is:** The skill specification that defines everything about the skill
**Used by:** Skills registry (skills.sh), skill discovery tools, Claude Code
**Contains:**
- YAML metadata (title, description, dependencies, tags)
- Capability descriptions
- Usage examples
- Risk assessment
- Quality standards

**Do not modify:** Unless updating skill capabilities

### README.md
**What it is:** Main entry point and overview
**Read by:** Users discovering the skill
**Contains:**
- Feature summary
- Quick start instructions
- Use cases
- Installation links

**Update when:** Adding major features or changing core functionality

### INSTALLATION.md
**What it is:** Complete installation and dependency guide
**Read by:** Users setting up the skill
**Contains:**
- Prerequisites
- Required dependencies (all 3 listed)
- Installation methods (3 different approaches)
- Verification steps
- Troubleshooting guide
- Uninstall instructions

**Update when:** Installation process changes or new dependencies added

### METHODOLOGY.md
**What it is:** Deep explanation of how the research works
**Read by:** Users wanting to understand the process
**Contains:**
- Research workflow phases
- The 3 specialist agents explained
- Research dimensions covered
- Quality assurance approach
- Customization options
- Best practices

**Update when:** Research methodology changes

### skills.lock
**What it is:** Machine-readable dependency specification
**Used by:** CI/CD, automated setup, dependency tracking
**Contains:**
- All required dependencies with versions
- Installation commands
- Metadata about the skill
- Status tracking

**Update when:** Dependencies change or versions update

### examples/RESEARCH_REQUESTS.md
**What it is:** Real-world examples of how to use the skill
**Read by:** Users learning by example
**Contains:**
- Investment due diligence examples
- Competitive analysis examples
- Market research examples
- Partnership evaluation examples
- Technology assessment examples
- And 5+ more use cases
- Tips for getting best results

**Update when:** Adding new use cases or improving examples

### package.json
**What it is:** NPM/Node.js package metadata
**Used by:** NPM registry, package managers
**Contains:**
- Package name and version
- Keywords for discoverability
- Repository links
- License info
- File list

**Update when:** Publishing new version or changing metadata

## Content Categories

### For Decision Makers
- Start with: **README.md** (5 min)
- Then: **SKILL.md** overview section (10 min)
- Result: Understand what the skill does

### For Users Getting Started
- Start with: **README.md** (5 min)
- Then: **INSTALLATION.md** (10 min)
- Then: **examples/RESEARCH_REQUESTS.md** (15 min)
- Result: Ready to use the skill

### For Users Doing Research
- Reference: **SKILL.md** (how to use)
- Reference: **METHODOLOGY.md** (how it works)
- Reference: **examples/RESEARCH_REQUESTS.md** (real examples)
- Result: Effective research requests

### For Contributors
- Read: **CONTRIBUTING.md** (how to contribute)
- Review: **METHODOLOGY.md** (understand system)
- Reference: **examples/RESEARCH_REQUESTS.md** (usage patterns)
- Result: Ready to improve the skill

### For System Integrators
- Read: **skills.lock** (dependencies)
- Read: **INSTALLATION.md** (setup)
- Read: **package.json** (package info)
- Result: Can integrate into CI/CD

## Dependency Documentation

### Dependencies Listed In:

1. **SKILL.md** (metadata section)
   ```yaml
   dependencies:
     - financial-deep-research
     - competitor-intel
     - app-store-optimization
   ```

2. **skills.lock** (detailed specs)
   - Full source URLs
   - Purpose of each dependency
   - Installation commands
   - Status tracking

3. **INSTALLATION.md** (setup guide)
   - Why each dependency is needed
   - How to install each one
   - Verification steps
   - Troubleshooting for each

4. **README.md** (quick reference)
   - Table of dependencies
   - Link to full installation guide

## No Research Output Files

**Intentional design decision:** This repository contains ONLY the skill definition.

**Why:**
- Skill should be generic and reusable
- Research outputs are project-specific
- Repository stays focused and clean
- Easier to maintain and update

**Research examples:**
- Are described in `examples/RESEARCH_REQUESTS.md`
- Not included as actual output files
- Users generate their own outputs

## Version Information

**Current Version:** 1.0.0
**Release Date:** February 2025
**Status:** Production Ready

**Version bumping:**
- Update in: SKILL.md frontmatter
- Update in: package.json
- Update in: skills.lock
- Commit with: `git tag v1.x.x`

## Updates & Maintenance

### Check for Updates
```bash
npx skills check
```

### File Update Frequency
- **SKILL.md**: When capabilities change (rare)
- **README.md**: When major features added
- **INSTALLATION.md**: When dependencies change
- **METHODOLOGY.md**: When process changes
- **examples/**: When new use cases discovered
- **package.json**: For version bumps

### Deprecation Process
1. Announce in README
2. Document in METHODOLOGY.md
3. Update examples
4. Major version bump
5. Sunset timeline

## Links & Navigation

**From README.md:**
- `[SKILL.md](SKILL.md)` - Full capabilities
- `[INSTALLATION.md](INSTALLATION.md)` - Setup guide
- `[METHODOLOGY.md](METHODOLOGY.md)` - How it works
- `[CONTRIBUTING.md](CONTRIBUTING.md)` - How to contribute

**From SKILL.md:**
- References examples (see them in this repo)
- Links to quality standards

**From INSTALLATION.md:**
- Links to SKILL.md for capabilities
- Links to examples for usage

**From examples:**
- References SKILL.md for full documentation
- References METHODOLOGY.md for process

---

## File Statistics

| File | Lines | Purpose |
|------|-------|---------|
| SKILL.md | 400+ | Skill specification |
| README.md | 150+ | Overview & quick start |
| INSTALLATION.md | 250+ | Setup guide |
| METHODOLOGY.md | 400+ | Research methodology |
| examples/ | 300+ | Usage examples |
| CONTRIBUTING.md | 100+ | Contribution guide |
| skills.lock | 50+ | Dependency specs |
| package.json | 40+ | Package metadata |
| **Total** | **1,690+** | **Complete skill** |

---

## Repository Goals

✅ **Clear & Organized**
- Each file has single purpose
- Logical organization
- Easy to navigate

✅ **Comprehensive**
- Covers all aspects
- Examples for all use cases
- Complete documentation

✅ **Maintainable**
- Version-controlled
- Update guidelines
- Deprecation process

✅ **Community-Friendly**
- Contributing guide
- Issue templates
- Pull request process

---

**Repository Structure Version:** 1.0
**Last Updated:** February 2025
