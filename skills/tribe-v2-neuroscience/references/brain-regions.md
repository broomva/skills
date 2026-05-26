# Cortical Atlas — fsaverage5 Brain Regions for TRIBE v2

TRIBE v2 outputs predictions on the **fsaverage5** surface mesh, which has **10,242 vertices per hemisphere** (20,484 total). This reference maps named brain regions to approximate vertex ranges in that combined array.

**Important caveats**:
- Vertex boundaries are approximate. Individual functional regions vary across subjects.
- The ranges below reflect typical functional boundaries from FreeSurfer parcellations and published fMRI atlases.
- Left hemisphere: vertices 0–10,241. Right hemisphere: vertices 10,242–20,483.
- TRIBE v2 is trained on naturalistic stimuli; very short (< 5s) or highly artificial stimuli may produce weaker signals.

---

## Visual Cortex

| Region | Full Name | Hemisphere | Approx vertex range (fsaverage5) | Primary inputs | Activated by |
|--------|-----------|-----------|----------------------------------|----------------|--------------|
| V1 | Primary Visual Cortex | Left | 0–1,500 | Retino-geniculo-calcarine | Any visual stimulus; retinotopic |
| V1 | Primary Visual Cortex | Right | 10,242–11,742 | Retino-geniculo-calcarine | Any visual stimulus; retinotopic |
| V2/V3 | Secondary / Tertiary Visual | Left | 1,500–2,500 | V1 outputs | Oriented edges, contours |
| V2/V3 | Secondary / Tertiary Visual | Right | 11,742–12,742 | V1 outputs | Oriented edges, contours |
| V4 | Ventral Color Area | Left | 2,500–3,000 | V2/V3 | Color, curved contours, faces |
| V4 | Ventral Color Area | Right | 12,742–13,242 | V2/V3 | Color, curved contours, faces |
| MT/V5 | Middle Temporal / V5 | Left | 2,800–3,200 | V1, V2, dorsal stream | Visual motion, optic flow, direction selectivity |
| MT/V5 | Middle Temporal / V5 | Right | 13,042–13,442 | V1, V2, dorsal stream | Visual motion, optic flow, direction selectivity |
| LOC | Lateral Occipital Complex | Left | 4,200–5,200 | V2/V3, ventral stream | Intact object shapes, viewpoint-invariant recognition |
| LOC | Lateral Occipital Complex | Right | 14,442–15,442 | V2/V3, ventral stream | Intact object shapes, viewpoint-invariant recognition |
| FFA | Fusiform Face Area | Left | 1,100–1,600 | Ventral visual stream | Faces (weaker than right); upright > inverted |
| FFA | Fusiform Face Area | Right | 9,900–10,400 | Ventral visual stream | Faces (dominant); upright > inverted; own race > other race |
| PPA | Parahippocampal Place Area | Left | 1,600–2,100 | Ventral stream | Scenes, spatial layout, indoor/outdoor environments |
| PPA | Parahippocampal Place Area | Right | 10,400–11,000 | Ventral stream | Scenes, spatial layout, indoor/outdoor environments |
| EBA | Extrastriate Body Area | Left | 5,200–5,700 | Lateral occipital | Body parts, silhouettes; not faces |
| EBA | Extrastriate Body Area | Right | 15,442–15,942 | Lateral occipital | Body parts, silhouettes; not faces |

**Lateralization notes (visual)**:
- FFA is strongly **right-lateralized** for faces.
- PPA is bilateral with slight right dominance for scenes.
- MT is bilateral; both hemispheres required for full motion processing.
- LOC is bilateral for object recognition.

---

## Auditory Cortex

| Region | Full Name | Hemisphere | Approx vertex range (fsaverage5) | Primary inputs | Activated by |
|--------|-----------|-----------|----------------------------------|----------------|--------------|
| A1 | Primary Auditory Cortex (Heschl's Gyrus) | Left | 3,500–4,200 | Medial geniculate nucleus (MGN) | Any sound; tonotopic (low-to-high frequency mapped) |
| A1 | Primary Auditory Cortex (Heschl's Gyrus) | Right | 13,742–14,442 | MGN | Any sound; right A1 biased toward pitch/music |
| Belt auditory | Auditory Belt / Lateral HG | Left | 4,200–4,800 | A1 | Complex sounds, pitch contours, voice identity |
| Belt auditory | Auditory Belt / Lateral HG | Right | 14,442–15,000 | A1 | Music, prosody, environmental sounds |
| STS | Superior Temporal Sulcus | Left | 4,800–5,300 | Belt, prefrontal | Audiovisual integration, voice, biological motion |
| STS | Superior Temporal Sulcus | Right | 15,000–15,500 | Belt, prefrontal | Social signals, facial expressions with sound |

**Lateralization notes (auditory)**:
- **Speech**: left-lateralized (left A1 + Wernicke's area stronger for phonemes and words).
- **Music and prosody**: right-lateralized (right belt auditory + right STS).
- STS is a multimodal convergence zone — activates for combined audio-visual speech.

---

## Language Network

| Region | Full Name | Hemisphere | Approx vertex range (fsaverage5) | Primary inputs | Activated by |
|--------|-----------|-----------|----------------------------------|----------------|--------------|
| Broca's area | IFG pars triangularis + opercularis (BA44/45) | Left | 6,200–6,800 | STS, DLPFC, premotor | Sentence comprehension, syntax, verbal working memory, speech production |
| Broca's area | IFG pars triangularis + opercularis (BA44/45) | Right | 16,442–17,042 | — | Prosodic processing; much weaker than left |
| Wernicke's area | Posterior STG / MTG (BA22) | Left | 5,700–6,200 | A1, STS | Word meaning, speech comprehension, phonological processing |
| Wernicke's area | Posterior STG / MTG (BA22) | Right | 15,942–16,442 | A1, STS | Prosody, emotional speech content |
| VWFA | Visual Word Form Area | Left | 7,100–7,500 | LOC, ventral visual stream | Written words, letter strings; font/case invariant |

**Lateralization notes (language)**:
- Language is strongly **left-lateralized** in ~95% of right-handers and ~70% of left-handers.
- Lateralization index (LI) = `(left - right) / (left + right)`; expect LI > 0.2 for any language stimulus.
- VWFA is exclusively left hemisphere; no right homolog shows significant activation for text.

---

## Motor and Somatosensory Cortex

| Region | Full Name | Hemisphere | Approx vertex range (fsaverage5) | Primary inputs | Activated by |
|--------|-----------|-----------|----------------------------------|----------------|--------------|
| M1 | Primary Motor Cortex (BA4) | Left | 8,600–9,000 | Premotor, SMA | Observed or imagined movement (mirror neuron overlap); strongest for contralateral movement |
| M1 | Primary Motor Cortex (BA4) | Right | 18,800–19,200 | Premotor, SMA | Contralateral (left side) observed movement |
| S1 | Primary Somatosensory Cortex (BA1/2/3) | Left | 9,100–9,600 | Thalamus (VPL) | Observed touch, pain imagery, body-contact scenes |
| S1 | Primary Somatosensory Cortex (BA3/1/2) | Right | 19,200–19,600 | Thalamus (VPL) | Contralateral body touch (left side of body) |
| SMA | Supplementary Motor Area | Left | 9,600–10,000 | M1, DLPFC | Action sequences, tool use videos, rhythm tracking |

**Notes**:
- M1 and S1 can activate during **observation** of actions (action observation network).
- For TRIBE v2 with video input, expect M1/S1 activation when stimuli show people interacting physically (sports, dance, handcraft).
- Somatotopy: face representation at inferior end, leg at superior-medial end of both M1 and S1.

---

## Default Mode Network (DMN)

| Region | Full Name | Hemisphere | Approx vertex range (fsaverage5) | Primary inputs | Activated by |
|--------|-----------|-----------|----------------------------------|----------------|--------------|
| mPFC | Medial Prefrontal Cortex | Left | 8,000–8,600 | PCC, angular gyrus, hippocampus | Self-referential thought, resting state, narrative; **deactivates** during demanding tasks |
| mPFC | Medial Prefrontal Cortex | Right | 18,200–18,800 | PCC, angular gyrus, hippocampus | Self-referential thought, resting state |
| PCC | Posterior Cingulate Cortex | Left | 9,000–9,500 | mPFC, hippocampus | Autobiographical memory retrieval, mind-wandering |
| PCC | Posterior Cingulate Cortex | Right | 19,200–19,700 | mPFC, hippocampus | Autobiographical memory retrieval, mind-wandering |
| Angular gyrus | Inferior parietal lobule | Left | 7,500–8,000 | STS, TPJ, parietal | Semantic integration, social cognition, story comprehension |
| Angular gyrus | Inferior parietal lobule | Right | 17,700–18,200 | STS, TPJ, parietal | Theory of mind, causal inference |
| Hippocampus | Parahippocampal / entorhinal | Left | 2,100–2,500 | Entorhinal cortex | Memory encoding, spatial context, episodic recall |

**Deactivation pattern**:
- The key DMN signature is **negative BOLD** (deactivation below resting baseline) during externally directed, cognitively demanding tasks.
- In TRIBE v2, this appears as **negative predicted activation values** in DMN regions for demanding stimuli.
- Conversely, slow narrative content or rest-like stimuli should produce **positive activation** in DMN.

---

## Prefrontal Cortex

| Region | Full Name | Hemisphere | Approx vertex range (fsaverage5) | Primary inputs | Activated by |
|--------|-----------|-----------|----------------------------------|----------------|--------------|
| DLPFC | Dorsolateral Prefrontal Cortex (BA9/46) | Left | 6,800–7,100 | Parietal, premotor, thalamus | Working memory, cognitive control, rule following, verbal rehearsal |
| DLPFC | Dorsolateral Prefrontal Cortex (BA9/46) | Right | 17,042–17,342 | Parietal, premotor | Spatial working memory, monitoring |
| OFC | Orbitofrontal Cortex (BA11/13) | Left | 9,600–10,000 | Amygdala, reward circuits | Reward prediction, emotional valence, hedonic value of stimuli |
| OFC | Orbitofrontal Cortex (BA11/13) | Right | 19,600–20,000 | Amygdala, reward circuits | Punishment, social emotion, facial attractiveness |
| vmPFC | Ventromedial PFC (BA10/11) | Left | 8,600–9,000 | OFC, mPFC, amygdala | Value-based decision, moral judgments, social reward |

**Notes**:
- DLPFC activates during narrative content with high cognitive load (complex grammar, working memory demands in the story).
- OFC is harder to drive with purely sensory stimuli; best activated by emotionally valenced or reward-predictive content.

---

## Quick Lookup: Region by Stimulus Type

| Stimulus type | Primary regions activated | Primary regions deactivated |
|---------------|--------------------------|------------------------------|
| Human faces (frontal, neutral) | FFA_right, FFA_left | — |
| Human faces (expressive) | FFA_right, STS_right, OFC | — |
| Outdoor scenes, landscapes | PPA_right, PPA_left | — |
| Moving objects / optic flow | MT_left, MT_right, V1 | — |
| Intact objects | LOC_left, LOC_right | — |
| Body parts, silhouettes | EBA_left, EBA_right | — |
| Spoken language (sentences) | Broca_left, Wernicke_left, A1_left | — |
| Written words / text | VWFA_left, Broca_left | — |
| Music / tonal sequences | A1_right, belt_auditory_right | — |
| Audiovisual speech | STS_left, Wernicke_left, A1 | — |
| Demanding cognitive task | DLPFC, Broca_left | mPFC, PCC, angular_gyrus (DMN) |
| Slow naturalistic narrative | mPFC, PCC, angular_gyrus (DMN) | — |
| Physical action / sports | M1, S1, STS | — |
| Tool use | Broca_left, premotor, M1 | — |

---

## Notes on Precision

These vertex ranges are **best estimates** derived from:
- FreeSurfer's Desikan-Killiany and Destrieux cortical parcellations mapped to fsaverage5
- Published fMRI coordinates converted to surface vertices (MNI → fsaverage5 via spherical registration)
- The TRIBE v2 paper's reported region-of-interest analyses

Exact activation peaks will vary with stimulus content and quality. For high-precision region localization, use a full parcellation atlas (e.g., `mne.datasets.fetch_fsaverage`, then map Glasser HCP 360-region parcellation to fsaverage5 vertices).

For exploratory work, the ranges above are sufficient to detect the canonical activations described in the paradigm library.
