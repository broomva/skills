# Structural Biology for Personalized Oncology

## Table of Contents
- [Overview](#overview)
- [Neoantigen Vaccine Enhancement](#neoantigen-vaccine-enhancement)
- [Radioligand Target Modeling](#radioligand-target-modeling)
- [De Novo Therapeutic Protein Design](#de-novo-therapeutic-protein-design)
- [Mutation Impact Analysis](#mutation-impact-analysis)
- [Key Target Structures](#key-target-structures)
- [Tool Stack](#tool-stack)
- [Quality Thresholds](#quality-thresholds)

---

## Overview

Structure prediction adds a 3D validation layer to the sequence-based pipeline. Instead of predicting binding from sequence alone (MHCflurry), validate that the peptide physically fits the MHC groove (AlphaFold Multimer). Instead of confirming a target via PET alone, model the ligand-protein binding interface.

**Where it fits in the three pillars:**
- Pillar 1 (Diagnostics): Mutation impact analysis, target structure characterization
- Pillar 2 (Therapeutics): Vaccine validation, radioligand optimization, de novo binder design
- Pillar 3 (Parallel): Structural prioritization of which modalities to combine

---

## Neoantigen Vaccine Enhancement

Enhance the pVACseq → MHCflurry → Vaxrank pipeline with 3D structure validation.

**Enhanced pipeline:**
```
Mutations → pVACseq → MHCflurry (1D binding) → TOP 20-50 CANDIDATES
  → AlphaFold Multimer (peptide + HLA chain) → 3D binding validation
  → Filter: ipTM >0.5, PAE_interface <10, pLDDT >85
  → Re-rank by structural confidence
  → Select top 10-20 for vaccine
```

**Why this helps:**
- MHCflurry predicts binding affinity from sequence — fast but approximate
- AlphaFold Multimer predicts actual 3D complex — reveals physical binding geometry
- Peptides scoring high on both = strongest candidates
- Structure reveals which residues are solvent-exposed (available for TCR recognition)
- The neoantigen-specific residue must face outward for T cells to distinguish it from wildtype

**Implementation:**
```bash
# Create FASTA with peptide + HLA-A*02:01 heavy chain
# Run ColabFold multimer
modal run modal_colabfold.py \
  --input-faa peptide_mhc_pairs.fasta \
  --out-dir af_neoantigen_validation/
```

**Evaluation** (using AlphaFold result files):
- Extract ipTM and pLDDT from result pkl files
- Filter: ipTM >0.5 and pLDDT >85 → PASS
- Re-rank passing candidates by ipTM descending

---

## Radioligand Target Modeling

Model the binding interface between tumor targets and targeting ligands.

**Workflow:**
```
1. Retrieve target structure from AlphaFold DB
   → FAP: AF-Q12884-F1
   → B7H3: AF-Q5ZPR3-F1
   → EphA2: AF-P29317-F1

2. Identify surface-exposed druggable pockets
   → Catalytic domain (for FAP: dipeptidyl peptidase activity)
   → Extracellular domains (for B7H3, EphA2)

3. Model ligand binding
   → Existing ligands: FAPI-04, FAPI-46 (for FAP)
   → Use Chai or Boltz for protein-ligand complex prediction
   → Assess binding pose and contact residues

4. Optimize
   → If binding is suboptimal, modify ligand chemistry
   → Validate with re-docking
   → Same ligand scaffold carries 68Ga (imaging) or 177Lu/225Ac (therapy)
```

**Theranostic validation**: Structural modeling can predict whether the diagnostic (68Ga-labeled) and therapeutic (177Lu/225Ac-labeled) versions maintain equivalent binding — critical for the theranostic principle.

---

## De Novo Therapeutic Protein Design

When no existing drug targets the identified surface, design custom proteins.

**Full pipeline:**
```
Phase 1: Target Characterization
  → AlphaFold DB or AlphaFold2 prediction of target
  → Identify binding epitope (tumor-specific, surface-exposed)
  → InterPro domain analysis

Phase 2: Backbone Generation
  → RFdiffusion: generate ≥5 backbone geometries complementary to epitope
  → Filter by geometry and contact surface area
  → Select top 3-5 backbones

Phase 3: Sequence Design
  → ProteinMPNN: design ≥8 sequences per backbone
  → Sample at temperature 0.1-0.3 for diversity
  → MPNN score >0.6

Phase 4: Structure Validation
  → ESMFold (fast): screen all candidates
  → AlphaFold2 (accurate): validate top candidates
  → Criteria: pLDDT >85, pTM >0.8

Phase 5: Developability
  → Aggregation propensity (low is better)
  → Isoelectric point (neutral range preferred)
  → Expression prediction
  → Immunogenicity assessment

Phase 6: Output
  → Ranked candidates with FASTA sequences
  → Structural models (.pdb)
  → Experimental recommendations
```

**Tools:**
| Step | Tool | Repo |
|------|------|------|
| Backbone generation | RFdiffusion | github.com/RosettaCommons/RFdiffusion (2.8K stars) |
| Backbone gen v2 | RFdiffusion2 | github.com/RosettaCommons/RFdiffusion2 (408 stars) |
| Sequence design | ProteinMPNN | github.com/dauparas/ProteinMPNN (1.7K stars) |
| Fast validation | ESMFold | Meta (API or local) |
| Accurate validation | AlphaFold2 | DeepMind / ColabFold |
| Protein-ligand | Chai / Boltz | For small molecule interactions |

**Use cases in oncology:**
- Design binder against FAP extracellular domain → fusion with radionuclide carrier
- Design binder against B7H3 → CAR construct or bispecific antibody
- Design binder against neoantigen-MHC complex → synthetic TCR mimic

---

## Mutation Impact Analysis

Understand structural consequences of each somatic mutation.

```
For each somatic mutation from WES/WGS:
  1. Get wildtype protein sequence (UniProt)
  2. Create mutant sequence (apply SNV)
  3. Predict both structures (ESMFold for speed, AF2 for accuracy)
  4. Compare:
     - RMSD (structural deviation)
     - pLDDT change (confidence shift → stability impact)
     - Surface exposure change (buried → exposed = potential neoantigen)
  5. Classify:
     - Surface-altering on expressed protein → neoantigen candidate
     - Destabilizing (large RMSD, pLDDT drop) → misfolded protein → immune recognition
     - Neutral → deprioritize for vaccine

ESM-2 embeddings can also predict mutation effects:
  → Compute log-likelihood ratio (wildtype vs mutant)
  → Large negative ratio = destabilizing mutation
  → Faster than full structure prediction for screening
```

---

## Key Target Structures

Retrieve from AlphaFold DB (alphafold.ebi.ac.uk):

| Target | UniProt | AF DB ID | Role in Treatment |
|--------|---------|----------|-------------------|
| FAP (Fibroblast Activation Protein) | Q12884 | AF-Q12884-F1 | Radioligand therapy target |
| B7-H3 (CD276) | Q5ZPR3 | AF-Q5ZPR3-F1 | Experimental PET/CAR-T target |
| EphA2 | P29317 | AF-P29317-F1 | Experimental PET target |
| PD-1 (PDCD1) | Q15116 | AF-Q15116-F1 | Dostarlimab target |
| PD-L1 (CD274) | Q9NZQ7 | AF-Q9NZQ7-F1 | Checkpoint target |
| CTLA-4 | P16410 | AF-P16410-F1 | Ipilimumab target |
| RANKL (TNFSF11) | O14788 | AF-O14788-F1 | XGeva target |
| HLA-A*02:01 | P01892 | AF-P01892-F1 | MHC for neoantigen presentation |

---

## Tool Stack

| Tool | Purpose | Speed | Accuracy | When |
|------|---------|-------|----------|------|
| **AlphaFold2** | Single protein structure | Moderate | Highest | Target characterization, mutation analysis |
| **AlphaFold Multimer** | Protein complex | Moderate | High | Peptide-MHC validation, antibody-antigen |
| **ESMFold** | Fast single chain | Fast | Good | Screening many candidates |
| **ESM-2** | Sequence embeddings | Very fast | Good | Mutation effect prediction, batch screening |
| **RFdiffusion** | De novo backbone | Moderate | N/A | Custom binder design |
| **ProteinMPNN** | Sequence for backbone | Fast | High | Sequence design after RFdiffusion |
| **Chai/Boltz** | Protein-ligand | Moderate | Good | Radioligand binding modeling |
| **ColabFold** | Cloud AF2 + MSA | Moderate | Highest | Batch validation, multimer |
| **NVIDIA NIM** | GPU-accelerated tools | Fast | High | RFdiffusion, ProteinMPNN, ESMFold via API |

---

## Quality Thresholds

| Metric | Excellent | Acceptable | Reject | Meaning |
|--------|-----------|------------|--------|---------|
| pLDDT (mean) | >85 | >75 | <70 | Per-residue confidence |
| pTM | >0.80 | >0.70 | <0.65 | Global fold confidence |
| ipTM (complex) | >0.60 | >0.50 | <0.40 | Interface confidence |
| PAE (interface) | <8 | <12 | >15 | Relative position error |
| MPNN score | >0.70 | >0.60 | <0.50 | Sequence recovery |

**Tier grading:**
- **T1** (best): pLDDT >85, pTM >0.8, low aggregation — proceed to synthesis
- **T2**: pLDDT >75, pTM >0.7 — consider with additional validation
- **T3**: pLDDT >70, pTM >0.65 — redesign recommended
- **T4**: Below thresholds — reject
