# Ethics and Privacy Reference for TRIBE v2 Applied Use

This document governs the acceptable and prohibited uses of this skill. Read this before any applied use of TRIBE v2 predictions. These constraints are not advisory — they are enforced by the skill's Ethical Guardrails section and by CC BY-NC 4.0 licensing law.

---

## 1. License Constraint: CC BY-NC 4.0

TRIBE v2 is released under the [Creative Commons Attribution-NonCommercial 4.0 International License](https://creativecommons.org/licenses/by-nc/4.0/).

**What this means:**

| Permitted | Blocked |
|-----------|---------|
| Academic research and publication | Optimizing content for commercial advertising campaigns |
| Accessibility and assistive technology research | Audience profiling for commercial targeting or revenue generation |
| Clinical hypothesis generation | Licensing or selling TRIBE v2 predictions as a product or service |
| Educational use | Neuromarketing research conducted on behalf of a for-profit client |
| Non-commercial UX research with full disclosure | Any use where the primary purpose is to increase commercial revenue |
| BCI research (non-profit, academic) | Building a commercial product whose core value derives from TRIBE v2 predictions |

**For commercial use**: Contact Meta Research to negotiate a separate commercial license.
- Meta AI Research contact: https://research.facebook.com
- License inquiries: reach out via the TRIBE v2 GitHub repository (https://github.com/facebookresearch/tribev2)

**Attribution**: Any publication or product using TRIBE v2 must attribute:
> Benchetrit et al. (2025). "Brain-wide visual responses to natural stimuli." Meta AI Research.

---

## 2. Consent Framework

Brain response simulation using TRIBE v2 does not involve any real brain scanning. No actual fMRI data is collected. However, predictions about neural responses to content raise important privacy and consent considerations.

### Core principle: Treat TRIBE v2 predictions like real fMRI data for consent purposes.

**Why**: Even though predictions are model outputs (not measured from real people), they characterize how human brains respond to stimuli. Using these predictions to optimize content for exploitation — without the knowledge of the audience — is equivalent to conducting covert neuroimaging on them.

### Consent tiers by use case:

| Use case | Minimum consent requirement |
|----------|-----------------------------|
| Academic research (published) | IRB/ethics board approval; participant disclosure of computational methods used |
| Internal UX research | Inform participants that neural prediction modeling was used in content design |
| Accessibility research | Full disclosure to participants; results shared back where appropriate |
| Clinical hypothesis generation | IRB approval; predictions treated as supporting evidence only, not diagnosis |
| BCI research | Full informed consent; disclose that population-average priors are used (see section 5) |

**What does NOT require individual consent**: Batch predictions on media you created, for internal research purposes, with no deployment to target audiences. Example: comparing two product videos you own to select the more neurally engaging one for internal review.

**What DOES require disclosure**: Any case where the predictions influence content that will be served to an audience without their knowledge that neural prediction was used in content design.

---

## 3. Prohibited Uses

The following uses of this skill are explicitly prohibited under CC BY-NC 4.0, ethical research norms, and the intended use policy of TRIBE v2.

### 3.1 Exploitative Optimization
**Prohibited**: Optimizing content to exploit emotional vulnerabilities in target audiences.

This includes: designing stimuli that maximize predicted amygdala/vmPFC activation specifically to trigger fear, anxiety, or impulsive decision-making in a commercial context. Neural optimization is acceptable for positive engagement; it is not acceptable when directed at vulnerabilities.

### 3.2 Commercial Audience Profiling
**Prohibited**: Building psychological or neural profiles of audience segments for the purpose of commercial advertising targeting, political micro-targeting, or personalized influence at scale.

This includes: generating TRIBE v2 predictions for a corpus of content consumed by a demographic and using those predictions to infer what that demographic is "neurologically susceptible to."

### 3.3 Neural Dark Patterns
**Prohibited**: Generating stimuli specifically designed to bypass conscious decision-making — colloquially called "neural dark patterns."

This includes:
- Content optimized to trigger automatic emotional responses before conscious evaluation can occur
- Interfaces designed to maximize neural engagement specifically to override deliberate choice
- Attention capture mechanisms designed to make disengagement neurologically costly

### 3.4 Minor-Specific Optimization Without Guardian Framework
**Prohibited**: Optimizing content targeting minors (under 18) without a formal guardian consent and oversight framework.

This includes: using TRIBE v2 to A/B test children's content for engagement optimization without parental consent and independent ethics review.

### 3.5 Non-Consensual Individual Profiling
**Prohibited**: Using TRIBE v2 to generate individual-level neural response predictions for real people without their explicit informed consent.

Note: TRIBE v2 is a population-average model — it does not predict a specific individual's responses. But inference about how content affects specific groups requires the same consent frameworks as group-level neuroimaging studies.

### 3.6 Surveillance and Monitoring
**Prohibited**: Using TRIBE v2 predictions as inputs to surveillance, attention monitoring, or behavioral monitoring systems without explicit opt-in consent from subjects.

---

## 4. Acceptable Uses

The following uses are explicitly acceptable within CC BY-NC 4.0 and ethical norms:

| Use case | Requirements |
|----------|-------------|
| Academic research on media perception | Non-commercial; cite TRIBE v2; follow institutional ethics procedures |
| Accessibility improvement research | Full participant disclosure; results shared back to community |
| Clinical hypothesis generation | Treat as hypothesis-generating only; no diagnostic use; IRB required |
| UX research with full participant disclosure | Inform participants that neural prediction modeling informed design |
| Non-invasive BCI research (EEG/fMEG) | Disclose use of population-average priors (see section 5); IRB required |
| Educational demonstrations | Must make clear predictions are population averages, not individual measurements |
| Internal creative optimization (non-commercial) | For research institutions or non-profits evaluating content they own |

---

## 5. BCI-Specific Risk Disclosures

When TRIBE v2 priors feed into a real BCI decoding pipeline (e.g., EEG source localization, imagined speech decoding), the following must be disclosed to end users and documented in any publication:

### 5.1 Population-Average Assumption
TRIBE v2 generates predictions based on patterns learned from a population of participants. Individual brains differ substantially in:
- Exact anatomical location of functional regions
- Magnitude of activation responses
- Individual processing strategies

**Required disclosure**: "The cortical priors used in this BCI system are derived from a population-average neural encoder (TRIBE v2, Meta AI Research). These priors represent expected population-level activation patterns and may not accurately reflect any individual user's neural responses."

### 5.2 No Diagnostic Use
TRIBE v2 predictions and the priors derived from them must not be used as diagnostic tools for neurological or psychiatric conditions. They are research and research-support tools only.

### 5.3 No Clinical Decision Support
TRIBE v2 predictions must not be used to make or inform clinical decisions about individual patients without explicit regulatory approval and clinical validation.

### 5.4 Data Security for BCI Predictions
Predicted neural response data should be treated with the same security standards as actual fMRI data:
- Do not transmit over unencrypted channels
- Do not store without consent
- Apply the same retention and deletion policies as clinical imaging data

---

## 6. Reporting Issues and Misuse

If you believe TRIBE v2 or this skill is being misused, or if you discover a vulnerability or ethical concern:

- **TRIBE v2 issues**: Open an issue on https://github.com/facebookresearch/tribev2
- **Meta Responsible AI**: https://about.meta.com/actions/safety/topics/safety/responsible-ai/
- **Institutional concerns**: Report to your institution's IRB or ethics board

If you are uncertain whether a use case is permitted under CC BY-NC 4.0:
1. Assume it is prohibited until confirmed otherwise
2. Consult the [CC BY-NC 4.0 license text](https://creativecommons.org/licenses/by-nc/4.0/legalcode)
3. For commercial edge cases, contact Meta Research directly

---

## Summary Card

Quick reference for field decisions:

| Question | Answer |
|----------|--------|
| Can I use this for a commercial ad campaign? | No — CC BY-NC 4.0 prohibits commercial use |
| Can I publish academic research using this? | Yes — with attribution and IRB compliance |
| Can I use this to improve accessibility tools? | Yes — with participant disclosure |
| Can I build a SaaS product on TRIBE v2 predictions? | No — commercial use; contact Meta for license |
| Do I need consent to predict responses to my own videos? | No, for internal non-commercial research |
| Do I need consent to deploy neural-optimized content to an audience? | Yes — disclose that neural prediction was used in content design |
| Can I use TRIBE v2 priors in an EEG BCI? | Yes — with population-average disclosure to users and IRB approval |
| Can I use this for children's content optimization? | Only with formal guardian consent framework and ethics review |
