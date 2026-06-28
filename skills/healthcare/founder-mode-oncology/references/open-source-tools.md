# Open-Source Tools for Personalized Oncology

## Table of Contents
- [Neoantigen Vaccine Pipelines](#neoantigen-vaccine-pipelines)
- [Genomics & Variant Calling](#genomics--variant-calling)
- [Single-Cell Analysis](#single-cell-analysis)
- [Copy Number & Structural Variants](#copy-number--structural-variants)
- [MHC Binding Prediction](#mhc-binding-prediction)
- [RNA-seq & Expression Analysis](#rna-seq--expression-analysis)
- [Visualization & Browsers](#visualization--browsers)
- [mRNA Vaccine Synthesis Guide](#mrna-vaccine-synthesis-guide)
- [Osteosarcoma-Specific Repos](#osteosarcoma-specific-repos)

---

## Neoantigen Vaccine Pipelines

### openvax/neoantigen-vaccine-pipeline
- **URL**: https://github.com/openvax/neoantigen-vaccine-pipeline
- **Stars**: 90 | **Language**: Python
- **Status**: Used in 2 Phase I clinical trials (NCT02721043, NCT03223103)
- **What it does**: End-to-end pipeline from FASTQ to ranked vaccine peptide candidates
- **Pipeline**: BWA align → GATK process → Mutect2/Strelka variant call → Vaxrank ranking
- **Requirements**: 16+ cores, 32GB RAM, ~500GB disk, tumor/normal WES + RNA-seq + HLA typing
- **Docker available**: Yes (recommended deployment)

### griffithlab/pVACtools
- **URL**: https://github.com/griffithlab/pVACtools
- **Stars**: 300+ | **Language**: Python
- **What it does**: Suite of tools for personalized variant antigen prediction
- **Components**:
  - `pVACseq`: Predict neoantigens from somatic mutations
  - `pVACbind`: Predict binding from peptide sequences
  - `pVACvector`: Design optimal vaccine peptide order (minimizes junctional epitopes)
  - `pVACview`: Visualization of neoantigen candidates
- **Input**: Annotated VCF + HLA alleles
- **Documentation**: https://pvactools.readthedocs.io/

### openvax/vaxrank
- **URL**: https://github.com/openvax/vaxrank
- **Language**: Python
- **What it does**: Ranks vaccine peptide candidates by integrating variant calls + RNA expression + MHC binding
- **Prioritization criteria**: Binding affinity, expression level, variant allele frequency

---

## Genomics & Variant Calling

### broadinstitute/gatk
- **URL**: https://github.com/broadinstitute/gatk
- **What it does**: Industry-standard variant calling toolkit
- **Key tools**: Mutect2 (somatic), HaplotypeCaller (germline), MarkDuplicates, BQSR
- **Best practices**: https://gatk.broadinstitute.org/hc/en-us/sections/360007226651-Best-Practices-Workflows

### Illumina/strelka
- **URL**: https://github.com/Illumina/strelka
- **What it does**: Fast somatic SNV/indel caller (validation against Mutect2)

### lh3/bwa
- **URL**: https://github.com/lh3/bwa
- **What it does**: DNA read alignment to reference genome (GRCh38)

### samtools/samtools
- **URL**: https://github.com/samtools/samtools
- **What it does**: BAM/CRAM file manipulation, sorting, indexing, statistics

### broadinstitute/picard
- **URL**: https://github.com/broadinstitute/picard
- **What it does**: BAM utilities (duplicate marking, metrics collection)

---

## Single-Cell Analysis

### 10x Genomics Cell Ranger
- **URL**: https://www.10xgenomics.com/support/software/cell-ranger
- **License**: Free download (proprietary)
- **What it does**: Process 10x Chromium scRNA-seq raw data → gene expression matrix

### scverse/scanpy
- **URL**: https://github.com/scverse/scanpy
- **Stars**: 2,000+ | **Language**: Python
- **What it does**: Full scRNA-seq analysis: QC, normalization, clustering, DE, visualization

### satijalab/seurat
- **URL**: https://github.com/satijalab/seurat
- **Stars**: 2,500+ | **Language**: R
- **What it does**: Same as Scanpy but in R ecosystem. Industry standard.

### scverse/anndata
- **URL**: https://github.com/scverse/anndata
- **What it does**: Data structure for single-cell data (the `.h5ad` format)

### scverse/scvi-tools
- **URL**: https://github.com/scverse/scvi-tools
- **What it does**: Deep learning for single-cell analysis (batch correction, imputation)

---

## Copy Number & Structural Variants

### VanLoo-lab/ascat
- **URL**: https://github.com/VanLoo-lab/ascat
- **What it does**: Allele-specific copy number analysis from WGS/WES
- **Output**: Segments with allele-specific copy number, tumor purity, ploidy

### CompEpigen/ezASCAT
- **URL**: https://github.com/CompEpigen/ezASCAT
- **Stars**: 12 | **Language**: R
- **What it does**: Convenient ASCAT wrapper for BAM input

### dellytools/delly
- **URL**: https://github.com/dellytools/delly
- **What it does**: Structural variant discovery (deletions, duplications, inversions, translocations)

---

## MHC Binding Prediction

### openvax/mhcflurry
- **URL**: https://github.com/openvax/mhcflurry
- **Stars**: 200+ | **Language**: Python
- **What it does**: Neural network MHC-I peptide binding prediction
- **Advantage**: Open-source alternative to NetMHC (which has license restrictions)

### IEDB Analysis Tools
- **URL**: http://tools.iedb.org/
- **What it does**: Comprehensive immune epitope prediction (free web interface)
- **Includes**: MHC-I binding, MHC-II binding, T cell epitope prediction, B cell epitope prediction

### OptiType
- **URL**: https://github.com/FRED-2/OptiType
- **What it does**: HLA typing from sequencing data (needed as input for neoantigen prediction)

---

## RNA-seq & Expression Analysis

### alexdobin/STAR
- **URL**: https://github.com/alexdobin/STAR
- **What it does**: RNA-seq alignment (splicing-aware)

### subread/featureCounts
- **URL**: https://github.com/ShiLab-Bioinformatics/subread
- **What it does**: Read quantification against gene annotations

### DESeq2 (Bioconductor)
- **URL**: https://bioconductor.org/packages/DESeq2/
- **What it does**: Differential expression analysis + GSEA

### Limma (Bioconductor)
- **URL**: https://bioconductor.org/packages/limma/
- **What it does**: Linear models for microarray/RNA-seq differential expression

### subinoy/fgsea
- **URL**: https://github.com/ctlab/fgsea
- **What it does**: Fast preranked gene set enrichment analysis

---

## Visualization & Browsers

### igvteam/igv
- **URL**: https://github.com/igvteam/igv
- **What it does**: Desktop genome browser for BAM/VCF/BED visualization

### igvteam/igv.js
- **URL**: https://github.com/igvteam/igv.js
- **What it does**: Web-embedded genome browser (used on osteosarc.com)

---

## mRNA Vaccine Synthesis Guide

### philfung/openvaxx
- **URL**: https://github.com/philfung/openvaxx
- **Stars**: 67 | **Language**: JavaScript (interactive guide)
- **What it does**: Complete open-source guide: sequencing → mutation detection → AI target selection → mRNA synthesis → LNP formulation → QC
- **Interactive guide**: https://philfung.github.io/openvaxx/

**8-Step Pipeline Summary**:
1. Genomic sequencing ($1K-$2.5K)
2. Mutation detection (GATK Mutect2)
3. AI target selection (pVACseq + MHCflurry)
4. Sequence optimization (pVACvector + LinearDesign)
5. DNA synthesis (BioXp, $600)
6. mRNA transcription ($2K)
7. LNP formulation ($500)
8. Quality assurance ($100)

**Total**: ~$4.2K in-house, ~$13.4K outsourced per patient
**Timeline**: 4-6 weeks biopsy to vial
**Equipment capital**: $500K-$800K for in-house lab

---

## Osteosarcoma-Specific Repos

| Repo | Stars | Description |
|------|-------|-------------|
| cortes-ciriano-lab/osteosarcoma_evolution | 4 | Genome complexity and evolution mechanisms |
| MSKCC-Computational-Pathology/DMMN-osteosarcoma | 6 | MSKCC computational pathology deep learning |
| dyammons/canine_osteosarcoma_atlas | 3 | Canine osteosarcoma scRNA-seq atlas |
| zhengxj1/A-Single-Cell-and-Spatially-Resolved-Atlas-of-Human-Osteosarcomas | 3 | Human osteosarcoma single-cell atlas |
| sulevk/OsteosarcomaFFPEdeconvolution | 0 | scRNA-seq deconvolution from FFPE samples |

---

## Open Data Reference

**Sid Sijbrandij's dataset**: 25TB on Google Cloud (publicly readable)
- **Portal**: https://osteosarc.com
- **Contents**: WGS, WES, RNA-seq, scRNA-seq, ONT long-read, spatial transcriptomics, H&E, IHC, HLA typing
- **Contact**: cancer@sytse.com
