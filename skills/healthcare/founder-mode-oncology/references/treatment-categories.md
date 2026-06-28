# Treatment Categories and Combination Logic

## Table of Contents
- [Checkpoint Inhibitors](#checkpoint-inhibitors)
- [Neoantigen Vaccines](#neoantigen-vaccines)
- [Oncolytic Viruses](#oncolytic-viruses)
- [Cell Therapies](#cell-therapies)
- [Radioligand Therapy](#radioligand-therapy)
- [Immune Modulators](#immune-modulators)
- [Targeted Therapy](#targeted-therapy)
- [Combination Rationale](#combination-rationale)
- [Contraindications and Monitoring](#contraindications-and-monitoring)

---

## Checkpoint Inhibitors

**Mechanism**: Block inhibitory receptors on T cells, removing the "brakes" on anti-tumor immunity.

| Target | Drug Examples | FDA Status |
|--------|-------------|------------|
| PD-1 | Dostarlimab, Pembrolizumab, Nivolumab | Approved (multiple indications) |
| PD-L1 | Atezolizumab, Durvalumab, Avelumab | Approved (multiple indications) |
| CTLA-4 | Ipilimumab, Tremelimumab | Approved (melanoma, others) |

**Role in combination**: Foundation layer. Required for other immunotherapies to work — if the brakes are on, no amount of immune activation matters.

**Common combination**: PD-1 + CTLA-4 dual blockade (e.g., Dostarlimab + Ipilimumab).

**Monitoring**: irAEs (immune-related adverse events) — thyroiditis, colitis, hepatitis, pneumonitis. Thyroid dysfunction is actually a positive prognostic sign.

---

## Neoantigen Vaccines

**Mechanism**: Train the immune system to recognize tumor-specific mutations (neoantigens) that are absent from normal tissue.

| Platform | Turnaround | Cost | Advantages |
|----------|-----------|------|------------|
| Peptide (synthetic long peptides) | 4-8 weeks | $10K-50K | Proven in trials, stable |
| mRNA (LNP-encapsulated) | 4-6 weeks | $4K-$13K | Potent, multiple antigens, scalable |
| Dendritic cell | 6-8 weeks | $50K+ | Strong immune priming |

**Pipeline**: Tumor sequencing → HLA typing → neoantigen prediction (pVACseq) → MHC binding prediction (MHCflurry) → candidate ranking (Vaxrank) → manufacturing

**Iterative versions**: As the tumor evolves and new sequencing is done, update the vaccine (JLFv1 → v2 → v3 in reference case).

**Adjuvants**: GM-CSF (granulocyte-macrophage colony-stimulating factor) enhances antigen presentation. Often co-administered.

**Monitoring**: ELISPOT assays measure T cell reactivity to vaccine peptides. Variant allele frequency tracking confirms target persistence.

---

## Oncolytic Viruses

**Mechanism**: Engineered viruses that selectively infect and lyse cancer cells. Tumor lysis releases antigens, creating an in situ vaccine effect.

| Virus | Example | Special Features |
|-------|---------|-----------------|
| Adenovirus | AdaPT-001 | TGF-beta trap (counteracts immunosuppressive TME) |
| HSV-1 | T-VEC (Imlygic) | GM-CSF expression (FDA approved for melanoma) |
| Reovirus | Pelareorep | Targets RAS pathway |

**Routes**: Intratumoral (IT) for accessible tumors, subcutaneous (SQ) for systemic priming.

**Synergy**: Complements checkpoint inhibitors and vaccines. Virus kills cells → releases neoantigens → vaccines have primed T cells against those antigens → checkpoint inhibitors ensure T cells can act.

---

## Cell Therapies

| Type | Source | Manufacturing | Advantages |
|------|--------|--------------|------------|
| CAR-T | Patient's T cells | 3-4 weeks, patient-specific | Potent, durable |
| CAR-NK | Donor NK cells | Off-the-shelf | No GvHD risk, scalable |
| NK cells (SNK-01) | Expanded autologous/allogeneic | 2-3 weeks | Innate killing, boosters |
| TILs | Tumor-infiltrating lymphocytes | 4-6 weeks | Already tumor-reactive |
| MSCs + exosomes | Adipose-derived | 2-3 weeks | Immunomodulatory |

**Advanced**: Genetic logic gates in cell therapies — engineered circuits that activate killing only when multiple tumor-specific signals are detected. Reduces off-target toxicity.

---

## Radioligand Therapy

**Mechanism**: Conjugate a radioactive isotope to a molecule that targets a tumor-specific surface protein. Delivers radiation directly to cancer cells.

**Theranostic principle**: Same targeting molecule used for:
1. **Diagnosis**: 68Ga (gallium-68, PET imaging) — "does the tumor express the target?"
2. **Therapy**: 177Lu (lutetium-177, beta emitter) or 225Ac (actinium-225, alpha emitter) — "deliver radiation to target-expressing cells"

| Isotope | Type | Range | Energy | Use Case |
|---------|------|-------|--------|----------|
| 177Lu | Beta | 2mm | Medium | First-line, broad coverage |
| 225Ac | Alpha | 50-100μm | High | Refractory disease, potent |
| 90Y | Beta | 12mm | High | Larger tumors |

**Known targets with existing ligands:**
- PSMA (prostate cancer — Pluvicto, FDA approved)
- FAP (fibroblast activation protein — many solid tumors)
- SSTR (neuroendocrine tumors — Lutathera, FDA approved)
- B7H3, EphA2 (experimental)

**Key insight from reference case**: FAP was discovered via scRNA-seq, not standard tests. Target must be validated by PET imaging before therapy.

**Access**: Available in Germany and select US centers. May require international travel or expanded access.

---

## Immune Modulators

| Agent | Mechanism | Timing |
|-------|-----------|--------|
| GM-CSF | Enhances antigen presentation | With vaccines |
| Anktiva (IL-15 superagonist) | Stimulates NK + T cell proliferation | Periodically |
| IFN-alpha | Broad immune activation | Less common, side effects |
| Toll-like receptor agonists | Innate immune activation | With vaccines |

---

## Targeted Therapy

| Category | Examples | Use Case |
|----------|---------|----------|
| Anti-RANKL (XGeva) | Denosumab | Bone-destructive cancers |
| mTOR inhibitors | nab-Sirolimus, Everolimus | PI3K/AKT/mTOR pathway active |
| Multi-kinase inhibitors | Pazopanib, Sorafenib | VEGFR/PDGFR overexpression |
| Gene therapy | DeltaRex-G | Cyclin G1 targeting (retroviral) |

---

## Combination Rationale

The goal is converting a "cold" tumor (immune-excluded) to a "hot" tumor (immune-infiltrated). Each modality attacks a different barrier:

```
BARRIER: Tumor is invisible to immune system
  → SOLUTION: Neoantigen vaccines train recognition

BARRIER: Immune cells are inhibited by tumor
  → SOLUTION: Checkpoint inhibitors remove brakes

BARRIER: Tumor microenvironment is immunosuppressive
  → SOLUTION: Oncolytic virus (TGF-beta trap), immune modulators

BARRIER: Not enough immune cells activated
  → SOLUTION: IL-15, GM-CSF amplify immune response

BARRIER: Tumor has a protective stromal shield
  → SOLUTION: FAP-targeted radioligand destroys stroma

BARRIER: Tumor escapes via clonal evolution
  → SOLUTION: Multi-antigen vaccines, updated per sequencing round
```

**Evidence from reference case**: This multi-modal parallel approach shifted immune infiltration from 19% → 89% T cells — the transformation from cold to hot.

---

## Contraindications and Monitoring

**Checkpoint inhibitor irAEs:**
- Thyroiditis (10-20%): Monitor TSH. Treat with methimazole or levothyroxine.
- Colitis (5-15%): Monitor for diarrhea. May require steroids.
- Hepatitis (5-10%): Monitor LFTs.
- Pneumonitis (1-5%): Monitor for dyspnea.
- Positive prognostic sign: irAEs correlate with better tumor response.

**Steroid risks:**
- Repeated dexamethasone → avascular necrosis risk (hip, jaw)
- Minimize steroid exposure when possible

**Radioligand risks:**
- Bone marrow suppression (monitor CBC)
- Kidney toxicity (225Ac: monitor renal function)
- Salivary gland damage (for some targets)

**Surgical site risks (post-spinal surgery):**
- Seroma/infection: culture-guided antibiotics, may require hardware removal
- CSF leak: epidural blood patch
