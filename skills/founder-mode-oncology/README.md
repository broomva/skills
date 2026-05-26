# Founder Mode Oncology

> Personalized cancer treatment navigation — maximal diagnostics, parallel therapy, therapeutic development, structure-based protein design.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Install with skills.sh](https://img.shields.io/badge/skills.sh-install-blue)](https://skills.sh)

## What This Skill Does

An agent skill that encodes a systematic framework for navigating personalized cancer treatment, generalized from [Sid Sijbrandij's osteosarcoma case](https://centuryofbio.com/p/sid) (2022--2026). It transforms the ad-hoc "billionaire with a team" approach into a reproducible methodology using open-source tools and structured decision-making.

For full skill content and clinical detail, see [SKILL.md](SKILL.md).

## Quick Install

```bash
npx skills add broomva/founder-mode-oncology
```

## Supported Agents

This skill works with any agent that supports the skills.sh format:

- **Claude Code** (Anthropic)
- **Cursor**
- **Codex** (OpenAI)
- **Gemini CLI** (Google)
- **Windsurf**
- **Amp**
- Any agent compatible with `SKILL.md` conventions

## Skill Structure

```
founder-mode-oncology/
├── SKILL.md                              # Main skill file (agent-readable)
├── references/
│   ├── diagnostics-pipeline.md           # Open-source bioinformatics toolchain
│   ├── treatment-categories.md           # Treatment modalities and combination rationale
│   ├── regulatory-access.md              # FDA expanded access and IRB navigation
│   ├── mrd-monitoring.md                 # Liquid biopsy interpretation
│   ├── structural-biology.md             # AlphaFold, RFdiffusion, ProteinMPNN pipelines
│   └── open-source-tools.md              # GitHub repos and analysis tools
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

## The Three Pillars

### 1. Maximal Diagnostics

Run every available diagnostic modality -- WGS, WES, RNA-seq, scRNA-seq, liquid biopsy, organoid drug testing, novel PET tracers -- to build a complete molecular picture. Standard clinical panels miss non-obvious targets; scRNA-seq in the reference case revealed FAP overexpression invisible to gene panels.

### 2. Personalized Therapeutic Development

Use diagnostic findings to design patient-specific treatments spanning checkpoint inhibitors, neoantigen vaccines, oncolytic viruses, cell therapies, radioligand therapy, and immune modulators. Access experimental drugs via FDA expanded access (Form 3926, typically approved within 48 hours).

### 3. Parallel Treatment

Run compatible therapies simultaneously rather than sequentially. Monitor with ctDNA every 2--4 weeks and serial scRNA-seq monthly to measure response in real time and adapt. The reference case achieved a T-cell infiltration shift from 19% to 89% in the tumor microenvironment.

## Key Links

- **Open patient data (25 TB)**: [osteosarc.com](https://osteosarc.com)
- **Source article**: [centuryofbio.com/p/sid](https://centuryofbio.com/p/sid) -- "Going Founder Mode on Cancer" by Elliot Hershberg
- **Venture fund scaling personalized oncology**: [evenone.ventures](https://evenone.ventures)
- **Research repository**: [github.com/broomva/founder-mode-cancer](https://github.com/broomva/founder-mode-cancer)

## Contributing

Contributions are welcome -- especially corrections from clinicians, researchers, and patients. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on improving references, adding treatment modalities, and submitting corrections.

## License

[MIT](LICENSE) -- Carlos D. Escobar-Valbuena ([@broomva](https://github.com/broomva)), 2026.
