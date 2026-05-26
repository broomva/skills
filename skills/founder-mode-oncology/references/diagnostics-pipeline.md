# Diagnostics Pipeline — Open-Source Bioinformatics Toolchain

## Table of Contents
- [End-to-End Pipeline](#end-to-end-pipeline)
- [Step 1: Alignment](#step-1-alignment)
- [Step 2: Variant Calling](#step-2-variant-calling)
- [Step 3: Copy Number Analysis](#step-3-copy-number-analysis)
- [Step 4: Single-Cell Analysis](#step-4-single-cell-analysis)
- [Step 5: Gene Set Enrichment](#step-5-gene-set-enrichment)
- [Step 6: Neoantigen Prediction](#step-6-neoantigen-prediction)
- [Step 7: Vaccine Design](#step-7-vaccine-design)
- [Step 8: Visualization](#step-8-visualization)

---

## End-to-End Pipeline

```
FASTQ (WGS/WES/RNA-seq/scRNA-seq)
  │
  ├─ DNA ──→ BWA align ──→ GATK process ──→ Mutect2 + Strelka2 (variants)
  │                                      └──→ ASCAT (copy number)
  │
  ├─ RNA ──→ STAR align ──→ featureCounts/HTSeq (quantification)
  │                      └──→ Limma/DESeq2 (differential expression + GSEA)
  │
  ├─ scRNA ─→ Cell Ranger ──→ Scanpy/Seurat (clustering, DE, target discovery)
  │
  └─ Variants + HLA ──→ pVACseq (neoantigen prediction)
                      └──→ MHCflurry (MHC binding)
                      └──→ Vaxrank (candidate ranking)
                      └──→ pVACvector (peptide vaccine design)
                      └──→ LinearDesign (mRNA optimization)
```

## Step 1: Alignment

**DNA alignment — BWA**
- Repo: https://github.com/lh3/bwa
- Command: `bwa mem -t 16 ref.fa tumor_R1.fq.gz tumor_R2.fq.gz | samtools sort -o tumor.bam`
- Reference: GRCh38 (or GRCh37+decoy for OpenVax pipeline compatibility)

**RNA alignment — STAR**
- Repo: https://github.com/alexdobin/STAR
- Two-pass alignment recommended for novel junction discovery
- Command: `STAR --genomeDir ref --readFilesIn R1.fq.gz R2.fq.gz --outSAMtype BAM SortedByCoordinate`

## Step 2: Variant Calling

**GATK Mutect2** (primary somatic caller)
- Repo: https://github.com/broadinstitute/gatk
- Pipeline: MarkDuplicates → BaseRecalibration → Mutect2 (tumor/normal paired)
- Output: VCF with somatic SNVs and indels
- Filter: `FilterMutectCalls` for quality control

**Strelka2** (validation caller)
- Repo: https://github.com/Illumina/strelka
- Run as secondary caller; intersect with Mutect2 for high-confidence calls

## Step 3: Copy Number Analysis

**ASCAT** (Allele-Specific Copy number Analysis of Tumours)
- Repo: https://github.com/VanLoo-lab/ascat
- Convenience wrapper: https://github.com/CompEpigen/ezASCAT
- Input: Tumor/normal BAMs from WGS
- Output: Allele-specific copy number segments, ploidy, purity estimates
- Use at multiple timepoints to track clonal evolution

## Step 4: Single-Cell Analysis

**Cell Ranger** (10x Genomics processing)
- Download: https://www.10xgenomics.com/support/software/cell-ranger
- Processes 10x Chromium scRNA-seq FASTQ → gene expression matrix
- Output: Filtered feature-barcode matrix (H5/MTX)

**Scanpy** (Python) or **Seurat** (R) — downstream analysis
- Scanpy: https://github.com/scverse/scanpy
- Seurat: https://github.com/satijalab/seurat

Standard workflow:
1. Quality control (filter doublets, dead cells)
2. Normalization + highly variable gene selection
3. PCA → UMAP/t-SNE dimensionality reduction
4. Clustering (Leiden/Louvain)
5. Differential expression per cluster
6. Cell type annotation
7. **Target discovery**: Identify surface proteins overexpressed on tumor clusters but not normal tissue (FAP, B7H3, EphA2, etc.)

**Critical**: This is where non-obvious targets are discovered. Standard genomics misses transcriptomic targets.

## Step 5: Gene Set Enrichment

**Limma** (R/Bioconductor)
- Linear models for differential expression
- `limma::camera()` for competitive GSEA

**DESeq2** (R/Bioconductor)
- Negative binomial model for count data
- Use with `fgsea` for preranked GSEA

Gene set databases: MSigDB (Hallmark, C2, C5), Reactome, KEGG

## Step 6: Neoantigen Prediction

**pVACtools** (Griffith Lab, Washington University)
- Repo: https://github.com/griffithlab/pVACtools
- Components:
  - `pVACseq`: Predict neoantigens from somatic mutations + HLA type
  - `pVACbind`: Predict binding from peptide sequences
  - `pVACvector`: Design optimal vaccine peptide sequences

**MHCflurry** (OpenVax, Mount Sinai)
- Repo: https://github.com/openvax/mhcflurry
- Neural network MHC-I peptide binding prediction
- More accurate than older methods (NetMHC)

**Vaxrank** (OpenVax)
- Repo: https://github.com/openvax/vaxrank
- Integrates variant calls + RNA expression + MHC binding → ranked vaccine candidates
- Prioritizes by: binding affinity, expression level, variant allele frequency

**Input requirements:**
- Somatic VCF (from Mutect2/Strelka2)
- RNA-seq BAM (for expression verification)
- HLA typing (Class I alleles) — from `OptiType` or clinical HLA typing

## Step 7: Vaccine Design

**Peptide vaccines:**
- pVACvector arranges selected neoantigens into optimal peptide sequence
- Minimizes junctional epitopes (false neoepitopes at peptide junctions)

**mRNA vaccines:**
- LinearDesign (Stanford): Optimize mRNA sequence for stable secondary structure
- Codon optimization for translation efficiency
- Add structural elements: 5' cap, 5' UTR, signal peptide, poly-A tail

**Physical production** (from OpenVaxx guide):
1. DNA synthesis (BioXp, ~$600)
2. In vitro transcription (T7 polymerase, ~$2K)
3. LNP formulation (microfluidic mixing, ~$500)
4. QC (DLS particle sizing, ~$100)
- Total: ~$4.2K in-house per patient

## Step 8: Visualization

**IGV** (Integrative Genomics Viewer)
- Repo: https://github.com/igvteam/igv
- Web version: https://github.com/igvteam/igv.js
- Browse WGS, WES, RNA-seq, scRNA-seq BAMs in context

**UCSC Genome Browser** — public track hubs for comparison

---

## Hardware Requirements

| Step | RAM | CPU | Disk | Time |
|------|-----|-----|------|------|
| BWA alignment (WGS) | 32GB | 16 cores | 500GB | 4-8h |
| Mutect2 | 16GB | 8 cores | 50GB | 2-6h |
| ASCAT | 8GB | 4 cores | 10GB | 1h |
| Cell Ranger | 64GB | 16 cores | 500GB | 4-12h |
| Scanpy analysis | 32GB | 8 cores | 50GB | 1-2h |
| pVACseq | 16GB | 8 cores | 10GB | 1-4h |

Total pipeline: ~24-48h on a 16-core machine with 64GB RAM.
