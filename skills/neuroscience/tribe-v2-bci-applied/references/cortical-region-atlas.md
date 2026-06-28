# Cortical Region Atlas for TRIBE v2 Applied Work

Applied reference for BCI research, neuromarketing, and content optimization using TRIBE v2 predictions on the fsaverage5 surface mesh (~20,484 vertices per hemisphere).

**Note on vertex ranges**: All ranges listed here are approximate, derived from published parcellations (Glasser 2016 HCP MMP1.0, Wang 2015 probabilistic retinotopy, Fedorenko 2010 language localizer). For production BCI use, replace with exact parcellation indices registered to your fsaverage5 space. These ranges are sufficient for content ranking and relative comparisons.

---

## 1. Visual Processing Hierarchy

The visual system is organized hierarchically from primary cortex (V1) through increasingly complex feature representations. TRIBE v2 was trained on visual stimuli with high fidelity — this is the best-characterized region for applied use.

| Region | Hemisphere | Approx fsaverage5 vertex range | What activates it | Applied BCI/neuromarketing use |
|--------|------------|-------------------------------|-------------------|-------------------------------|
| V1 / V2 (primary visual cortex) | Bilateral | 1000–4000 | Edges, contrast, spatial frequency, luminance gradients | Baseline visual response — any on-screen content; contrast/sharpness testing |
| V4 (color/form area) | Bilateral | 4000–5500 | Color saturation, shape contours, object form | Color palette testing, logo recognition, brand color impact |
| MT / V5 (motion area) | Bilateral | 5500–7000 | Optical flow, motion direction, speed, biological motion | Dynamic ad elements, video transitions, animation speed testing |
| FFA (fusiform face area) | Bilateral (RH dominant) | 12000–14000 | Face identity, expression, eye contact | Spokesperson effectiveness, avatar design, product-with-person ads |
| PPA (parahippocampal place area) | Bilateral | 14000–16000 | Spatial layouts, architecture, scene geometry, outdoor environments | Location/setting imagery in ads, spatial UI design, real estate content |
| EBA (extrastriate body area) | Bilateral | Near MT, ~6500–8000 | Body shape, posture, gesture | Fitness content, fashion, gesture-based UI |

**Applied notes (visual hierarchy):**
- V1/V2 activation is essentially always present for visual stimuli — use as normalization baseline
- High MT activation = content has strong motion/dynamics; correlates with perceived energy and liveliness
- High FFA + high STS = face + social processing; strong predictor of emotional engagement with on-screen people
- PPA activation matters for setting-driven narratives (travel, real estate, outdoor lifestyle)

---

## 2. Auditory Processing

Auditory cortex is organized from primary (tonotopic) through increasingly abstract speech and social representations. TRIBE v2 captures these well when video or audio input includes natural soundtracks.

| Region | Hemisphere | Approx fsaverage5 vertex range | What activates it | Applied BCI/neuromarketing use |
|--------|------------|-------------------------------|-------------------|-------------------------------|
| A1 (primary auditory cortex) | Bilateral | 8000–10000 | Pure tones, pitch, onset transients, amplitude modulation | Music beat timing, audio onset design, alert sound design |
| Auditory belt regions | Bilateral | 10000–11500 | Voice identity, timbre, music melody, pitch patterns | Voiceover voice selection, music genre testing, podcast audio quality |
| STS (superior temporal sulcus) | Bilateral | 11500–13000 | Speaker identity, prosody, emotional tone, lip movement, audiovisual integration | Voiceover effectiveness, emotional tone of narration, talking-head video engagement |

**Applied notes (auditory):**
- STS is a hub for social audio — it activates for emotionally expressive speech, charming voices, and audiovisual synchrony
- High STS + high FFA = strong predicted engagement with on-screen speakers
- Low auditory activation despite audio content = flat prosody or generic background music with no salience
- Use auditory belt to compare different music tracks or voiceover artists

---

## 3. Language Network

The language network is left-hemisphere dominant and distributed across frontal and temporal cortex. TRIBE v2 was trained with text and speech inputs that engage this network.

| Region | Hemisphere | Approx fsaverage5 vertex range | What activates it | Applied BCI/neuromarketing use |
|--------|------------|-------------------------------|-------------------|-------------------------------|
| Broca's area (IFG pars triangularis + opercularis) | Left | 15000–17000 | Syntactic processing, speech production planning, semantic working memory | Caption/subtitle complexity, script structure testing, syntax simplicity A/B |
| Wernicke's area (posterior STG / STS) | Left | 17000–18500 | Speech comprehension, phonological decoding, semantic integration | Spoken content clarity, voiceover comprehension, word choice optimization |
| VWFA (visual word form area, fusiform gyrus) | Left | 18500–19500 | Reading, letter recognition, word-level orthographic processing | On-screen text readability, caption font/size testing, reading level assessment |

**Applied notes (language):**
- High Broca's activation = content requires more active linguistic processing — good for complex narratives, can be fatigue-inducing for simple ads
- High Wernicke's = speech is being actively decoded — indicates comprehensible but engaging spoken content
- High VWFA = strong on-screen text processing; matters when captions are critical to comprehension (e.g., silent video)
- For accessibility: compare VWFA activation for different caption styles to find the most readable format

---

## 4. Emotional and Social Processing

These regions mediate reward valuation, emotional salience, and social interpretation. Note: vmPFC is cortical and within TRIBE v2's fsaverage5 coverage; amygdala is subcortical and has limited coverage.

| Region | Hemisphere | Approx fsaverage5 vertex range | What activates it | Applied BCI/neuromarketing use |
|--------|------------|-------------------------------|-------------------|-------------------------------|
| vmPFC (ventromedial prefrontal cortex) | Bilateral (medial) | 18000–19000 | Reward value, emotional valence, self-relevance, preference encoding | Emotional resonance testing, brand value perception, preference-driven content design |
| OFC (orbitofrontal cortex) | Bilateral | Near vmPFC, ~17500–18500 | Expected reward, pleasantness, sensory value | Hedonic appeal of visual/taste/luxury content |
| Amygdala | Bilateral (subcortical) | Not well-covered in fsaverage5 | Emotional salience, threat detection, arousal | Limited TRIBE v2 coverage; use vmPFC as cortical proxy for valence |
| TPJ (temporoparietal junction) | Bilateral (RH dominant) | ~13000–15000 | Theory of mind, social attribution, agency | Social narrative content, character-driven storytelling, empathy-inducing ads |

**Applied notes (emotional/social):**
- vmPFC activation is a key marker for content that feels personally relevant or rewarding
- TPJ activation correlates with understanding character intentions and social dynamics in narratives
- Combine vmPFC + FFA + STS for a "social-emotional engagement" composite score
- Avoid confusing vmPFC activation with DMN activation — they partially overlap; check context

---

## 5. Attention and Default Mode Network

These regions govern top-down attentional control and the mind-wandering / narrative immersion state. The DMN typically deactivates during external task engagement — high DMN activation during content viewing can indicate mind-wandering or self-referential processing.

| Region | Hemisphere | Approx fsaverage5 vertex range | What activates it | Applied BCI/neuromarketing use |
|--------|------------|-------------------------------|-------------------|-------------------------------|
| IPS (intraparietal sulcus) | Bilateral | 7000–8000 | Spatial attention, visual salience-driven orienting, numerical processing | Attentional guidance design, UI layout scanning behavior, infographic comprehension |
| FEF (frontal eye fields) | Bilateral | ~8000–8500 | Volitional gaze direction, covert attention | Eye-tracking prediction, UI element prominence, call-to-action placement |
| mPFC (medial prefrontal cortex — DMN node) | Bilateral (medial) | 19000–19500 | Self-referential thought, prospective memory, mind-wandering | Detect narrative immersion vs. distraction; low mPFC during task = high focus |
| PCC (posterior cingulate cortex — DMN node) | Bilateral (medial) | ~19200–19700 | Default mode hub, autobiographical memory, internal narrative | Narrative resonance, story-driven engagement; PCC activation = deep immersion |
| Angular gyrus (DMN + language overlap) | Bilateral | ~19500–20000 | Semantic integration, narrative comprehension, conceptual metaphor | Abstract concept understanding, brand storytelling, metaphor in advertising |

**Applied notes (attention and DMN):**
- IPS + FEF high activation = stimulus is actively directing visual attention; useful for UI design testing
- DMN (mPFC + PCC + angular gyrus) often deactivates during externally demanding tasks
- High DMN during content = either mind-wandering (bad) or deep narrative immersion (good) — context matters
- For content designed to be immersive/story-driven, moderate DMN activation is expected and desirable
- For instructional or attention-critical content (safety videos, tutorial walkthroughs), low DMN + high IPS is ideal

---

## Composite Attention Proxy

For applied engagement scoring, a weighted combination of visual + motion + social regions provides a robust attention proxy that correlates with behavioral attention measures:

```
Attention proxy = 0.4 * V1–V4 + 0.3 * MT/V5 + 0.3 * STS
```

This captures: Are they looking? (V1–V4), Is it dynamic? (MT), Are social signals present? (STS)

---

## Cross-Region Interaction Patterns

Common multi-region combinations and their interpretations:

| Pattern | Interpretation | Applied use case |
|---------|----------------|-----------------|
| High visual + High STS + High FFA | Strong social-visual engagement; face+voice together | Talking-head videos, spokesperson ads |
| High visual + Low language + Low STS | Visually engaging but not verbally or socially memorable | Silent visual ads, abstract motion graphics |
| High language + Low visual | Verbally driven; good for podcasts, radio ads, text-heavy content | Audio content, documentary narration |
| High language + High VWFA | Reading-heavy engagement; captions are load-bearing | Tutorial content with heavy text |
| High vmPFC + High FFA | Emotional + face engagement; personal resonance | Testimonial content, empathy-driven ads |
| High DMN + Low visual | Possible mind-wandering; content may not be sustaining attention | Flag for content revision |
| High MT + Low FFA + Low STS | Action/motion without social engagement | Product-demo videos without people |

---

## fsaverage5 Technical Notes

- **Total vertices**: 20,484 per hemisphere (40,968 bilateral); TRIBE v2 likely uses the combined surface
- **Vertex numbering**: Not anatomically contiguous — parcellation lookup required for exact ROIs
- **Resolution**: ~3mm average inter-vertex distance (coarser than fsaverage with 163,842 vertices)
- **Registration**: All individual brains registered to this surface via FreeSurfer spherical registration
- **Atlases to use for exact parcellations**:
  - Glasser 2016 HCP MMP1.0 (360 parcels bilateral) — best parcellation for applied work
  - Wang 2015 probabilistic retinotopy — best for early visual cortex
  - Fedorenko 2010 functional localizer — language network
  - Yeo 2011 7-network / 17-network — coarse functional networks

**Getting exact parcellation indices** (Python):
```python
import nibabel as nib
import numpy as np

# Download HCP MMP1.0 parcellation for fsaverage5
# From: https://github.com/ThomasYeoLab/CBIG/tree/master/stable_projects/brain_parcellation
label_img = nib.load("hcp_mmp1_fsaverage5_lh.label.gii")
labels = label_img.darrays[0].data  # (n_vertices,) array of parcel IDs
parcel_names = label_img.labeltable.labels  # map ID → name

# Get exact V4 vertices
v4_vertices = np.where(labels == parcel_id_for_V4)[0].tolist()
```

---

## Further Reading

- Glasser et al. (2016) "A multi-modal parcellation of human cerebral cortex" — Nature
- Wang et al. (2015) "Probabilistic maps of visual topography in human cortex" — Cerebral Cortex
- Benchetrit et al. (2025) "Brain-wide visual responses to natural stimuli" — Meta AI Research (TRIBE v2 paper)
- Huth et al. (2016) "Natural speech reveals the semantic maps that tile human cerebral cortex" — Nature
- Regev et al. (2019) "Selective responses to video stimuli in neural systems across the human brain" — Cerebral Cortex
