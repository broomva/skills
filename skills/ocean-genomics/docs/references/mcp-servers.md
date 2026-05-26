# MCP Servers & Agent Integration for Bioinformatics

## Overview

Model Context Protocol (MCP) servers expose bioinformatics tools as structured, callable functions for AI agents. This enables agentic workflows where Claude (or other LLMs) can directly query genomic databases, run BLAST searches, predict protein structures, and orchestrate analysis pipelines.

## Available MCP Servers

### gget-MCP (Recommended — Highest Coverage)

**Repository**: github.com/longevity-genie/gget-mcp
**Install**: `uvx gget-mcp stdio` or `pip install gget-mcp`

**12 tools exposed:**

| Tool | Function | Example Use |
|------|----------|-------------|
| `gget_search` | Search Ensembl for genes | "Find all CO1 genes in fish" |
| `gget_info` | Gene/transcript metadata | "Get info for BRCA1" |
| `gget_seq` | Fetch DNA/protein sequences | "Get protein sequence for ENSG00000012048" |
| `gget_ref` | Reference genome info | "What assemblies exist for zebrafish?" |
| `gget_blast` | BLAST sequence search | "Find homologs of this deep-sea enzyme" |
| `gget_blat` | BLAT alignment | "Where does this sequence map?" |
| `gget_muscle` | Multiple sequence alignment | "Align these CO1 sequences" |
| `gget_archs4` | Gene expression data | "What tissues express this gene?" |
| `gget_enrichr` | Gene set enrichment | "What pathways are these genes in?" |
| `gget_pdb` | PDB structure retrieval | "Get the structure for 1BNA" |
| `gget_alphafold` | AlphaFold structure prediction | "Predict structure for this sequence" |
| `gget_cosmic` | Cancer mutation database | "Find mutations in TP53" |

**Claude Code configuration:**
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

**Transport modes**: stdio (default), HTTP, SSE

### bio-mcp (Modular Architecture)

**Repository**: github.com/bio-mcp
**Architecture**: One MCP server per tool — compose what you need

| Server | Tools | Purpose |
|--------|-------|---------|
| `bio-mcp-blast` | `blastn`, `blastp`, `blastx`, `tblastn` | NCBI BLAST sequence search |
| `bio-mcp-bwa` | `bwa_mem`, `bwa_index` | Short read alignment |
| `bio-mcp-samtools` | `view`, `sort`, `index`, `flagstat`, `depth`, `coverage` | SAM/BAM manipulation |
| `bio-mcp-seqkit` | `stats`, `grep`, `convert`, `translate` | FASTA/FASTQ manipulation |
| `bio-mcp-bcftools` | `call`, `filter`, `stats`, `view` | Variant calling |
| `bio-mcp-bedtools` | `intersect`, `merge`, `coverage`, `genomecov` | Genome arithmetic |
| `bio-mcp-fastqc` | `fastqc`, `multiqc` | Sequencing quality control |
| `bio-mcp-interpro` | `scan`, `search` | Protein domain analysis |
| `bio-mcp-evo2` | `embed`, `score_variants`, `generate` | Evo 2 DNA language model |
| `bio-mcp-amber` | `minimize`, `dynamics` | Molecular dynamics |
| `bio-mcp-queue` | `submit`, `status`, `results` | Distributed job queue (Redis/Celery/MinIO) |

**All servers**: Python-based, Docker-ready, stdio transport

**Configuration example (multiple servers):**
```json
{
  "mcpServers": {
    "blast": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "bio-mcp/blast:latest"]
    },
    "samtools": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/data:/data", "bio-mcp/samtools:latest"]
    },
    "evo2": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--gpus", "all", "bio-mcp/evo2:latest"]
    }
  }
}
```

### BioinfoMCP (Auto-Generated)

**Paper**: arxiv.org/abs/2510.02139
**Concept**: Automatically generate MCP servers from bioinformatics tool documentation

**38 tools converted** with 94.7% success rate:
- Alignment: Bowtie2, BWA, HISAT2, Minimap2, STAR
- QC: FastQC, fastp, Trim-galore, Trimmomatic, MultiQC, Qualimap
- Variant calling: GATK (4 sub-tools), freebayes
- Assembly: SPAdes, Flye
- Quantification: Salmon, Kallisto
- Manipulation: SAMtools, BEDtools, Cutadapt, Seqtk
- Analysis: MAFFT, MEME, MACS3, Deeptools

**Validated on**: Claude Desktop, Cursor, local AI agents

### CIViC MCP — Clinical Variants

**Paper**: bioRxiv 2025.10.13.682185
**Purpose**: Clinical Interpretation of Variants in Cancer
**Use case**: Query curated variant-disease associations for marine pharmacogenomics

---

## Agent Skills (Claude Code)

### Available from skills.sh

**Tier 1 — High Value:**

| Skill | Source | Install |
|-------|--------|---------|
| AlphaFold workflows | `adaptyvbio/protein-design-skills@alphafold` | `npx skills add adaptyvbio/protein-design-skills@alphafold -g -y` |
| Protein therapeutic design | `mims-harvard/tooluniverse@tooluniverse-protein-therapeutic-design` | `npx skills add mims-harvard/tooluniverse@tooluniverse-protein-therapeutic-design -g -y` |
| Nextflow development | `anthropics/life-sciences@nextflow-development` | `npx skills add anthropics/life-sciences@nextflow-development -g -y` |
| Bioskills suite | `gptomics/bioskills@bioskills` | `npx skills add gptomics/bioskills@bioskills -g -y` |
| gget genomics queries | `davila7/claude-code-templates@gget` | `npx skills add davila7/claude-code-templates@gget -g -y` |

**Tier 2 — Specialized:**

| Skill | Source | Install |
|-------|--------|---------|
| Sequence analysis | `mims-harvard/tooluniverse@tooluniverse-sequence-analysis` | `npx skills add mims-harvard/tooluniverse@tooluniverse-sequence-analysis -g -y` |
| Comparative genomics | `mims-harvard/tooluniverse@tooluniverse-comparative-genomics` | `npx skills add mims-harvard/tooluniverse@tooluniverse-comparative-genomics -g -y` |
| Biopython | `tondevrel/scientific-agent-skills@biopython` | `npx skills add tondevrel/scientific-agent-skills@biopython -g -y` |
| Protein assembly | `letta-ai/skills@protein-assembly` | `npx skills add letta-ai/skills@protein-assembly -g -y` |
| STRING database | `davila7/claude-code-templates@string-database` | `npx skills add davila7/claude-code-templates@string-database -g -y` |
| AlphaFold database | `davila7/claude-code-templates@alphafold-database` | `npx skills add davila7/claude-code-templates@alphafold-database -g -y` |

---

## Programmatic Access (Non-MCP)

### NCBI E-utilities REST API

```bash
# Search
curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nucleotide&term=deep-sea+CO1&retmax=10&retmode=json"

# Fetch
curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nucleotide&id=NM_001301717&rettype=fasta"
```

### BOLD API v4

```bash
# Taxonomy search
curl "https://v4.boldsystems.org/api/v2/taxonomy?taxName=Bathynomus"

# Sequence identification
curl -X POST "https://v4.boldsystems.org/api/v2/identify" \
  -H "Content-Type: application/json" \
  -d '{"sequences": [{"id": "s1", "marker": "COI-5P", "sequence": "ATCG..."}]}'
```

### UniProt REST API

```bash
# Search for deep-sea proteins
curl "https://rest.uniprot.org/uniprotkb/search?query=deep-sea+AND+reviewed:true&format=json&size=10"

# Get protein by ID
curl "https://rest.uniprot.org/uniprotkb/P00520.json"
```

### AlphaFold DB API

```bash
# Get prediction by UniProt ID
curl "https://alphafold.ebi.ac.uk/api/prediction/P00520"

# Download PDB structure
curl -O "https://alphafold.ebi.ac.uk/files/AF-P00520-F1-model_v4.pdb"

# Download confidence scores
curl -O "https://alphafold.ebi.ac.uk/files/AF-P00520-F1-confidence_v4.json"
```

### OBIS API

```bash
# Species occurrence
curl "https://api.obis.org/v3/occurrence?scientificname=Bathynomus%20giganteus&size=10"

# eDNA records
curl "https://api.obis.org/v3/occurrence?dna=true&geometry=POLYGON((-180 -90, 180 -90, 180 90, -180 90, -180 -90))&size=100"
```

---

## Agentic Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT LAYER                                  │
│  Claude Code / AI Agent with MCP clients                        │
│                                                                  │
│  Skills: ocean-genomics, alphafold, bioskills, nextflow-dev     │
│  MCP Clients: gget-mcp, bio-mcp-blast, bio-mcp-evo2           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MCP protocol (stdio/HTTP/SSE)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MCP SERVER LAYER                             │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ gget-mcp │ │ bio-mcp  │ │ bio-mcp  │ │ bio-mcp  │          │
│  │ (12 tools)│ │ -blast   │ │ -samtools│ │ -evo2    │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
└───────┼─────────────┼────────────┼─────────────┼───────────────┘
        │             │            │             │
        ▼             ▼            ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TOOL/DATABASE LAYER                          │
│                                                                  │
│  Ensembl  NCBI  BOLD  PDB  AlphaFold DB  BLAST+  SAMtools      │
│  UniProt  OBIS  DOO   ENA  ESM Atlas     BWA     Evo 2         │
└─────────────────────────────────────────────────────────────────┘
```

### Example Agent Workflow: Novel Deep-Sea Enzyme Discovery

```
User: "Analyze this metagenomic assembly from a hydrothermal vent sample"

Agent steps:
1. gget_blast → Search for homologs in GenBank
2. bio-mcp-evo2 → Score variant effects on novel genes
3. gget_alphafold → Predict structure of unknown proteins
4. gget_enrichr → Pathway enrichment of gene cluster
5. gget_pdb → Find structural homologs for functional annotation
6. Report: Species inventory + novel enzymes + predicted functions
```
