# Ocean Genomics Research

Comprehensive research repository documenting deep-ocean genomics, eDNA metabarcoding, AI-driven protein structure prediction, and the computational biology toolchain for marine biodiversity discovery.

## Purpose

This repository serves as:
1. **Scientific documentation** of ocean genomics methods, tools, and discoveries
2. **Reference architecture** for building agentic bioinformatics workflows
3. **Skill source** for the `ocean-genomics` agent skill
4. **Knowledge base** bridged into the Obsidian vault for cross-session reasoning

## Structure

```
ocean-genomics/
├── docs/
│   ├── architecture/          # System design, pipeline diagrams
│   │   ├── sequencing-pipeline.md
│   │   ├── edna-metabarcoding.md
│   │   ├── protein-structure-prediction.md
│   │   └── ai-genomics-convergence.md
│   ├── references/            # Scientific references, database catalogs
│   │   ├── tools-inventory.md
│   │   ├── marine-databases.md
│   │   ├── foundation-models.md
│   │   └── mcp-servers.md
│   └── conversations/         # Session logs (auto-generated)
├── scripts/                   # Bridge scripts, analysis utilities
├── assets/                    # Diagrams, figures
└── CLAUDE.md                  # This file
```

## Key Topics

- **Molecular Biology Fundamentals**: DNA → RNA → Protein → Structure → Function
- **Sequencing Technologies**: Illumina short reads, Oxford Nanopore long reads, MinION portable
- **eDNA Metabarcoding**: Water sampling → filtration → CO1 amplification → species ID
- **Metagenomics**: Shotgun sequencing of environmental samples for functional + taxonomic profiling
- **Protein Structure Prediction**: AlphaFold 3, ESMFold, OpenFold-3, ColabFold, Boltz-2
- **Foundation Models**: Evo 2 (DNA), ESM-2 (protein), ProGen3 (protein generation)
- **Marine Databases**: OBIS, BOLD, DOO, Tara Oceans, ESM Metagenomic Atlas
- **Pipeline Orchestration**: Nextflow + nf-core, Snakemake, QIIME2
- **MCP Integration**: gget-MCP, bio-mcp, BioinfoMCP

## Conventions

- Scientific accuracy is paramount — cite sources for all claims
- Use SI units and standard bioinformatics notation
- File formats: FASTQ, FASTA, SAM/BAM, VCF, BED/GFF
- Gene names in italics (*CO1*, *16S*), protein names in Roman (AlphaFold, ESM-2)
