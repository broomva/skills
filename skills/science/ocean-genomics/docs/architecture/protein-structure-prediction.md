# Protein Structure Prediction — From Sequence to 3D Shape

## Why Structure Matters

Proteins are the functional molecules of life. Their 3D shape determines what they do — enzymes catalyze reactions, channels transport molecules, receptors detect signals. Understanding structure is the key to:

1. **Drug discovery**: Design molecules that fit into protein binding sites
2. **Enzyme engineering**: Modify deep-sea extremophile enzymes for industrial use
3. **Functional annotation**: Predict what an unknown protein does based on structural similarity
4. **Evolution**: Understand how organisms adapt to extreme environments (pressure, temperature, pH)

## The Protein Folding Problem

Given a linear amino acid sequence, predict the 3D coordinates of every atom.

- **Why it's hard**: A 100-residue protein has ~10^47 possible conformations (Levinthal's paradox)
- **Why it matters**: Experimental structure determination (X-ray crystallography, cryo-EM) costs $50K-$500K and takes months-years per structure
- **The breakthrough**: AlphaFold 2 (2020) solved it computationally with near-experimental accuracy

## AlphaFold 3

### Overview
- **Developer**: Google DeepMind + Isomorphic Labs
- **Released**: May 2024 (paper), November 2024 (code), February 2025 (weights)
- **License**: Non-commercial (weights require Google approval)
- **Key advance**: Predicts complexes of proteins with DNA, RNA, ligands, ions, and modifications

### Architecture

```
Input: Amino acid sequence(s) + optional DNA/RNA/ligand
    ↓
┌─────────────────────────────────────────┐
│  MSA (Multiple Sequence Alignment)      │
│  Search evolutionary relatives via      │
│  MMseqs2 / JackHMMER against:          │
│  - UniRef90 (protein families)          │
│  - BFD (big fantastic database)         │
│  - Uniclust30                           │
│  Output: co-evolution patterns          │
└───────────────┬─────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  Pairformer                             │
│  (Simplified Evoformer from AF2)        │
│  - Single representation (per residue)  │
│  - Pair representation (residue pairs)  │
│  - Attention over rows + columns        │
│  - Triangular multiplicative updates    │
│  Output: refined pair representations   │
└───────────────┬─────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│  Diffusion Module (NEW in AF3)          │
│  - Starts from random atom cloud        │
│  - Iteratively denoises positions        │
│  - Conditioned on Pairformer output     │
│  - Predicts all atoms simultaneously    │
│  - Multiple samples → confidence ranking│
│  Output: 3D coordinates of all atoms    │
└───────────────┬─────────────────────────┘
                ↓
Output: PDB/mmCIF structure file + confidence scores (pLDDT, PAE)
```

### Confidence Metrics

| Metric | Range | Meaning |
|--------|-------|---------|
| **pLDDT** | 0-100 | Per-residue confidence in position accuracy |
| **PAE** | 0-31.75 Å | Predicted Aligned Error — inter-domain/chain relative position accuracy |
| **pTM** | 0-1 | Predicted Template Modeling score — overall structure quality |
| **ipTM** | 0-1 | Interface pTM — quality of predicted protein-protein or protein-ligand interfaces |

### How to Use

**AlphaFold Server** (free, web): alphafoldserver.com — paste sequence, get structure

**Local CLI** (requires Linux + NVIDIA GPU CC 8.0+, ~1 TB SSD):
```bash
# Clone and set up
git clone https://github.com/google-deepmind/alphafold3.git
cd alphafold3

# Request model weights from Google (form on GitHub README)
# Download genetic databases (~1 TB)

# Input: JSON file
cat > input.json << 'EOF'
{
  "name": "deep_sea_enzyme",
  "sequences": [
    {"protein": {"id": "A", "sequence": "MVLSPADKTNVKAAWGKVGAHAG..."}}
  ],
  "modelSeeds": [1, 2, 3, 4, 5]
}
EOF

# Run prediction
python run_alphafold.py --input_dir=inputs/ --output_dir=outputs/
```

**AlphaFold Database**: alphafold.ebi.ac.uk — 200M+ pre-computed structures (UniProt-aligned)

## Open-Source Alternatives

| Model | License | Developer | Key Features |
|-------|---------|-----------|-------------|
| **OpenFold-3** | MIT | AlQuraishi Lab, Columbia | Bitwise AF3 reproduction, commercial use OK |
| **Boltz-2** | MIT | Independent | Controllability: distance constraints, method conditioning, multi-chain templates |
| **Protenix** | Apache 2.0 | ByteDance | Full AF3 clone, REST API via Neurosnap |
| **Chai-1** | Open | Chai Discovery | Strong on protein-ligand prediction |
| **ColabFold** | MIT | Mirdita/Steinegger | MMseqs2 + AF2/ESMFold, ~1000 structures/day/GPU, Google Colab notebooks |
| **ESMFold** | MIT (via HuggingFace) | Meta FAIR | No MSA needed (single-sequence), 10x faster than AF2, slightly lower accuracy |
| **ABCFold** | Open | Community | Meta-tool: runs AF3 + Boltz-1 + Chai-1 together for comparison |

### Decision Matrix

| Need | Use | Why |
|------|-----|-----|
| Highest accuracy, protein complexes | AlphaFold 3 / OpenFold-3 | Gold standard for multi-chain |
| Fast screening, many sequences | ESMFold | No MSA search = 10x faster |
| Google Colab (no local GPU) | ColabFold | Notebooks ready, free GPU tier |
| Commercial use | OpenFold-3 / Boltz-2 | MIT license |
| Protein-ligand docking | Chai-1 / AF3 | Strong interface prediction |
| Experimental constraints | Boltz-2 | Distance constraints, controllability |
| Quick lookup (known protein) | AlphaFold DB | Pre-computed, instant |

## Deep-Sea Applications

### Extremophile Enzyme Discovery

Deep-sea organisms produce proteins that function under extreme conditions:

| Environment | Conditions | Enzyme Adaptations | Applications |
|-------------|-----------|-------------------|-------------|
| **Hydrothermal vents** | 80-400°C, acidic, H₂S-rich | Thermostable enzymes, disulfide bonds | PCR polymerases, industrial catalysis |
| **Abyssal plains** | 1-4°C, 200-600 atm | Cold-active enzymes, flexible structures | Detergents, food processing |
| **Hadal trenches** | 0-4°C, 600-1100 atm | Piezophilic adaptations, compact folds | High-pressure biotechnology |
| **Cold seeps** | 2-10°C, methane-rich | Methanotrophic enzymes | Bioremediation, carbon capture |

### The Pipeline: eDNA → Structure → Function

```
eDNA metabarcoding / metagenomics
    ↓
Novel gene discovery (no reference match)
    ↓
Translate to protein sequence
    ↓
AlphaFold 3 / ESMFold → predicted 3D structure
    ↓
Structural comparison (Foldseek / DALI) → identify structural homologs
    ↓
Functional annotation from structural similarity
    ↓
Candidate selection for experimental validation
    ↓
Synthetic biology: express, characterize, engineer
```

## Sources

- Jumper J, et al. "Highly accurate protein structure prediction with AlphaFold." Nature 596:583-589, 2021.
- Abramson J, et al. "Accurate structure prediction of biomolecular interactions with AlphaFold 3." Nature 630:493-500, 2024.
- Lin Z, et al. "Evolutionary-scale prediction of atomic-level protein structure with a language model." Science 379:1123-1130, 2023.
- van Kempen M, et al. "Fast and accurate protein structure search with Foldseek." Nature Biotechnology 42:243-246, 2024.
- Zhang C, et al. "Deep-sea enzymes: diversity, function, and biotechnological potential." Marine Drugs 21:82, 2023.
- AlphaFold Protein Structure Database. alphafold.ebi.ac.uk, 2025.
