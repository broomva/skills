# Ocean Genomics

Comprehensive research repository and agent skill for deep-ocean genomics, eDNA metabarcoding, AI-driven protein structure prediction, and marine biodiversity discovery.

## Install as Agent Skill

```bash
npx skills add broomva/ocean-genomics@ocean-genomics -g -y
```

This installs the `ocean-genomics` skill into Claude Code, Cursor, Codex, Gemini CLI, and 30+ other AI agents.

**Browse on skills.sh:** [skills.sh/broomva/ocean-genomics](https://skills.sh/broomva/ocean-genomics)

## What the Skill Provides

Four agentic workflows for computational biology:

| Workflow | Input | Output |
|----------|-------|--------|
| **eDNA Species Inventory** | FASTQ amplicon data | Species list, diversity metrics, novel species flags |
| **Metagenomic Profiling** | Shotgun FASTQ data | Taxonomic profiles, functional pathways, MAGs |
| **Novel Protein Characterization** | Protein sequences (FASTA) | 3D structures, functional annotations, enzyme candidates |
| **Variant Effect Analysis** | DNA sequences + variants | Pathogenicity scores, structural impact, conservation |

Plus reference docs for 30+ CLI tools, 15 marine databases, 9 foundation models, and 4 MCP servers.

## Quick Start

### 1. Install the Skill

```bash
npx skills add broomva/ocean-genomics@ocean-genomics -g -y
```

### 2. Install Companion Skills

```bash
npx skills add adaptyvbio/protein-design-skills@alphafold -g -y
npx skills add anthropics/life-sciences@nextflow-development -g -y
npx skills add gptomics/bioskills@bioskills -g -y
npx skills add davila7/claude-code-templates@gget -g -y
npx skills add mims-harvard/tooluniverse@tooluniverse-protein-therapeutic-design -g -y
```

### 3. Set Up MCP Integration (Optional)

Add to your `.claude/settings.json` for direct BLAST, AlphaFold, and sequence queries:

```json
{
  "mcpServers": {
    "gget-mcp": {
      "command": "uvx",
      "args": ["--from", "gget-mcp@latest", "stdio"]
    }
  }
}
```

### 4. Install CLI Tools

```bash
# Core bioinformatics
brew install blast mmseqs2 samtools minimap2 nextflow

# Python libraries
pip install biopython biotite gget

# Nanopore basecalling (Apple Silicon)
brew install nanoporetech/dorado/dorado

# eDNA pipeline
conda create -n edna -c bioconda -c conda-forge qiime2 kraken2 fastp fastqc
```

## Repository Structure

```
ocean-genomics/
├── ocean-genomics/              # Agent skill (installable via npx skills)
│   ├── SKILL.md                 # Skill definition + 4 core workflows
│   └── references/              # Progressive-disclosure reference docs
│       ├── tools-inventory.md   #   30+ CLI tools with commands
│       ├── marine-databases.md  #   15 databases with API patterns
│       ├── foundation-models.md #   Evo 2, ESM-2, AlphaFold 3, ProGen3
│       └── mcp-integration.md   #   gget-MCP, bio-mcp, BioinfoMCP
│
├── docs/                        # Scientific documentation
│   ├── architecture/            # Deep technical docs
│   │   ├── sequencing-pipeline.md
│   │   ├── edna-metabarcoding.md
│   │   ├── protein-structure-prediction.md
│   │   └── ai-genomics-convergence.md
│   └── references/              # Reference catalogs
│       ├── tools-inventory.md
│       ├── marine-databases.md
│       ├── foundation-models.md
│       └── mcp-servers.md
│
├── scripts/                     # Automation
│   ├── conversation-history.py  # Knowledge graph bridge
│   └── conversation-bridge-hook.sh
│
├── LICENSE                      # MIT
├── README.md
└── CLAUDE.md                    # Agent instructions
```

## Documentation

### Architecture Docs

- **[Sequencing Pipeline](docs/architecture/sequencing-pipeline.md)** -- Central dogma, sequencing generations (Sanger to Nanopore), end-to-end bioinformatics pipeline, file formats (FASTQ/FASTA/SAM/BAM/VCF), quality metrics
- **[eDNA Metabarcoding](docs/architecture/edna-metabarcoding.md)** -- 7-step eDNA pipeline from field sampling to species inventory, deep-sea challenges, Ocean Census, NOAA, Tara Oceans programs
- **[Protein Structure Prediction](docs/architecture/protein-structure-prediction.md)** -- AlphaFold 3 architecture, confidence metrics, open alternatives (OpenFold-3, Boltz-2, ColabFold, ESMFold), extremophile enzyme applications
- **[AI + Genomics Convergence](docs/architecture/ai-genomics-convergence.md)** -- Foundation model stack (Evo 2, ESM-2, AlphaFold 3, ProGen3), integrated discovery-to-application pipeline

### Reference Docs

- **[Tools Inventory](docs/references/tools-inventory.md)** -- 30+ CLI tools: BLAST+, MMseqs2, SAMtools, QIIME2, Kraken2, Nextflow, Dorado, gget, ColabFold, BWA, Minimap2, and more
- **[Marine Databases](docs/references/marine-databases.md)** -- OBIS, BOLD, DOO, Tara Oceans, GenBank, UniProt, AlphaFold DB, ESM Atlas, WoRMS, Copernicus, GEBCO
- **[Foundation Models](docs/references/foundation-models.md)** -- Evo 2, ESM-2/ESMFold, AlphaFold 3, OpenFold-3, Boltz-2, ColabFold, ProGen3: specs, code, compute requirements
- **[MCP Servers](docs/references/mcp-servers.md)** -- gget-MCP (12 tools), bio-mcp (11 modules), BioinfoMCP (38 auto-generated tools), agent workflow architecture

## Key Topics

| Domain | What's Covered |
|--------|---------------|
| Molecular Biology | DNA, RNA, protein, central dogma, gene structure |
| Sequencing | Illumina short reads, Oxford Nanopore long reads, MinION portable |
| eDNA | Water sampling, filtration, CO1 amplification, species identification |
| Metagenomics | Shotgun sequencing, taxonomic/functional profiling, MAG assembly |
| Structure Prediction | AlphaFold 3, ESMFold, ColabFold, OpenFold-3, Boltz-2, Foldseek |
| Foundation Models | Evo 2 (DNA, 40B), ESM-2 (protein, 15B), ProGen3 (protein generation) |
| Marine Databases | OBIS, BOLD, DOO, Tara Oceans, ESM Metagenomic Atlas |
| Pipeline Tools | Nextflow + nf-core, QIIME2, Kraken2, BLAST+, MMseqs2 |
| Agent Integration | MCP servers, Claude Code skills, agentic bioinformatics workflows |

## Contributing

Contributions welcome. Please ensure scientific accuracy and cite sources for all claims.

## License

[MIT](LICENSE)
