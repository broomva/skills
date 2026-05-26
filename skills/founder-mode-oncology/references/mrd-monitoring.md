# MRD Monitoring — Liquid Biopsy Interpretation

## Table of Contents
- [Overview](#overview)
- [Platform Comparison](#platform-comparison)
- [Interpretation Guide](#interpretation-guide)
- [Monitoring Cadence](#monitoring-cadence)
- [Actionable Thresholds](#actionable-thresholds)
- [Complementary Monitoring](#complementary-monitoring)

---

## Overview

Minimum Residual Disease (MRD) monitoring via circulating tumor DNA (ctDNA) enables real-time treatment response measurement — weeks before imaging shows changes. This is the primary feedback loop for the parallel treatment strategy.

**Principle**: Tumor cells shed DNA fragments into the bloodstream. Detecting and quantifying these fragments tells you:
1. Whether cancer is present (even below imaging threshold)
2. Whether treatment is working (declining ctDNA = response)
3. Whether cancer is recurring (rising ctDNA = progression)

---

## Platform Comparison

### Tumor-Informed Assays

Custom panel designed from the patient's specific tumor mutations.

**Signatera (Natera)** — MTM/mL (mean tumor molecules per mL)
- Requires: Prior tumor sequencing to design personalized panel (16 variants tracked)
- Sensitivity: Can detect down to 0.01 MTM/mL
- Specificity: Very high (custom panel minimizes false positives)
- Turnaround: 7-10 business days
- Cost: ~$3,000-$5,000 per test
- Best for: Definitive clearance confirmation, recurrence detection

**Personalis NeXT Personal** — PPM (parts per million)
- WGS-based ctDNA quantification
- Ultra-sensitive (detects at single-digit PPM)
- Logarithmic scale provides dynamic response range
- Best for: Early response measurement (large dynamic range)

### Tumor-Agnostic Assays

Detect cancer signal without prior tumor information.

**Northstar** — TMS (Tumor Methylation Signal)
- Methylation-based detection (epigenetic, not mutation-based)
- Does not require prior tumor sequencing
- Never reaches zero (background methylation signal)
- Range observed: 10-26 in reference case
- Best for: Trend monitoring, complementary to mutation-based assays
- Limitation: Cannot confirm true clearance (non-zero floor)

### Comparison Matrix

| Feature | Signatera | Personalis | Northstar |
|---------|-----------|------------|-----------|
| Type | Tumor-informed | Tumor-informed | Tumor-agnostic |
| Input required | Tumor sequencing | Tumor WGS | Blood only |
| Units | MTM/mL | PPM | TMS |
| Can reach zero | Yes | Yes | No |
| Dynamic range | Moderate | Very high | Moderate |
| Best use | Clearance confirmation | Response dynamics | Trend monitoring |
| False negative risk | Low | Low | Higher |
| False positive risk | Very low | Low | Moderate |

---

## Interpretation Guide

### Declining ctDNA

**Pattern**: Progressive decrease over 2-4 readings
**Interpretation**: Treatment is working
**Action**: Continue current regimen. Layer additional therapies if decline is slow.

### Rapidly Declining ctDNA

**Pattern**: >90% drop within 2-4 weeks (e.g., Personalis 963 → 21 PPM)
**Interpretation**: Strong treatment response
**Action**: Continue. Consider adding maintenance therapy (vaccine) to sustain.

### Stable Low ctDNA

**Pattern**: Hovering at low but detectable levels
**Interpretation**: Residual disease persists, treatment containing but not eliminating
**Action**: Add new modality (radioligand, oncolytic virus, or updated vaccine).

### Rising ctDNA

**Pattern**: Two consecutive increases
**Interpretation**: Treatment resistance or progression
**Action**: Urgent re-evaluation. New biopsy for updated sequencing. Switch or add therapies.

### Undetectable ctDNA

**Pattern**: Zero on tumor-informed assay (Signatera = 0)
**Interpretation**: No detectable molecular residual disease
**Action**: Continue preventive vaccines. Extend monitoring intervals to monthly, then quarterly.

### Blip (Transient Spike)

**Pattern**: Single elevated reading followed by return to baseline
**Interpretation**: May reflect: tumor cell death from treatment (positive), inflammation, or assay noise
**Action**: Repeat in 2 weeks before changing therapy. Correlate with clinical context (recent treatment, infection, surgery).

### Discordance Between Platforms

**Pattern**: One platform shows signal, another doesn't
**Interpretation**: Different assays have different sensitivities and specificities

**Resolution**:
- Signatera positive, Northstar negative: Trust Signatera (tumor-informed > agnostic)
- Northstar elevated, Signatera negative: Likely non-tumor methylation (inflammation, aging)
- Both positive: High confidence of disease
- Both negative: High confidence of clearance

---

## Monitoring Cadence

| Phase | Frequency | Rationale |
|-------|-----------|-----------|
| Active treatment | Every 2-4 weeks | Real-time response feedback |
| Post-surgery | Every 2 weeks for 3 months | Detect early recurrence |
| Stable remission | Monthly for 1 year | Surveillance |
| Extended remission | Quarterly | Long-term monitoring |
| Suspected progression | Every 2 weeks | Confirm trend before treatment change |

---

## Actionable Thresholds

| Scenario | Signatera | Personalis | Action |
|----------|-----------|------------|--------|
| Baseline (pre-treatment) | >0.1 MTM/mL | >50 PPM | Document. Start treatment. |
| Good response | <0.01 or ND | <10 PPM or ND | Continue. Add maintenance vaccine. |
| Molecular clearance | ND (×2 consecutive) | ND (×2 consecutive) | Preventive mode. Extend intervals. |
| Molecular relapse | Any detectable after ND | Any detectable after ND | Urgent: re-biopsy, re-sequence, new therapy. |

ND = Not Detected

---

## Complementary Monitoring

ctDNA alone is insufficient. Combine with:

### Flow Cytometry
- Track B/T cell subsets (CD4, CD8, NK, MAIT cells)
- Monitor immune reconstitution during immunotherapy
- Declining T cells may indicate immunosuppression or disease progression

### Serial scRNA-seq (PBMCs)
- Monthly during active treatment
- Reveals immune cell composition changes at single-cell resolution
- Can identify: T cell exhaustion markers, new immune populations, clonal expansion
- More informative than flow cytometry but more expensive

### Imaging (PET/CT/MRI)
- Every 2-3 months during active treatment
- ctDNA detects molecular changes weeks before imaging shows structural changes
- Imaging confirms structural response after ctDNA response
- Novel PET tracers (68Ga-FAP, 68Ga-B7H3) for target-specific imaging

### Tumor Markers (if applicable)
- ALP (alkaline phosphatase) for bone cancers
- PSA for prostate
- CA-125 for ovarian
- CEA for colorectal
- Less specific than ctDNA but cheap and widely available

### ELISPOT
- Measures T cell reactivity to specific peptides (vaccine antigens)
- Confirms vaccine is generating immune response
- Run after each vaccine dose series
