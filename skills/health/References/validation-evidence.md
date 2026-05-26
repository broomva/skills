# Validation evidence — what synthesis metrics are HIGH-confidence

Every synthesis metric in this skill is tagged **[HIGH] / [MED] / [LOW] / [CONFLICT]** by the evidence quality behind it. The agent surfaces these tags whenever it quotes a metric value to the user. This is the *substance* of "be honest about what we know"; without it, "validated longevity-proxy synthesis" is marketing.

The taxonomy:

| Tag | Threshold |
|---|---|
| **[HIGH]** | Multiple peer-reviewed studies; meta-analysis; consensus across independent researchers |
| **[MED]** | At least one well-conducted study; expert consensus with acknowledged gaps |
| **[LOW]** | Industry claim without independent replication; vendor composite without published formula; "made up score" per Marco Altini |
| **[CONFLICT]** | Active disagreement between credible sources; replication failures published |

---

## VO2max & longevity — **[HIGH]**

**Claim:** VO2max is the strongest modifiable predictor of all-cause mortality among the commonly-measurable longevity proxies. Moving from bottom 25th percentile to top 25th percentile is associated with **~5× reduction** in all-cause mortality risk.

**Evidence:**
- Mandsager K. et al., *Association of Cardiorespiratory Fitness With Long-term Mortality Among Adults Undergoing Exercise Treadmill Testing*. **JAMA Network Open**, 2018;1(6):e183605. **n = 122,007**, 8.4-year median follow-up. https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2707428
- Kodama S. et al., *Cardiorespiratory Fitness as a Quantitative Predictor of All-Cause Mortality and Cardiovascular Events in Healthy Men and Women: A Meta-Analysis*. **JAMA**, 2009;301(19):2024-2035. Meta-analysis, **n = 102,980 across 33 studies**. https://jamanetwork.com/journals/jama/fullarticle/183967
- Strasser B. & Burtscher M., *Survival of the fittest: VO2max, a key predictor of longevity?*. **Frontiers in Bioscience (Landmark Edition)**, 2018;23:1505-1516. https://pubmed.ncbi.nlm.nih.gov/29293446/
- Peter Attia, *Outlive: The Science and Art of Longevity* (Harmony, 2023), chapter 11 — synthesizes the above + discusses programming VO2max-targeted training. https://peterattiamd.com/outlive/

**Tag:** **[HIGH]** — multiple high-quality studies, consistent effect-size estimates across cohorts, biologically plausible mechanism (cardiorespiratory fitness = aggregate physiologic reserve).

**Caveats** (do not downgrade the tag, but surface):
- The 5× ratio is *associational*, not causal. VO2max may proxy other healthful behaviors.
- Wearable VO2max estimates are *estimates* — Garmin's algorithm is proprietary. Cooper-test or treadmill VO2max with gas exchange is the lab reference; wearable values track but are noisier.

---

## HRV-CV > absolute HRV — **[HIGH]**

**Claim:** The coefficient of variation (CV) of an individual's own overnight HRV over a stable trailing window is more actionable than the absolute HRV value. CV is the trend signal; absolute is noise.

**Evidence:**
- Marco Altini, "The Ultimate Guide to Heart Rate Variability (HRV): Part 1" — extensive coverage of why intra-individual CV is the right unit of analysis. https://www.marcoaltini.com/blog/the-ultimate-guide-to-heart-rate-variability-hrv-part-1
- Galpin AJ et al. (Andy Galpin / WHOOP 2026 update on HRV interpretation in the *Performance* podcast and WHOOP's locker — emphasis on intra-individual trends over inter-individual comparison)
- Plews DJ et al., *Training Adaptation and Heart Rate Variability in Elite Endurance Athletes: Opening the Door to Effective Monitoring*. **Sports Medicine**, 2013;43(9):773-781. https://pubmed.ncbi.nlm.nih.gov/23852814/
- Buchheit M., *Monitoring training status with HR measures: Do all roads lead to Rome?*. **Frontiers in Physiology**, 2014;5:73. https://pubmed.ncbi.nlm.nih.gov/24578692/

**Tag:** **[HIGH]** — consistent across athlete-monitoring literature, validated in elite-endurance cohorts, biologically grounded (autonomic regulation is individual; cross-person comparison is noisy).

**Caveats:**
- Requires ≥ 7 nights in window for the CV estimate to be meaningful (we encode `_MIN_SAMPLES = 7` in `synthesis/hrv.py` and return `None` below that).
- Wearable HRV is RMSSD-based by convention; some research uses SDNN. Compare like with like.

---

## CTL / ATL / TSB (Coggan PMC) — **[HIGH]**

**Claim:** The Coggan Performance Management Chart — Chronic Training Load (42-day EWMA of TSS), Acute Training Load (7-day EWMA), Training Stress Balance (CTL − ATL) — is the canonical training-load model in endurance sports literature.

**Evidence:**
- Coggan AR & Allen H., *Training and Racing with a Power Meter* (3rd ed., VeloPress 2019). The canonical text.
- Coggan AR, *The Science of the Performance Manager*. TrainingPeaks Learn. https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/
- Banister EW & Calvert TW, *Planning for Future Performance: Implications for Long Term Training*. **Canadian Journal of Applied Sport Sciences**, 1980;5(3):170-176. The original "fitness/fatigue" model that Coggan formalized; cited in nearly every paper since.
- Pinot J & Grappe F, *The Record Power Profile to assess performance in elite cyclists*. **International Journal of Sports Medicine**, 2011;32(11):839-844. Validation of the PMC framework in elite cyclists. https://pubmed.ncbi.nlm.nih.gov/22052033/

**Tag:** **[HIGH]** — 40+ years of literature, used by every major endurance-training platform (TrainingPeaks, Intervals.icu, Final Surge), reproducible from raw TSS without vendor magic.

**Caveats:**
- Requires power-meter or HR-derived TSS. Activities without TSS (yoga, easy walks) don't contribute — load here is a **training-stress** proxy, not an **energy-expenditure** proxy.
- The 42 / 7 time constants are the convention, not magic. Different communities tune them (e.g. 56/12 for ultra-endurance).

---

## Vendor recovery scores (Body Battery, Training Readiness, Whoop Recovery, Oura Readiness) — **[LOW]**

**Claim:** Vendor-composite "recovery scores" — Garmin Body Battery, Garmin Training Readiness, Whoop Recovery, Oura Readiness, Polar Recovery — are **unvalidated composites without published formulas**. Per Marco Altini and other independent researchers, they are best treated as opaque trace data, **not** as the answer to "how recovered am I".

**Evidence:**
- Marco Altini, "On HRV-based recovery scores" and various blog posts — explicitly characterizes most vendor recovery scores as "made-up". https://www.marcoaltini.com/blog
- The vendor formulas are unpublished. Garmin's Body Battery whitepaper is a marketing document; it does not specify the inputs or weights. Whoop's Recovery is partly published but the strain side is proprietary.
- No peer-reviewed validation studies of any of these composites against gold-standard recovery measures (lab cortisol, subjective wellness questionnaires, performance tests) have replicated cleanly.

**Tag:** **[LOW]** — vendor composite, no independent replication.

**Policy:** We store the vendor scores in the trace DB under their canonical `MetricCode` (`BODY_BATTERY`, `TRAINING_READINESS`, etc.) for completeness, but the [RecoveryReview](../Workflows/RecoveryReview.md) workflow computes its **own** transparent composite (`recovery_composite_z`) from inputs the agent can explain. The vendor scores are surfaced under `vendor_scores_opaque` and tagged **[LOW]**.

---

## Wearable sleep staging — **[MED]**

**Claim:** Wearable sleep-stage classification (light / deep / REM / awake) is moderately accurate for *total sleep duration* and *sleep / wake discrimination*, but unreliable for *stage-level* detection. Best published estimate for consumer wearable slow-wave (deep) sleep detection: **~51.5%** sensitivity.

**Evidence:**
- de Zambotti M et al., *The Sleep of the Ring: Comparison of the OURA Sleep Tracker Against Polysomnography*. **Behavioral Sleep Medicine**, 2019;17(2):124-136. Oura vs PSG; total sleep time accurate, stage breakdown poor. https://pubmed.ncbi.nlm.nih.gov/28323455/
- Chinoy ED et al., *Performance of seven consumer sleep-tracking devices compared with polysomnography*. **Sleep**, 2021;44(5):zsaa291. Seven-device head-to-head; **slow-wave sleep sensitivity ≈ 51.5% across devices**. https://pubmed.ncbi.nlm.nih.gov/33378539/
- Miller DJ et al., *A validation study of the WHOOP strap against polysomnography to assess sleep*. **Journal of Sports Sciences**, 2020;38(22):2631-2636. https://pubmed.ncbi.nlm.nih.gov/32713257/

**Tag:** **[MED]** — sleep *duration* is **[HIGH]**, sleep *stages* are **[LOW]**, aggregate **[MED]**.

**Policy:** [DailyNote](../Workflows/DailyNote.md) surfaces `sleep_hours` ([HIGH]) and `sleep_score` ([MED] — vendor composite) directly. Per-stage detail is available in the trace under `SLEEP_STAGE` category samples but is surfaced with the staging-accuracy caveat in any agent prose.

---

## Menstrual-cycle periodization — **[LOW]**

**Claim:** Periodizing training based on menstrual cycle phase (follicular vs. luteal) is widely promoted in performance literature (notably Stacy Sims), but the underlying evidence base is **weak and acknowledged as such by the leading proponents.**

**Evidence:**
- Sims ST, *ROAR: How to Match Your Food and Fitness to Your Unique Female Physiology for Optimum Performance, Great Health, and a Strong, Lean Body for Life* (Rodale, 2016).
- Sims ST, "Updated Position Statements on Menstrual Cycle and Training" (2025) — explicit acknowledgement that the evidence base for phase-based periodization is preliminary, the inter-individual variability is large, and most "rules" don't survive replication.
- McNulty KL et al., *The Effects of Menstrual Cycle Phase on Exercise Performance in Eumenorrheic Women: A Systematic Review and Meta-Analysis*. **Sports Medicine**, 2020;50(10):1813-1827. **n = 78 studies**, conclusion: trivial average effect on performance with **very high inter-individual variability**. https://pubmed.ncbi.nlm.nih.gov/32661839/
- Elliott-Sale KJ et al., *Methodological Considerations for Studies in Sport and Exercise Science with Women as Participants: A Working Guide for Standards of Practice for Research on Women*. **Sports Medicine**, 2021;51(5):843-861. https://pubmed.ncbi.nlm.nih.gov/33725341/

**Tag:** **[LOW]** — promising frame, weak average effects, very high individual variability, even leading proponents acknowledge the evidence base is preliminary.

**Policy:** The trace stores `MENSTRUAL_FLOW` and `CYCLE_PHASE` as category samples (so users tracking cycle data on a wearable have it captured), but the agent does **not** issue cycle-based training recommendations in v1. The Coaching workflow is explicitly NOT IMPLEMENTED.

---

## RHR trend — **[HIGH]**

**Claim:** A sustained elevation of resting heart rate (5+ bpm above 30-day baseline) often precedes detectable illness by 24–48 hours and is a long-standing overreaching marker in endurance-training literature.

**Evidence:**
- Achten J & Jeukendrup AE, *Heart rate monitoring: applications and limitations*. **Sports Medicine**, 2003;33(7):517-538. https://pubmed.ncbi.nlm.nih.gov/12762827/
- Plews DJ et al. (see HRV-CV section above).
- Stanford / Snyder lab work on Fitbit RHR as a leading indicator of viral illness onset (COVID-era publications): Mishra T et al., *Pre-symptomatic detection of COVID-19 from smartwatch data*. **Nature Biomedical Engineering**, 2020;4:1208-1220. https://www.nature.com/articles/s41551-020-00640-6
- Quer G et al., *Wearable sensor data and self-reported symptoms for COVID-19 detection*. **Nature Medicine**, 2021;27:73-77. https://www.nature.com/articles/s41591-020-1123-x

**Tag:** **[HIGH]** — multiple independent lines of evidence, including illness-precursor work using wearable RHR.

---

## Promotion rules

A health observation is **only** promoted to the entity graph (`research/entities/concept/health-*.md` via P6 Bookkeeping, score ≥ 5/9 on the Nous gate) when:

1. It's a **pattern** that recurs (rule-of-three) — not a single day's number.
2. It carries an evidence tag ([HIGH] / [MED] / [LOW]) and the tag is justified in the entity body.
3. The provenance trail back to the raw trace is documented (date, source, samples used).
4. If the tag is [LOW], the entity body explicitly says "low-confidence; surfaced for completeness".

Individual sample values **never** promote. The skill is a substrate; entities are insights *about* the substrate.

---

## All cited URLs

- https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2707428 (Mandsager 2018 — VO2max & mortality, JAMA Network Open)
- https://jamanetwork.com/journals/jama/fullarticle/183967 (Kodama 2009 — CRF meta-analysis, JAMA)
- https://pubmed.ncbi.nlm.nih.gov/29293446/ (Strasser & Burtscher 2018 — VO2max & longevity)
- https://peterattiamd.com/outlive/ (Peter Attia, *Outlive*)
- https://www.marcoaltini.com/blog/the-ultimate-guide-to-heart-rate-variability-hrv-part-1 (Altini — HRV guide)
- https://www.marcoaltini.com/blog (Altini — vendor recovery score critique)
- https://pubmed.ncbi.nlm.nih.gov/23852814/ (Plews 2013 — HRV in elite endurance)
- https://pubmed.ncbi.nlm.nih.gov/24578692/ (Buchheit 2014 — HR-based training-status monitoring)
- https://www.trainingpeaks.com/learn/articles/the-science-of-the-performance-manager/ (Coggan — PMC)
- https://pubmed.ncbi.nlm.nih.gov/22052033/ (Pinot & Grappe 2011 — Record Power Profile)
- https://pubmed.ncbi.nlm.nih.gov/28323455/ (de Zambotti 2019 — Oura vs PSG)
- https://pubmed.ncbi.nlm.nih.gov/33378539/ (Chinoy 2021 — 7-device sleep validation)
- https://pubmed.ncbi.nlm.nih.gov/32713257/ (Miller 2020 — WHOOP vs PSG)
- https://pubmed.ncbi.nlm.nih.gov/32661839/ (McNulty 2020 — menstrual cycle meta-analysis)
- https://pubmed.ncbi.nlm.nih.gov/33725341/ (Elliott-Sale 2021 — women in sport science research)
- https://pubmed.ncbi.nlm.nih.gov/12762827/ (Achten & Jeukendrup 2003 — HR monitoring)
- https://www.nature.com/articles/s41551-020-00640-6 (Mishra 2020 — Fitbit pre-symptomatic COVID detection)
- https://www.nature.com/articles/s41591-020-1123-x (Quer 2021 — wearables + symptoms COVID)
