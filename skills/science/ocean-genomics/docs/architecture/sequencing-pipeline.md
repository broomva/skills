# DNA Sequencing Pipeline — From Sample to Species

## The Central Dogma of Molecular Biology

All life encodes information in nucleic acids and expresses it through proteins:

```
DNA  ──transcription──▶  mRNA  ──translation──▶  Protein  ──folding──▶  3D Structure  ──▶  Function
 │                         │                        │                      │
 │ 4-letter alphabet       │ Transient copy          │ 20 amino acids       │ Shape = function
 │ A, T, G, C              │ A, U, G, C              │ ~50-2000 residues     │ Lock-and-key
 │ Double helix             │ Single strand            │ Linear chain          │ Enzymes, channels,
 │ ~3.2 Gbp (human)        │ Spliced exons            │ Folds in milliseconds │ structural, signaling
```

### DNA Structure

- **Nucleotides**: Adenine (A), Thymine (T), Guanine (G), Cytosine (C)
- **Base pairing**: A=T (2 hydrogen bonds), G≡C (3 hydrogen bonds)
- **Double helix**: Two antiparallel strands wound around each other
- **Genome size**: Bacteria ~1-10 Mbp, human ~3.2 Gbp, some plants >100 Gbp
- **Genes**: Subsequences encoding proteins (~20,000 in humans, only ~1.5% of genome)
- **Non-coding regions**: Regulatory elements, introns, transposons, structural DNA

### Proteins

- **Amino acids**: 20 standard amino acids, each encoded by 1-6 codons (3-nucleotide triplets)
- **Primary structure**: Linear sequence of amino acids
- **Secondary structure**: Local folding patterns — alpha helices, beta sheets
- **Tertiary structure**: Full 3D fold of a single polypeptide
- **Quaternary structure**: Multi-chain complexes (what AlphaFold 3 now predicts)

## The Sequencing Revolution

### Generation Timeline

| Generation | Technology | Read Length | Throughput | Error Rate | Cost/Gb |
|-----------|-----------|-------------|------------|------------|---------|
| 1st (1977) | Sanger | ~1,000 bp | Low | 0.001% | ~$500,000 |
| 2nd (2005) | Illumina | 75-300 bp | Very high | 0.1% | ~$5-10 |
| 3rd (2014) | PacBio HiFi | 10-25 kbp | Medium | 0.1% (HiFi) | ~$15-20 |
| 3rd (2014) | Oxford Nanopore | 10 kbp-4 Mbp | Medium | 1-5% (raw) | ~$10-20 |

### How Illumina Sequencing Works

1. **Library preparation**: Fragment DNA → attach adapters → amplify on flow cell
2. **Sequencing by synthesis**: Fluorescent nucleotides incorporated one at a time
3. **Imaging**: Camera captures which base was added at each cluster
4. **Base calling**: Convert images → nucleotide sequences + quality scores
5. **Output**: Millions of short reads (FASTQ files)

### How Oxford Nanopore Works

1. **Library preparation**: Attach motor protein + adapter to DNA fragment
2. **Nanopore transit**: DNA thread through protein nanopore in membrane
3. **Current measurement**: Each base modifies ionic current differently
4. **Basecalling**: Neural network (Dorado) converts current signal → sequence
5. **Output**: Long reads (up to megabases), real-time

**Key advantage**: Portable (MinION = 130g, USB-C) — sequencing at sea, in the field

## End-to-End Bioinformatics Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SAMPLE COLLECTION                                │
│  Water, tissue, soil, swab → DNA extraction → quantification         │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LIBRARY PREPARATION                              │
│  Fragment → adapter ligation → size selection → amplification (PCR)  │
│  OR: PCR amplification of marker gene (metabarcoding)                │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SEQUENCING                                       │
│  Illumina (short, accurate) │ Nanopore (long, real-time, portable)  │
│  Output: FASTQ files (reads + Phred quality scores)                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     QUALITY CONTROL                                  │
│  FastQC → assess quality │ fastp/Trimmomatic → trim adapters/low-Q  │
│  Remove duplicates │ Filter by length │ Check contamination          │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              ANALYSIS (branch by objective)                          │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ ALIGNMENT   │  │ ASSEMBLY     │  │ CLASSIFICATION│               │
│  │ BWA/Minimap2│  │ SPAdes/Flye  │  │ Kraken2/QIIME│               │
│  │ → SAM/BAM   │  │ → Contigs    │  │ → Taxa tables │               │
│  │ → Variants  │  │ → Scaffolds  │  │ → Species IDs │               │
│  │ (VCF)       │  │ (FASTA)      │  │ (BIOM)        │               │
│  └─────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

## File Formats Reference

### FASTQ — Raw Sequencing Reads

```
@SEQ_ID_001 length=150
ATCGATCGATCGATCGATCG...
+
IIIIIIIIIIIIIHHHHHFF...
```

- Line 1: `@` + read identifier
- Line 2: Nucleotide sequence
- Line 3: `+` separator
- Line 4: Quality scores (ASCII-encoded Phred+33)
  - `I` = Q40 (99.99% accuracy)
  - `H` = Q39
  - `F` = Q37
  - `!` = Q0 (worst)

### FASTA — Sequences Without Quality

```
>species_name gene=CO1 organism=Bathynomus_giganteus
ATGAATTTTGGAACATGGGCAGGAATAATTGGAACTTCTTT...
```

### SAM/BAM — Sequence Alignments

```
read001  0  chr1  100  60  50M  *  0  0  ATCGATCG...  IIIIIIII...
```

11 mandatory fields: QNAME, FLAG, RNAME, POS, MAPQ, CIGAR, RNEXT, PNEXT, TLEN, SEQ, QUAL

- **SAM**: Human-readable tab-delimited text
- **BAM**: Binary compressed (standard for storage/analysis)
- **CRAM**: Even more compressed (reference-based)

### VCF — Variant Call Format

```
#CHROM  POS   ID   REF  ALT  QUAL  FILTER  INFO
chr1    1000  .    A    G    30    PASS    DP=50;AF=0.25
```

Records positions where the sample differs from the reference genome.

### BED — Genomic Intervals

```
chr1  1000  2000  gene_name  100  +
```

Chromosome, start (0-based), end, optional name/score/strand.

### GFF/GTF — Gene Features

```
chr1  ENSEMBL  gene   1000  2000  .  +  .  gene_id "ENSG001"; gene_name "BRCA1"
```

Annotations of gene models, exons, UTRs, regulatory elements.

## Sequencing Approaches Compared

| Approach | What's Sequenced | Scope | Resolution | Primary Use | Key Tools |
|----------|-----------------|-------|------------|-------------|-----------|
| **Whole Genome Sequencing (WGS)** | All DNA from one organism | Complete genome | Single nucleotide | Reference assembly, variant calling, evolution | BWA, GATK, SAMtools |
| **Metagenomics** | All DNA from environment | Community-wide | Gene/species level | Functional + taxonomic profiling | Kraken2, MetaPhlAn, HUMAnN |
| **Metabarcoding** | Specific marker gene (CO1, 16S, 18S, ITS) via PCR | Community inventory | Species level | Biodiversity surveys, eDNA | QIIME2, DADA2, BOLD |
| **Transcriptomics (RNA-seq)** | mRNA (→ cDNA) | Gene expression | Transcript level | Which genes are active, at what levels | STAR, Salmon, DESeq2 |
| **Epigenomics** | DNA + modifications | Methylation patterns | CpG site level | Gene regulation, development | Bismark, MACS3 |
| **Single-cell sequencing** | Individual cell genomes/transcriptomes | Per-cell resolution | Cell type level | Cell atlas, tumor heterogeneity | CellRanger, Seurat, Scanpy |

## Quality Metrics

| Metric | What It Measures | Good Value | Tool |
|--------|-----------------|------------|------|
| **Phred score (Q)** | Per-base sequencing accuracy | Q30+ (99.9%) | FastQC |
| **N50** | Assembly contiguity (50% of assembly in contigs ≥ this length) | Species-dependent | QUAST |
| **Coverage depth** | Average reads per position | 30x (WGS), 100x+ (variants) | SAMtools |
| **GC content** | Nucleotide composition bias | ~40-60% (most organisms) | FastQC |
| **Duplication rate** | PCR duplicate proportion | <20% | Picard |
| **Mapping rate** | Fraction of reads aligned to reference | >90% | SAMtools flagstat |

## Sources

- Illumina. "An Introduction to Next-Generation Sequencing Technology." 2024.
- Oxford Nanopore Technologies. "Nanopore Sequencing: The Basics." nanoporetech.com.
- Li H, Durbin R. "Fast and accurate short read alignment with Burrows-Wheeler transform." Bioinformatics 25:1754-1760, 2009.
- Bolyen E, et al. "Reproducible, interactive, scalable and extensible microbiome data science using QIIME 2." Nature Biotechnology 37:852-857, 2019.
- Heng Li. "Minimap2: pairwise alignment for nucleotide sequences." Bioinformatics 34:3094-3100, 2018.
