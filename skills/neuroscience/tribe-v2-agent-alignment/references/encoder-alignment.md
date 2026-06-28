# Encoder Alignment — Methodology and Reference

Technical reference for interpreting cortical alignment scores produced by `scripts/align_encoder.py`.

---

## 1. Methodology: Linear Probing via Ridge Regression

Cortical alignment is measured using the **linear encoding model** paradigm from computational neuroscience. The protocol:

1. **Encoder forward pass** — Run each stimulus through the candidate AI encoder. Extract the final hidden state and mean-pool over the spatial/temporal dimension to get a single vector per stimulus. This yields a matrix `X` of shape `(n_stimuli, encoder_dim)`.

2. **TRIBE v2 forward pass** — Run the same stimuli through TRIBE v2. Extract predicted fMRI activity over the modality-relevant ROI (e.g., language cortex vertices 12000-18000 for text). This yields `Y` of shape `(n_stimuli, n_roi_vertices)`.

3. **Ridge regression probe** — Fit a ridge regression `Y_hat = X @ W + b` where `W` is `(encoder_dim, n_roi_vertices)`. Train and test on disjoint stimulus sets via k-fold cross-validation (default 5 folds). Regularization prevents overfitting to encoder-specific quirks.

4. **R-squared as alignment score** — Report the mean coefficient of determination (R²) across vertices and CV folds. R² = 1 - (sum of squared residuals / total variance). This measures the fraction of TRIBE v2 cortical variance that the encoder's representations can linearly explain.

### Why R² and Not Pearson r

R² accounts for both correlation and scaling. An encoder whose activations are correlated but differently scaled from cortical activity will score lower than one with matched magnitude. In practice, StandardScaler is applied to both X and Y before fitting, so the difference from using r vs. R² is small, but R² is the conventional reporting metric in encoding model benchmarks (see Scotti et al., Brain-Score 2, 2024).

### Why Ridge and Not LASSO or OLS

Ridge regression handles the high-dimensional `encoder_dim >> n_stimuli` regime (common with LLMs) without overfitting. The regularization strength alpha defaults to 1.0; sweep over `[0.01, 0.1, 1.0, 10.0, 100.0]` and pick the best by inner CV when n_stimuli is large enough.

---

## 2. Known Alignment Scores (from TRIBE v2 paper and related work)

These are reference values from the TRIBE v2 publication (Benchetrit et al., 2025) and related encoding model studies. Use them to sanity-check your benchmark runs.

### Text Encoders — Language Cortex (vertices 12000-18000)

| Encoder | Architecture | R² (approx) | Source |
|---------|-------------|-------------|--------|
| LLaMA 3.2-3B | Autoregressive LM | ~0.40 | TRIBE v2 paper |
| LLaMA 3.1-8B | Autoregressive LM | ~0.38-0.42 | Benchetrit et al. |
| Mistral 7B | Autoregressive LM | ~0.35-0.40 | Community benchmarks |
| GPT-2 (large) | Autoregressive LM | ~0.28-0.33 | Encoding model literature |
| BERT-base | Masked LM | ~0.18-0.22 | Multiple sources |
| RoBERTa-large | Masked LM | ~0.20-0.26 | Multiple sources |
| all-mpnet-base-v2 | Sentence BERT | ~0.12-0.18 | Approximate |
| Random linear encoder | Baseline | ~0.00-0.03 | Lower bound |

**Key finding from TRIBE v2**: Autoregressive LMs (LLaMA family) consistently outperform masked LMs (BERT family) on language cortex alignment. This matches the finding that language cortex processes text in a predictive (left-to-right) manner, not bidirectionally.

### Video Encoders — Visual Cortex (vertices 1000-8000)

| Encoder | Architecture | R² (visual cortex) | Notes |
|---------|-------------|-------------------|-------|
| V-JEPA2 (ViT-G) | Masked video prediction | High (~0.35-0.45) | TRIBE v2's native video encoder |
| VideoMAE-v2 (ViT-H) | Masked video prediction | ~0.30-0.40 | Strong motion encoding |
| CLIP ViT-L/14 | Contrastive image-text | ~0.20-0.28 | Good static visual, weak motion |
| DINO ViT-B/16 | Self-supervised image | ~0.15-0.22 | Limited temporal sensitivity |
| ResNet-50 | Supervised image classification | ~0.10-0.15 | Old baseline |
| Random CNN | Baseline | ~0.00-0.05 | Lower bound |

**Key finding from TRIBE v2**: Self-supervised video models trained with masked prediction (V-JEPA2, VideoMAE) strongly align with motion-selective cortex (MT/MST, vertices 5000-8000). CLIP-style models align better with ventral visual stream (V1-V4) than dorsal motion stream.

### Audio Encoders — Auditory Cortex (vertices 8000-11000)

| Encoder | Architecture | R² (auditory cortex) | Notes |
|---------|-------------|---------------------|-------|
| Wav2Vec-BERT 2.0 | Self-supervised speech | High (~0.30-0.40) | TRIBE v2's native audio encoder |
| wav2vec 2.0 (large) | Self-supervised speech | ~0.25-0.35 | Strong speech alignment |
| HuBERT (large) | Self-supervised speech | ~0.25-0.32 | Similar to wav2vec 2.0 |
| Whisper (encoder only) | Supervised ASR | ~0.20-0.28 | Task supervision reduces alignment |
| CLAP (audio-text) | Contrastive audio-text | ~0.15-0.22 | General audio, not speech-specific |
| Random waveform features | Baseline | ~0.00-0.04 | Lower bound |

---

## 3. Interpretation Thresholds

| R² Range | Label | Recommendation |
|----------|-------|----------------|
| > 0.40 | Excellent | Use as primary encoder for this modality in Arcan routing |
| 0.25 – 0.40 | Good | Use; monitor for regression after fine-tuning |
| 0.10 – 0.25 | Moderate | Consider as fallback; may lack higher-level semantic features |
| 0.05 – 0.10 | Poor | Not recommended; likely encoding only low-level statistical patterns |
| < 0.05 | Chance | Do not use; representations are not capturing modality-relevant information |

**Practical guidance**: A 0.05 R² difference between two encoders is typically not meaningful given fMRI noise. Treat differences < 0.05 as ties and prefer the faster/smaller model.

---

## 4. Modality-to-Region Mapping

The ROI vertex ranges below are approximate boundaries on the fsaverage5 surface (~20k vertices total, both hemispheres combined). Left hemisphere is vertices 0-9999, right hemisphere 10000-19999.

| Modality | ROI Label | Vertex Range | Cortical Areas |
|----------|-----------|-------------|----------------|
| Text | language_cortex | 12000 – 18000 | IFG (Broca, ~15000-18000), STG posterior (Wernicke, ~13000-15000) |
| Video | visual_cortex | 1000 – 8000 | V1/V2 (~1000-3000), V3/V4 (~3000-5000), MT/MST motion (~5000-8000) |
| Audio | auditory_cortex | 8000 – 11000 | Primary auditory cortex A1 (~8000-10000), belt areas (~10000-11000) |

For more precise parcellation, use the HCP MMP1.0 atlas projected onto fsaverage5. The vertex ranges above are suitable for bulk alignment scoring but not for fine-grained region analysis.

### Emergent Functional Networks

TRIBE v2 spontaneously recovers 5 functional brain networks from its training data alone. Verify your encoder activates the expected network:

| Network | ROI Vertices (approx) | Encoder That Best Drives It |
|---------|----------------------|----------------------------|
| Primary auditory | 8000 – 10000 | Wav2Vec-BERT 2.0 |
| Language | 12000 – 18000 | LLaMA 3.2-3B |
| Motion | 5000 – 8000 | V-JEPA2 |
| Default mode | 18000 – 20000 | Broad contextual encoders |
| Visual | 1000 – 5000 | V-JEPA2, CLIP |

If your encoder achieves high R² outside its expected network (e.g., a video encoder scoring high on language cortex vertices), investigate for data leakage or multimodal contamination in training.

---

## 5. Limitations

### Population-Average Predictions
TRIBE v2 predicts population-average cortical responses from its training cohort. Individual subjects show ~0.05 R² variability around the population mean. Alignment scores therefore reflect how well an encoder matches the "average human", not any particular subject.

### 5-Second Temporal Window
TRIBE v2 processes stimuli in non-overlapping 5-second windows. Encoders that capture phenomena at shorter timescales (e.g., phoneme-level in audio) may be slightly disadvantaged. Temporal pooling (mean over the window) is applied before probing.

### Linear Probe Assumption
Ridge regression measures linear decodability only. An encoder could have high non-linear alignment with cortex but low linear R². For a fuller picture, use representational similarity analysis (RSA) in addition to linear probing — but linear R² is sufficient for model selection.

### Stimulus Distribution Shift
Alignment scores are sensitive to stimulus statistics. TRIBE v2 was trained on naturalistic video/audio/text; synthetic or highly structured stimuli (e.g., word lists, artificial tones) will yield lower and less reliable alignment estimates. Use naturalistic stimuli when possible.

### CC BY-NC 4.0 License Constraint
TRIBE v2 is released under Creative Commons Attribution-NonCommercial 4.0. Alignment scores derived from its predictions cannot be used in commercial products or to gate commercial model routing decisions without a separate agreement with Meta. For internal R&D and open-source projects within the Broomva stack, CC BY-NC permits use.

### Stimulus Count Requirement
Reliable R² estimates require at least 20 stimuli (more is better). With fewer than 10 stimuli, the cross-validation estimate has high variance; treat results as directional only. The TRIBE v2 paper used thousands of fMRI trial repetitions; `align_encoder.py` is a lightweight proxy using TRIBE v2 predictions as a surrogate ground truth.
