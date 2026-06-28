# Biological Foundation Models — Technical Reference

## Model Comparison Matrix

| Model | Developer | Parameters | Training Data | Input | Output | License |
|-------|-----------|-----------|--------------|-------|--------|---------|
| **Evo 2** | Arc Institute + NVIDIA | 40B | 9.3T nucleotides, 128K genomes | DNA sequence | Embeddings, variants, generation | Open source |
| **ESM-2** | Meta FAIR | 15B | UniRef protein sequences | Protein sequence | Embeddings, contacts | MIT |
| **ESMFold** | Meta FAIR | Based on ESM-2 | Protein sequences | Protein sequence | 3D structure (PDB) | MIT |
| **AlphaFold 3** | DeepMind | N/A | PDB + evolution | Protein/DNA/RNA/ligand | 3D structure + confidence | Non-commercial |
| **OpenFold-3** | AlQuraishi Lab | AF3 reproduction | Same as AF3 | Same as AF3 | Same as AF3 | MIT |
| **Boltz-2** | Independent | AF3-class | PDB + evolution | Protein + constraints | 3D structure (controllable) | MIT |
| **Protenix** | ByteDance | AF3 clone | Same as AF3 | Same as AF3 | Same as AF3 | Apache 2.0 |
| **ColabFold** | Mirdita/Steinegger | AF2 + ESMFold | MMseqs2 MSAs | Protein sequence | 3D structure | MIT |
| **ProGen3** | Profluent Bio | Billions | 3.4B protein sequences | Prompt/conditioning | Novel protein sequences | Proprietary |

## Evo 2 — DNA Foundation Model

- **Architecture**: StripedHyena 2 — hybrid state-space + attention, sub-quadratic, ~3x faster than transformers
- **Context**: 1 million base pairs (entire bacterial genome)
- **Variants**: 7B and 40B parameter versions
- **Published**: Nature, March 2026
- **Source**: github.com/ArcInstitute/evo2

### Capabilities

| Task | How | Accuracy |
|------|-----|----------|
| Pathogenic variant prediction | Zero-shot scoring | AUROC 0.90+ on ClinVar |
| BRCA1 variant classification | Zero-shot | Near-clinical accuracy |
| Gene essentiality | Likelihood scoring | r=0.85+ vs experimental |
| Regulatory element prediction | Embedding analysis | Competitive with specialized models |
| Genome generation | Autoregressive sampling | Functional when synthesized |

### Usage

```python
from evo2 import Evo2

model = Evo2("arc-agi/evo2-7b")  # Single A100

# Score variants
scores = model.score_variants(
    sequence="ATGCGATCG...",
    variants=[{"position": 100, "ref": "A", "alt": "G"}]
)

# Generate DNA
generated = model.generate(prompt="ATGCGATCG", max_length=10000, temperature=0.7)

# Embeddings
embeddings = model.embed("ATGCGATCG...")
```

## ESM-2 / ESMFold — Protein Language Model

- **ESM-2**: Masked language model for proteins, sizes from 8M to 15B params
- **ESMFold**: End-to-end structure prediction — no MSA needed, 10x faster than AF2
- **ESM Atlas**: 617M+ metagenomic protein structures at esmatlas.com
- **Source**: github.com/facebookresearch/esm

### Usage

```python
import torch, esm

# ESM-2 embeddings
model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
batch_converter = alphabet.get_batch_converter()

data = [("protein1", "MVLSPADKTNVK...")]
_, _, batch_tokens = batch_converter(data)

with torch.no_grad():
    results = model(batch_tokens, repr_layers=[33])
embeddings = results["representations"][33]

# ESMFold structure prediction
fold_model = esm.pretrained.esmfold_v1()

with torch.no_grad():
    pdb_string = fold_model.infer_pdb("MVLSPADKTNVK...")

with open("prediction.pdb", "w") as f:
    f.write(pdb_string)
```

## AlphaFold 3 — Multi-Molecular Structure Prediction

- **Architecture**: Pairformer (simplified Evoformer) + Diffusion model
- **Input**: JSON with protein/DNA/RNA/ligand sequences
- **Confidence**: pLDDT (per-residue), PAE (inter-domain), pTM/ipTM (overall/interface)
- **Requirements**: Linux, NVIDIA GPU CC 8.0+, ~1 TB SSD for genetic databases
- **Database**: 200M+ structures at alphafold.ebi.ac.uk

### Input Format

```json
{
  "name": "prediction",
  "sequences": [
    {"protein": {"id": "A", "sequence": "MVLSPADKTNVK..."}},
    {"dna": {"id": "B", "sequence": "ATCGATCG"}},
    {"ligand": {"id": "C", "ccdCodes": ["ATP"]}}
  ],
  "modelSeeds": [1, 2, 3, 4, 5]
}
```

### Open Alternatives (Permissive Licenses)

| Model | License | Best For |
|-------|---------|----------|
| **OpenFold-3** (MIT) | Commercial use, AF3 reproduction | Production pipelines |
| **Boltz-2** (MIT) | Controllability, experimental constraints | Research with distance constraints |
| **Protenix** (Apache 2.0) | Cloud API via Neurosnap | Quick predictions without local setup |
| **ColabFold** (MIT) | Batch predictions, free GPU | Google Colab notebooks, ~1000/day |

## Compute Requirements

| Model | GPU | RAM | Storage | Speed |
|-------|-----|-----|---------|-------|
| ESMFold | 1x A100 40GB | 32 GB | Minimal | Seconds |
| ColabFold | Free Colab | Minimal | Minimal | 1-5 min |
| AlphaFold 3 | 1x A100 80GB | 64 GB | ~1 TB | 5-30 min |
| Evo 2 (7B) | 1x A100 80GB | 64 GB | ~15 GB | Seconds |
| Evo 2 (40B) | 4x A100 80GB | 256 GB | ~80 GB | Seconds |

## Decision Matrix

| Need | Use | Why |
|------|-----|-----|
| DNA variant effects | Evo 2 | Zero-shot, cross-species |
| Fast protein structure | ESMFold | No MSA, seconds per prediction |
| High-accuracy complexes | AlphaFold 3 / OpenFold-3 | Gold standard multi-chain |
| Batch structure screening | ColabFold | Free GPU, 1000/day |
| Structural homolog search | Foldseek | Finds function from shape |
| Novel protein design | ProGen3 | 73% functional rate |
| Commercial deployment | OpenFold-3 / Boltz-2 | MIT license |
