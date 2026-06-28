# Paradigm Library — Classic Neuroscience Findings Replicable In-Silico with TRIBE v2

Each entry covers: the original finding, the stimulus type required, the expected TRIBE v2 vertex range to check, and what a positive replication looks like.

---

## 1. Face Selectivity in the Fusiform Face Area (FFA)

**Original finding**: Kanwisher, McDermott & Chun (1997, *J. Neuroscience*)
A region in the right fusiform gyrus (FFA) responds significantly more to upright faces than to objects, houses, or scrambled images. This was the founding paper for the "face patch" system.

**Stimulus type needed**
- **Faces condition**: video or images of frontal/profile human faces (no bodies visible, neutral expression acceptable)
- **Control condition**: matched images/video of common objects (chairs, tools) at same visual complexity

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| FFA (primary) | Right | 9,900–10,400 |
| FFA (secondary) | Left | 1,100–1,600 |

**How to interpret a positive replication**
- `mean_activation(FFA_right, faces) > mean_activation(FFA_right, objects)` with a selectivity index > 0.15
- Right FFA should show at least 1.5x higher response than left FFA for faces
- Objects and scrambled stimuli should produce activation near 0 in FFA

```python
selectivity_index = (face_ffa - object_ffa) / (face_ffa + object_ffa + 1e-8)
# Positive replication: selectivity_index > 0.15
```

---

## 2. Scene Selectivity in the Parahippocampal Place Area (PPA)

**Original finding**: Epstein & Kanwisher (1998, *Nature*)
A region in the parahippocampal cortex (PPA) responds maximally to images of places and scenes (indoor rooms, outdoor landscapes) compared to faces or objects.

**Stimulus type needed**
- **Scenes condition**: video of outdoor landscapes, cityscapes, indoor environments (no people in foreground)
- **Control condition**: close-up object or face videos without spatial context

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| PPA (primary) | Right | 10,400–11,000 |
| PPA | Left | 1,600–2,100 |

**How to interpret a positive replication**
- PPA shows higher activation for scenes than for faces or isolated objects
- PPA and FFA should show a double dissociation: scenes > faces in PPA, faces > scenes in FFA
- The double dissociation is the strongest replication signal

---

## 3. Object Selectivity in the Lateral Occipital Complex (LOC)

**Original finding**: Malach et al. (1995, *PNAS*)
A lateral occipital region (LOC) responds to intact objects regardless of exact size, viewpoint, or illumination — tuned to object shape rather than low-level features.

**Stimulus type needed**
- **Intact objects condition**: video or images of everyday objects in various viewpoints
- **Scrambled control**: pixel-scrambled versions of the same images (same spatial frequency, no object structure)

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| LOC | Right | 14,442–15,442 |
| LOC | Left | 4,200–5,200 |

**How to interpret a positive replication**
- `mean_activation(LOC, intact_objects) > mean_activation(LOC, scrambled)` by at least 0.2 units
- LOC activation should be bilateral (both hemispheres), unlike FFA which is right-dominant
- Should be robust across object category (tools, animals, vehicles)

---

## 4. Body Selectivity in the Extrastriate Body Area (EBA)

**Original finding**: Downing et al. (2001, *Science*)
A region in lateral occipitotemporal cortex (EBA) responds selectively to images of human bodies and body parts compared to objects, scrambled bodies, or faces.

**Stimulus type needed**
- **Body condition**: video of people walking, silhouettes, body parts (hands, arms) — faces cropped out
- **Control condition**: matched objects or scrambled body images

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| EBA | Right | 15,442–15,942 |
| EBA | Left | 5,200–5,700 |

**How to interpret a positive replication**
- EBA activation > baseline for body stimuli
- Face stimuli should not drive EBA (helps dissociate EBA from FFA)
- Both hemispheres should activate; slight right lateralization expected

---

## 5. Language Lateralization in Broca's Area

**Original finding**: Broca (1861) (clinical); modern fMRI confirmations by Binder et al. (1997, *JCMS*)
Language production and comprehension are strongly left-lateralized in most right-handed individuals. Broca's area (IFG pars triangularis, BA44/45) activates during sentence comprehension, verbal working memory, and syntactic processing.

**Stimulus type needed**
- **Language condition**: spoken or written sentences — narrative, syntactically complex preferred
- **Control condition**: non-linguistic auditory tone sequences or visual patterns of the same duration

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| Broca's area | Left | 6,200–6,800 |
| Broca's area | Right (control) | 16,442–17,042 |
| Wernicke's area | Left | 5,700–6,200 |

**How to interpret a positive replication**
- Left Broca's shows higher activation for sentences than for matched non-linguistic stimuli
- Compute lateralization index (LI):

```python
LI = (left_broca - right_broca) / (left_broca + right_broca + 1e-8)
# LI > 0 → left-lateralized (expected)
# LI > 0.2 → strong lateralization (replication)
```

---

## 6. Visual Word Form Area (VWFA) Selectivity

**Original finding**: Cohen et al. (2000, *Science*)
A region in the left fusiform gyrus (VWFA) responds selectively to written words and letter strings compared to non-orthographic visual stimuli such as faces, objects, or symbol strings.

**Stimulus type needed**
- **Words condition**: video or images of printed words, sentences, or letter strings in various fonts and cases
- **Control condition**: false fonts (letter-like symbols with no linguistic value), objects, or faces

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| VWFA | Left | 7,100–7,500 |

**How to interpret a positive replication**
- VWFA activation significantly higher for real words vs. false-font strings
- Left-lateralized: right hemisphere homolog (17,300–17,700) should show minimal response
- Selectivity should be invariant to font and case (uppercase vs. lowercase both drive VWFA)

---

## 7. Motion Selectivity in MT/V5

**Original finding**: Zeki (1974, *Brain*); Zeki et al. (1991, fMRI)
Area MT (middle temporal) / V5 responds selectively to visual motion — coherent moving dot fields, optic flow, moving gratings — compared to static images.

**Stimulus type needed**
- **Motion condition**: video with coherent optic flow (moving dot fields, walking humans, flowing water, camera dolly shots)
- **Static condition**: same content photographed with no camera or object motion (freeze frames replayed)

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| MT/V5 | Left | 2,800–3,200 |
| MT/V5 | Right | 13,042–13,442 |

**How to interpret a positive replication**
- MT activation significantly higher for motion than static stimuli
- Bilateral: both hemispheres should show the effect
- Effect should be robust across motion types (translational, radial, rotational)
- V1 activation should also increase but less specifically (distinguishes MT from V1 response)

---

## 8. Default Mode Network Deactivation During Task

**Original finding**: Raichle et al. (2001, *PNAS*); Buckner et al. (2008, review)
The Default Mode Network (DMN) — comprising mPFC, PCC, angular gyrus, and hippocampus — deactivates during externally-directed cognitive tasks but is active during rest, mind-wandering, and self-referential thought.

**Stimulus type needed**
- **Task condition**: cognitively demanding content — rapid arithmetic narration, spatial navigation instructions, fast-changing unfamiliar stimuli that demand attention
- **Rest/narrative condition**: slow, familiar naturalistic narrative (a familiar story told at relaxed pace)

**Expected TRIBE v2 vertex range to check**
| Region | Hemisphere | Vertex range (fsaverage5) |
|--------|-----------|--------------------------|
| mPFC | Left | 8,000–8,600 |
| PCC | Left | 9,000–9,500 |
| Angular gyrus | Left | 7,500–8,000 |
| mPFC | Right | 18,200–18,800 |
| PCC | Right | 19,200–19,700 |

**How to interpret a positive replication**
- DMN regions show **negative activation** (below-baseline suppression) during demanding-task stimuli
- DMN regions show positive activation during naturalistic narrative
- Task-negative contrast = `mean_activation(DMN, demanding) - mean_activation(DMN, narrative)` should be negative

```python
dmn_contrast = (demanding_mPFC + demanding_PCC) / 2 - (narrative_mPFC + narrative_PCC) / 2
# Replication: dmn_contrast < -0.1
```

This is the most counterintuitive paradigm to replicate: showing that brain regions *deactivate* with demanding stimuli.

---

## Using These Paradigms in TRIBE v2

All paradigms above require the same basic workflow:

```python
from tribev2 import TribeModel
import numpy as np

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")

# Load condition stimuli
df_a = model.get_events_dataframe(video_path="condition_A.mp4")
df_b = model.get_events_dataframe(video_path="condition_B.mp4")

preds_a, _ = model.predict(events=df_a)
preds_b, _ = model.predict(events=df_b)

# Extract ROI
v_start, v_end = 9900, 10400  # e.g., FFA_right
roi_a = preds_a[:, v_start:v_end].mean()
roi_b = preds_b[:, v_start:v_end].mean()

contrast = roi_a - roi_b
print(f"Contrast A - B = {contrast:.4f}")
```

See `scripts/run_experiment.py` for automated multi-condition batch processing.
