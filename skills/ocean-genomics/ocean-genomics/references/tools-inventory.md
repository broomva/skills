# Computational Biology Tools Inventory

Comprehensive catalog of CLI tools, libraries, and platforms for ocean genomics and bioinformatics workflows.

## Table of Contents

1. [Sequence Search & Alignment](#sequence-search--alignment)
2. [SAM/BAM Processing](#sambam-processing)
3. [Quality Control](#quality-control)
4. [eDNA & Metabarcoding](#edna--metabarcoding)
5. [Metagenomics](#metagenomics)
6. [Genome Assembly](#genome-assembly)
7. [Variant Calling](#variant-calling)
8. [Pipeline Orchestrators](#pipeline-orchestrators)
9. [Protein Structure Prediction](#protein-structure-prediction)
10. [Python Libraries](#python-libraries)
11. [Nanopore Sequencing](#nanopore-sequencing)
12. [Visualization](#visualization)

---

## Sequence Search & Alignment

### BLAST+ (NCBI)

Basic Local Alignment Search Tool — the workhorse of bioinformatics.

| Property | Value |
|----------|-------|
| **Purpose** | Find regions of similarity between biological sequences |
| **Install** | `brew install blast` or `conda install -c bioconda blast` |
| **License** | Public domain |
| **URL** | blast.ncbi.nlm.nih.gov |

**Key commands:**
```bash
# Create a local database
makeblastdb -in sequences.fasta -dbtype nucl -parse_seqids

# Nucleotide-nucleotide search
blastn -query input.fasta -db nt -evalue 1e-6 -outfmt 6 -num_threads 8

# Protein-protein search
blastp -query proteins.fasta -db nr -evalue 1e-10 -outfmt 6

# Translated nucleotide vs protein
blastx -query reads.fasta -db swissprot -evalue 1e-5
```

**Output format 6** (tabular): qseqid, sseqid, pident, length, mismatch, gapopen, qstart, qend, sstart, send, evalue, bitscore

**Cloud-scale**: ElasticBLAST for AWS/GCP — distributes across cloud instances.

**REST API**: `https://blast.ncbi.nlm.nih.gov/Blast.cgi?CMD=Put&PROGRAM=blastn&DATABASE=nt&QUERY=...`

### MMseqs2

Ultra-fast sequence search and clustering — 40-60x faster than BLAST.

| Property | Value |
|----------|-------|
| **Purpose** | Fast homology search, clustering, taxonomy assignment |
| **Install** | `brew install mmseqs2` or `conda install -c bioconda mmseqs2` |
| **License** | GPLv3 |
| **URL** | github.com/soedinglab/MMseqs2 |

```bash
# Create database
mmseqs createdb sequences.fasta targetDB

# Search
mmseqs search queryDB targetDB resultDB tmp --threads 8

# Cluster at 30% identity
mmseqs cluster inputDB clusterDB tmp --min-seq-id 0.3

# Taxonomy assignment
mmseqs taxonomy queryDB targetDB taxDB tmp
```

**Key advantage**: Backend of ColabFold's MSA server. Used by AlphaFold for fast sequence searches.

### BWA / Minimap2

Short-read (BWA) and long-read (Minimap2) aligners.

```bash
# BWA: short read alignment
bwa index reference.fasta
bwa mem -t 8 reference.fasta reads_R1.fq reads_R2.fq | samtools sort -o aligned.bam

# Minimap2: long read alignment
minimap2 -ax map-ont reference.fasta nanopore_reads.fq | samtools sort -o aligned.bam

# Minimap2: assembly-to-assembly
minimap2 -ax asm5 reference.fasta assembly.fasta > aligned.sam
```

---

## SAM/BAM Processing

### SAMtools

| Property | Value |
|----------|-------|
| **Purpose** | Manipulate SAM/BAM/CRAM alignment files |
| **Install** | `brew install samtools` |
| **License** | MIT |
| **URL** | github.com/samtools/samtools |

```bash
# View, sort, index
samtools view -bS input.sam | samtools sort -o sorted.bam
samtools index sorted.bam

# Statistics
samtools flagstat sorted.bam    # alignment summary
samtools idxstats sorted.bam    # per-reference counts
samtools coverage sorted.bam    # coverage statistics

# Depth at each position
samtools depth -a sorted.bam > depth.txt

# Variant calling (simple)
samtools mpileup -uf reference.fasta sorted.bam | bcftools call -mv -Oz -o variants.vcf.gz
```

### BEDtools

```bash
# Intersect features
bedtools intersect -a features.bed -b regions.bed

# Coverage calculation
bedtools genomecov -ibam aligned.bam -g genome.sizes

# Merge overlapping intervals
bedtools merge -i sorted.bed
```

---

## Quality Control

### FastQC

```bash
fastqc input_R1.fq input_R2.fq -o qc_output/ -t 4
```

Produces HTML reports with: per-base quality, GC content, adapter contamination, duplication levels.

### fastp

All-in-one preprocessing: adapter trimming, quality filtering, polyG/polyX trimming, UMI processing.

```bash
fastp -i input_R1.fq -I input_R2.fq -o clean_R1.fq -O clean_R2.fq \
  --detect_adapter_for_pe --thread 8 --html report.html
```

### MultiQC

Aggregate QC reports from multiple tools into one HTML dashboard.

```bash
multiqc qc_output/ -o multiqc_report/
```

---

## eDNA & Metabarcoding

### QIIME2

| Property | Value |
|----------|-------|
| **Purpose** | Complete eDNA/amplicon bioinformatics platform |
| **Install** | `conda install -c qiime2 qiime2` (recommended: dedicated conda env) |
| **License** | BSD-3-Clause |
| **URL** | qiime2.org |

```bash
# Import FASTQ files
qiime tools import --type 'SampleData[PairedEndSequencesWithQuality]' \
  --input-path manifest.tsv --output-path reads.qza \
  --input-format PairedEndFastqManifestPhred33V2

# Denoise with DADA2 → Amplicon Sequence Variants (ASVs)
qiime dada2 denoise-paired --i-demultiplexed-seqs reads.qza \
  --p-trunc-len-f 220 --p-trunc-len-r 200 \
  --o-table table.qza --o-representative-sequences rep-seqs.qza

# Taxonomy classification
qiime feature-classifier classify-sklearn \
  --i-classifier silva-138-99-nb-classifier.qza \
  --i-reads rep-seqs.qza --o-classification taxonomy.qza

# Diversity analysis
qiime diversity core-metrics-phylogenetic \
  --i-phylogeny rooted-tree.qza --i-table table.qza \
  --p-sampling-depth 1000 --output-dir diversity/

# Export results
qiime tools export --input-path taxonomy.qza --output-path taxonomy/
```

**Marker genes supported**: 16S (bacteria), 18S (eukaryotes), CO1 (animals), ITS (fungi)

---

## Metagenomics

### Kraken2

| Property | Value |
|----------|-------|
| **Purpose** | Ultra-fast k-mer-based taxonomic classification |
| **Install** | `brew install kraken2` or `conda install -c bioconda kraken2` |
| **License** | MIT |
| **URL** | ccb.jhu.edu/software/kraken2 |

```bash
# Download standard database
kraken2-build --standard --db standard_kraken2

# Classify reads
kraken2 --db standard_kraken2 --paired reads_R1.fq reads_R2.fq \
  --report report.txt --output classifications.txt --threads 8

# Abundance estimation with Bracken
bracken -d standard_kraken2 -i report.txt -o bracken_output.txt -r 150 -l S
```

### MetaPhlAn4

Taxonomic profiling using clade-specific marker genes.

```bash
metaphlan reads_R1.fq,reads_R2.fq --input_type fastq --nproc 8 \
  -o profiled_communities.txt
```

---

## Genome Assembly

### SPAdes (short reads)

```bash
spades.py -1 reads_R1.fq -2 reads_R2.fq -o assembly_output/ --threads 16 --memory 64
```

### Flye (long reads)

```bash
flye --nano-raw nanopore_reads.fq --out-dir assembly/ --threads 16
```

### QUAST (assembly quality)

```bash
quast assembly/assembly.fasta -o quast_output/ -r reference.fasta
```

---

## Variant Calling

### GATK HaplotypeCaller

```bash
gatk HaplotypeCaller -R reference.fasta -I sorted.bam -O variants.g.vcf -ERC GVCF
gatk GenotypeGVCFs -R reference.fasta -V variants.g.vcf -O genotyped.vcf
```

### bcftools

```bash
bcftools mpileup -f reference.fasta sorted.bam | bcftools call -mv -Oz -o variants.vcf.gz
bcftools stats variants.vcf.gz > stats.txt
bcftools filter -i 'QUAL>30 && DP>10' variants.vcf.gz -o filtered.vcf.gz
```

---

## Pipeline Orchestrators

### Nextflow + nf-core

| Property | Value |
|----------|-------|
| **Purpose** | Dataflow-based bioinformatics pipeline orchestration |
| **Install** | `brew install nextflow` |
| **License** | Apache 2.0 |
| **URL** | nextflow.io, nf-co.re |

**Key nf-core pipelines for ocean genomics:**

| Pipeline | Purpose | Command |
|----------|---------|---------|
| `nf-core/ampliseq` | eDNA metabarcoding (16S, CO1, 18S, ITS) | `nextflow run nf-core/ampliseq --input samplesheet.csv --FW_primer CCHGAYATRGCHTTYCCHCG --RV_primer TCDGGRTGNCCRAARAAYCA` |
| `nf-core/taxprofiler` | Multi-tool metagenomics taxonomy | `nextflow run nf-core/taxprofiler --input samplesheet.csv --databases databases.csv` |
| `nf-core/mag` | Metagenome assembly + binning | `nextflow run nf-core/mag --input samplesheet.csv --assembly_type megahit` |
| `nf-core/proteinfold` | AlphaFold2/ColabFold/ESMFold | `nextflow run nf-core/proteinfold --input sequences.fasta --mode alphafold2` |
| `nf-core/fetchngs` | Download from SRA/ENA | `nextflow run nf-core/fetchngs --input ids.csv` |

### Snakemake

```python
# Snakefile
rule all:
    input: "results/taxonomy.tsv"

rule qc:
    input: "data/{sample}_R1.fq"
    output: "qc/{sample}_R1_trimmed.fq"
    shell: "fastp -i {input} -o {output}"
```

---

## Protein Structure Prediction

### gget (Unified Interface)

| Property | Value |
|----------|-------|
| **Purpose** | One-stop gene/protein queries (Ensembl, UniProt, PDB, BLAST, AlphaFold) |
| **Install** | `pip install gget` |
| **License** | BSD-2-Clause |
| **URL** | github.com/pachterlab/gget |

```python
import gget

# Search for gene info
gget.info("BRCA1", species="human")

# Get protein sequence
gget.seq("ENSG00000012048", translate=True)

# BLAST a sequence
gget.blast("MVLSPADKTNVKAAWGKVGAHAG...")

# Predict structure via AlphaFold
gget.alphafold("MVLSPADKTNVKAAWGKVGAHAG...")

# Get known structure from PDB
gget.pdb("1BNA")

# Gene enrichment analysis
gget.enrichr(["BRCA1", "TP53", "EGFR"], database="KEGG_2021_Human")
```

### ColabFold

```bash
colabfold_batch input.fasta output_dir/ --num-recycle 3 --num-models 5
```

---

## Python Libraries

### Biopython

```python
from Bio import SeqIO, Entrez
from Bio.Blast import NCBIWWW, NCBIXML

# Parse FASTA
for record in SeqIO.parse("sequences.fasta", "fasta"):
    print(record.id, len(record.seq))

# Remote BLAST
result = NCBIWWW.qblast("blastn", "nt", "ATCGATCG...")
records = NCBIXML.parse(result)

# Fetch from NCBI
Entrez.email = "user@example.com"
handle = Entrez.efetch(db="nucleotide", id="NM_001301717", rettype="fasta")
```

### Biotite

```python
import biotite.structure.io.pdb as pdb
import biotite.sequence as seq
import biotite.database.rcsb as rcsb

# Download and parse PDB structure
file = rcsb.fetch("1BNA", "pdb")
structure = pdb.PDBFile.read(file).get_structure()

# Create and manipulate sequences
dna = seq.NucleotideSequence("ATCGATCG")
protein = seq.ProteinSequence("MVLSPADKTNVK")
```

---

## Nanopore Sequencing

### Dorado (Oxford Nanopore Basecaller)

| Property | Value |
|----------|-------|
| **Purpose** | High-performance basecalling from raw nanopore signals |
| **Install** | `brew install nanoporetech/dorado/dorado` |
| **Runs on** | Apple Silicon (M-series), NVIDIA GPUs |
| **License** | ONT Public License |
| **URL** | github.com/nanoporetech/dorado |

```bash
# Basecall POD5 files
dorado basecaller sup pod5_dir/ > calls.bam

# With modified base detection
dorado basecaller sup,5mCG_5hmCG pod5_dir/ > calls.bam

# Duplex basecalling (higher accuracy)
dorado duplex sup pod5_dir/ > duplex_calls.bam

# Demultiplex barcoded samples
dorado demux calls.bam --output-dir demuxed/
```

### MinKNOW

Device control software for Oxford Nanopore sequencers. Integrates Dorado for real-time basecalling during sequencing.

### EPI2ME

Pre-configured analysis workflows:
- `wf-metagenomics` — taxonomic classification from nanopore reads
- `wf-16s` — 16S rRNA amplicon analysis
- `wf-human-variation` — human variant calling

---

## Visualization

### IGV (Integrative Genomics Viewer)

Desktop genome browser for viewing alignments, variants, and annotations.

```bash
igv.sh -g reference.fasta aligned.bam variants.vcf
```

### Krona

Interactive hierarchical taxonomy visualization.

```bash
ktImportTaxonomy kraken2_report.txt -o taxonomy_chart.html
```

### iTOL (Interactive Tree of Life)

Web-based phylogenetic tree visualization: itol.embl.de

---

## Installation Quick Reference

```bash
# macOS (Homebrew + Conda)
brew install blast mmseqs2 samtools minimap2 nextflow

# Conda (bioinformatics channel)
conda create -n bioinfo -c bioconda -c conda-forge \
  fastqc fastp multiqc kraken2 bracken spades flye quast \
  qiime2 bwa gatk4 bcftools bedtools

# Python
pip install biopython biotite gget colabfold

# Nanopore
brew install nanoporetech/dorado/dorado

# Verify installations
blast -version && mmseqs version && samtools --version && nextflow -version
```
