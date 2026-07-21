# Biological Foundation Models — Technical Reference

## Model Comparison Matrix

| Model | Developer | Parameters | Training Data | Input | Output | License |
|-------|-----------|-----------|--------------|-------|--------|---------|
| **Evo 2** | Arc Institute + NVIDIA | 40B | 9.3T nucleotides, 128K genomes | DNA sequence | Embeddings, variants, generation | Open source |
| **ESMC** | Biohub | 6B (also 300M/600M) | Billions of protein sequences | Protein sequence | Embeddings, logits, SAE features | MIT |
| **ESMFold2** | Biohub | Built on frozen ESMC 6B | PDB + MSA (optional) | Protein/DNA/RNA/ligand/modified AA | All-atom 3D + pLDDT/pAE/pTM/ipTM | MIT |
| **ESM-2** *(legacy)* | Meta FAIR | 15B | UniRef protein sequences | Protein sequence | Embeddings, contacts | MIT |
| **ESMFold** *(legacy)* | Meta FAIR | Based on ESM-2 | Protein sequences | Protein sequence | 3D structure (PDB) | MIT |
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

## ESMC / ESMFold2 — Protein Language Model (current generation)

> **Lineage note.** Stewardship of the ESM line ran Meta FAIR → EvolutionaryScale →
> **Chan Zuckerberg Biohub**. `github.com/evolutionaryscale/esm` now redirects to
> `github.com/Biohub/esm` (same repo id — a transfer, not a fork), and `LICENSE.md` carries
> Chan Zuckerberg Biohub copyright. The original `github.com/facebookresearch/esm` was
> **archived 2024-02-07** and should not be used for new work.
>
> The *corporate* relationship is *not* established: the preprint's competing-interest statement
> reads "a subset of the authors performed portions of this work while at **EvolutionaryScale, PBC
> and / or CZ Biohub**", treating them as distinct entities. Treat this as a repo/stewardship
> transfer of unknown corporate form — not a confirmed rename or acquisition.

- **ESMC**: protein LM at 300M / 600M / **6B** params; 6B has 80 layers, 2.37e23 training FLOPs.
  Positioned as a new scaling frontier relative to ESM-2 for long-range structural understanding.
- **ESMFold2**: structure prediction trained on a **frozen ESMC 6B** + a **diffusion** structure
  head. All-atom output. Unlike ESMFold, it predicts **all biomolecules** — small molecules, DNA,
  RNA, and modified amino acids. Optional MSA input; single-sequence mode for large speedup.
- **ESM Atlas (Biohub, current)**: **6.8B proteins**, >1B predicted structures, at
  `biohub.ai/esm/protein/atlas`. Organized by ESMC's internal representation space (SAE features),
  not by sequence similarity.
- **ESM Metagenomic Atlas (Meta AI, legacy — still live)**: 617M metagenomic structures at
  `esmatlas.com`. **Not superseded** — it remains a distinct, separately-hosted resource, and its
  metagenomic focus makes it directly relevant to environmental/eDNA work. Use both.
- **ESMC SAEs**: sparse autoencoders over ESMC activations (reference:
  `ESMC-6B-sae-layer60-k64-codebook16384`, ~16k features) with agent-generated natural-language
  feature descriptions. See `../../../knowledge/` KG entity `tool/esm-biohub-world-model`.
- **Source**: `github.com/Biohub/esm` · weights on HF under `biohub/`

### Licensing (changed 2026-05-27 — verify before citing older guidance)

The repo relicensed from the Cambrian matrix (ESM-3 Open and ESM C 600M weights were
**non-commercial**; ESM C 6B was **API-only**) to plain **MIT**, Chan Zuckerberg Biohub
copyright, at commit `c94ed8d7`. ESMC 6B, ESMFold2, and the SAEs are now MIT open weights.

⚠️ GitHub's license detector reports `NOASSERTION` for the repo because the MIT text lives in
`LICENSE.md` behind a bold header. HF cards tag `[mit, other]`, where `other` resolves to
`THIRD_PARTY_NOTICE.md` — **dependency** licenses (flash-attn BSD, PyTorch BSD, einops MIT),
not a restriction on the weights. Automated license scans will misreport this repo.

### Usage — ESMC embeddings (current)

```python
import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer

model = AutoModelForMaskedLM.from_pretrained("biohub/ESMC-6B", device_map="auto").eval()
tokenizer = AutoTokenizer.from_pretrained("biohub/ESMC-6B")

inputs = tokenizer(["MVLSPADKTNVK..."], return_tensors="pt", padding=True)
inputs = {k: v.to(model.device) for k, v in inputs.items()}
with torch.inference_mode():
    output = model(**inputs, output_hidden_states=True)  # all layers
```

### Usage — ESMFold2 all-atom structure (protein + DNA + ligand)

```python
from esm.models.esmfold2 import (
    DNAInput, ESMFold2InputBuilder, LigandInput,
    Modification, ProteinInput, StructurePredictionInput,
)
from transformers.models.esmfold2.modeling_esmfold2 import ESMFold2Model

model = ESMFold2Model.from_pretrained("biohub/ESMFold2").cuda().eval()

spi = StructurePredictionInput(sequences=[
    ProteinInput(id="A", sequence="MIEIKDKQLTGLRFIDLFAGLGGFRLALE..."),
    DNAInput(id="B", sequence="GATAGCGCTATC",
             modifications=[Modification(position=5, ccd="C36")]),
    LigandInput(id="L", ccd=["SAH"]),
])

result = ESMFold2InputBuilder().fold(
    model, spi, num_loops=20, num_sampling_steps=100, num_diffusion_samples=1, seed=0
)
print(f"pLDDT {float(result.plddt.mean()):.3f}  pTM {float(result.ptm):.3f}  ipTM {float(result.iptm):.3f}")
with open("pred.cif", "w") as f:
    f.write(result.complex.to_mmcif())
```

> AMD ROCm users: ROCm 6.4 with PyTorch 2.9+.

### Legacy ESM-2 / ESMFold (still valid, no longer the frontier)

```python
import torch, esm

model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()   # ESM-2 embeddings
fold_model = esm.pretrained.esmfold_v1()                  # ESMFold structure
with torch.no_grad():
    pdb_string = fold_model.infer_pdb("MVLSPADKTNVK...")
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
| **ESMFold2** (MIT) | Commercial use, all-atom incl. DNA/RNA/ligand/modified AA | Broadest biomolecule coverage; single-sequence mode for speed |
| **OpenFold-3** (MIT) | Commercial use, AF3 reproduction | Production pipelines |
| **Boltz-2** (MIT) | Controllability, experimental constraints | Research with distance constraints |
| **Protenix** (Apache 2.0) | Cloud API via Neurosnap | Quick predictions without local setup |
| **ColabFold** (MIT) | Batch predictions, free GPU | Google Colab notebooks, ~1000/day |

> **ESMFold2 vs AlphaFold 3 — what actually holds (verified 2026-07-21).**
> Biohub's README claims ESMFold2 "matches or exceeds AlphaFold3 **across diverse evaluation
> datasets**." An adversarial check against the preprint and the independent FoldBench leaderboard
> found that claim **partially supported** — the task-specific wins are real, the sweeping version
> is not:
>
> | FoldBench task | AF3 (independent leaderboard) | ESMFold2 (preprint, MSA) | |
> |---|---|---|---|
> | Protein-protein | 72.93% | **76% ± 1** | ESMFold2 ✅ |
> | Antibody-antigen | 47.90% | **53% ± 2** | ESMFold2 ✅ |
> | Protein-ligand | **64.90%** | 61% ± 1 | AlphaFold 3 ✅ |
> | Protein-DNA | 79.18% | 79% ± 1 | tie |
>
> Points **in favor** of the numbers: the authors ran AF3 from official released code, and their
> AF3 results reproduce the independent Fudan-maintained FoldBench leaderboard to within ~1 point
> — the baseline was not sandbagged. Training cutoff (2021-09-30) is *more* conservative than
> FoldBench requires, unlike Boltz-2/RosettaFold3 which FoldBench flags for possible leakage.
>
> Points **against**: every number was produced in-house (ESMFold2 is not on the official
> leaderboard); no independent replication exists; not peer reviewed. Notable single-sequence
> result — 50% ± 2 antibody-antigen with **no MSA**, above AF3's 47% ± 2 *with* one — but
> single-sequence protein-protein (70%) falls below AF3's 73%, so "single-sequence beats MSA" is
> task-specific, not general.
>
> **Practical routing:** prefer ESMFold2 for protein-protein and antibody-antigen; prefer
> AlphaFold 3 for protein-ligand; treat protein-DNA as a coin flip and decide on license. Then
> benchmark your own targets — none of this has been replicated by a third party.

## Compute Requirements

| Model | GPU | RAM | Storage | Speed |
|-------|-----|-----|---------|-------|
| ESMC 300M / 600M | 1x A100 40GB | 32 GB | Minimal | Seconds |
| ESMC 6B | multi-GPU (`device_map="auto"`) | 64 GB+ | ~12 GB weights | Seconds |
| ESMFold2 | 1x A100 80GB (ESMC 6B backbone) | 64 GB | ~12 GB+ | Seconds–minutes; single-seq mode fastest |
| ESMFold *(legacy)* | 1x A100 40GB | 32 GB | Minimal | Seconds |
| ColabFold | Free Colab | Minimal | Minimal | 1-5 min |
| AlphaFold 3 | 1x A100 80GB | 64 GB | ~1 TB | 5-30 min |
| Evo 2 (7B) | 1x A100 80GB | 64 GB | ~15 GB | Seconds |
| Evo 2 (40B) | 4x A100 80GB | 256 GB | ~80 GB | Seconds |

## Decision Matrix

| Need | Use | Why |
|------|-----|-----|
| DNA variant effects | Evo 2 | Zero-shot, cross-species |
| Protein embeddings | ESMC (300M/600M local, 6B for max quality) | Current generation; ESM-2 is the legacy fallback |
| Fast protein structure | ESMFold2 single-sequence mode | No MSA; large speedup over MSA path |
| Structure with ligands / DNA / RNA / modified AA | ESMFold2 or AlphaFold 3 | Both handle full biomolecule range; ESMFold2 is MIT |
| High-accuracy complexes | Benchmark ESMFold2 vs AlphaFold 3 / OpenFold-3 on **your** targets | Vendor rankings are self-reported and unreplicated — measure, don't inherit |
| Batch structure screening | ColabFold | Free GPU, 1000/day |
| Structural homolog search | Foldseek | Finds function from shape |
| Interpretable protein features | ESMC SAEs | ~16k named features; functional organization, not sequence similarity |
| Novel protein design | ProGen3 | 73% functional rate |
| Binder / minibinder design | ESMFold2 inversion | Published protocol: `cookbook/tutorials/binder_design.ipynb` |
| Commercial deployment | ESMFold2 / OpenFold-3 / Boltz-2 | MIT license (ESMFold2 as of 2026-05-27) |
