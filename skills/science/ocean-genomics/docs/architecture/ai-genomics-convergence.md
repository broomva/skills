# AI + Genomics Convergence — Foundation Models for Biology

## The Paradigm Shift

Traditional bioinformatics relied on handcrafted algorithms (BLAST, HMMs, phylogenetic trees). The new paradigm: **train neural networks on billions of biological sequences** and let them learn the language of life.

Three scales of biological foundation models:

```
┌─────────────────────────────────────────────────────────────────┐
│  DNA LEVEL                                                       │
│  Model: Evo 2 (Arc Institute + NVIDIA)                          │
│  Scale: 40B params, 9.3T nucleotides, 128K genomes              │
│  Capability: Mutation impact, genome design, regulatory elements │
│  Context: 1M base pairs (entire bacterial genome)                │
│  Architecture: StripedHyena 2 (sub-quadratic, 3x faster)        │
└─────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PROTEIN LEVEL                                                   │
│  Model: ESM-2 (Meta FAIR)                                       │
│  Scale: 15B params, protein sequence universe                    │
│  Capability: Structure prediction, function, embeddings          │
│  Output: ESMFold (3D structure), ESM Atlas (600M+ structures)   │
│  Architecture: Transformer (masked language model)               │
└─────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STRUCTURE LEVEL                                                 │
│  Model: AlphaFold 3 (DeepMind)                                  │
│  Scale: Protein/DNA/RNA/ligand complexes                         │
│  Capability: 3D atomic coordinates, interaction prediction       │
│  Architecture: Pairformer + Diffusion model                      │
│  Database: 200M+ pre-computed structures                         │
└─────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  GENERATION LEVEL                                                │
│  Model: ProGen3 (Profluent Bio)                                  │
│  Scale: 3.4B protein sequences                                   │
│  Capability: Generate novel functional proteins from scratch     │
│  Result: 73% functional (vs 59% natural proteins in same assay) │
│  Architecture: Autoregressive language model                     │
└─────────────────────────────────────────────────────────────────┘
```

## Evo 2 — DNA Foundation Model

### Overview
- **Developer**: Arc Institute + NVIDIA (published Nature, March 2026)
- **Architecture**: StripedHyena 2 — hybrid architecture ~3x faster training than transformers
- **Training data**: 9.3 trillion nucleotides from 128,000 complete genomes (prokaryotes + eukaryotes + phage)
- **Context window**: 1 million base pairs — can process entire bacterial genomes
- **Parameters**: 40 billion
- **License**: Open-source (github.com/ArcInstitute/evo2)

### Capabilities

| Capability | Description | Accuracy |
|-----------|-------------|----------|
| **Variant effect prediction** | Predict pathogenicity of mutations (including BRCA1 variants) | Zero-shot, no fine-tuning needed |
| **Regulatory element prediction** | Identify promoters, enhancers, splice sites from sequence | Competitive with specialized models |
| **Gene essentiality** | Predict which genes are essential for organism survival | High correlation with experimental data |
| **Genome generation** | Design novel bacterial-length genomes from scratch | Functional when synthesized |
| **Phylogenetic awareness** | Understand evolutionary relationships from sequence patterns | Emergent from training |

### Ocean Genomics Applications
- Analyze novel genes from deep-sea metagenomes — predict function without homologs
- Screen environmental DNA for pathogenic mutations in marine organisms
- Predict regulatory elements in extremophile genomes — understand adaptation
- Design synthetic sequences based on deep-sea organism genomes

### Usage
```python
# Install
pip install evo2

# Load model
from evo2 import Evo2
model = Evo2("arc-agi/evo2-40b")

# Predict variant effects
scores = model.score_variants(
    sequence="ATGCGATCG...",
    variants=["A100G", "T200C", "G300A"]
)

# Generate sequence
generated = model.generate(
    prompt="ATGCGATCG",
    max_length=10000,
    temperature=0.7
)
```

## ESM-2 / ESMFold — Protein Language Model

### Overview
- **Developer**: Meta FAIR (Fundamental AI Research)
- **Architecture**: Transformer (masked language model), up to 15B parameters
- **Training**: Protein sequence databases (UniRef, BFD)
- **Output**: Rich per-residue embeddings that encode structure, function, and evolution
- **License**: MIT (via HuggingFace and OpenFold)

### ESMFold — Structure from Sequence Alone
- **Key innovation**: No MSA (Multiple Sequence Alignment) needed — single sequence → 3D structure
- **Speed**: 10x faster than AlphaFold 2 (no database search step)
- **Accuracy**: Slightly below AlphaFold 2/3 for well-studied proteins, competitive for metagenomic proteins
- **Sweet spot**: Rapid screening of millions of metagenomic proteins

### ESM Metagenomic Atlas
- **Scale**: 617 million metagenomic protein structures — the largest structural database ever
- **Source**: Environmental metagenomes (ocean, soil, gut)
- **Significance**: 3x larger than all prior structural databases combined
- **Access**: esmatlas.com

### Why This Matters for Ocean Genomics
When you discover a new protein from deep-sea metagenomics:
1. ESMFold gives you a structure prediction in seconds (vs. hours for AlphaFold)
2. ESM-2 embeddings cluster proteins by function — even without sequence homology
3. ESM Atlas may already contain the structure from a related environmental sample

## ProGen3 — Protein Generation

### Overview
- **Developer**: Profluent Bio (founded by Salesforce Research alumni)
- **Capability**: Generate entirely novel protein sequences that fold and function
- **Result**: 73% of AI-generated proteins were functional in experimental assays (vs. 59% of natural protein variants)
- **Implication**: We can now *design* proteins, not just *predict* existing ones

### Applications to Ocean Genomics
- Generate variants of deep-sea enzymes optimized for industrial conditions
- Design proteins inspired by extremophile adaptations but tailored for specific applications
- Create chimeric proteins combining features from multiple deep-sea organisms

## The Integrated AI-Genomics Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DISCOVERY LAYER                                    │
│                                                                      │
│  eDNA Sampling → Sequencing → Assembly/Classification                │
│  Tools: MinION, QIIME2, Kraken2, Nextflow                          │
│                                                                      │
│  Output: Novel gene sequences, species inventories                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ANALYSIS LAYER                                     │
│                                                                      │
│  Sequence Analysis:                                                  │
│  ├── Evo 2: Variant effects, regulatory elements, gene essentiality │
│  ├── BLAST/MMseqs2: Homology search against known databases          │
│  └── Kraken2: Taxonomic classification                               │
│                                                                      │
│  Structure Prediction:                                               │
│  ├── ESMFold: Fast screening (seconds per protein)                   │
│  ├── AlphaFold 3: High-accuracy complexes (minutes per structure)   │
│  └── Foldseek: Structural similarity search                         │
│                                                                      │
│  Output: Functional annotations, 3D structures, evolutionary context │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                                  │
│                                                                      │
│  Drug Discovery:                                                     │
│  ├── Virtual screening against predicted binding sites               │
│  ├── Marine natural product scaffold identification                  │
│  └── Lead optimization via ProGen3 / directed evolution              │
│                                                                      │
│  Enzyme Engineering:                                                 │
│  ├── Identify extremophile enzymes from metagenomes                  │
│  ├── Predict stability at target conditions (temperature, pH, etc.)  │
│  └── Design optimized variants via protein language models            │
│                                                                      │
│  Conservation:                                                       │
│  ├── Species inventory for marine protected areas                    │
│  ├── Biodiversity monitoring via eDNA time series                    │
│  └── Early warning for invasive species or ecosystem shifts          │
│                                                                      │
│  Output: Drug candidates, engineered enzymes, conservation policy    │
└─────────────────────────────────────────────────────────────────────┘
```

## Emerging Models and Directions

### "AlphaFold 4" (Rumored)
- Isomorphic Labs (DeepMind spinoff) reportedly has a next-generation model
- Nature reported scientists characterizing it as "AlphaFold 4" in early 2026
- Expected: Better small molecule binding, dynamic conformations, drug design

### Multi-Modal Biology Models
- **Geneformer** (Theodoris et al.): Single-cell transcriptome foundation model
- **scGPT**: Generative pre-trained model for single-cell multi-omics
- **CellPLM**: Cell foundation model combining transcriptomics + proteomics

### AI for Conservation
- **BioCLIP**: CLIP-style model for species identification from images
- **eBird + ML**: Bird species detection from audio recordings
- **iNaturalist CV**: Computer vision for species ID from photos
- **eDNA + AI**: Automated species classification from sequencing data

## Sources

- Nguyen E, et al. "Sequence modeling and design from molecular to genome scale with Evo." Nature, 2026.
- Lin Z, et al. "Evolutionary-scale prediction of atomic-level protein structure with a language model." Science 379:1123-1130, 2023.
- Rives A, et al. "Biological structure and function emerge from scaling unsupervised learning to 250 million protein sequences." PNAS 118:e2016239118, 2021.
- Madani A, et al. "Large language models generate functional protein sequences across diverse families." Nature Biotechnology 41:1099-1106, 2023.
- Abramson J, et al. "Accurate structure prediction of biomolecular interactions with AlphaFold 3." Nature 630:493-500, 2024.
- Meta FAIR. "ESM Metagenomic Atlas: 617 million metagenomic protein structures." ai.meta.com, 2022.
- Arc Institute. "Evo 2: A 40-billion-parameter genomic foundation model." arcinstitute.org, 2026.
