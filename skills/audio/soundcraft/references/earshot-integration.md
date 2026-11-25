# Earshot integration

Earshot adds optional local CPU perceptual evidence after the deterministic checks. Install a reviewed revision in a separate environment using its upstream instructions. Listening commands can download CLAP and AudioSet AST models on first use. Record the Earshot revision with results and consult its current help for command options. [Earshot documentation](https://github.com/Leonxlnx/earshot#readme).

```sh
earshot describe candidate.wav
earshot match candidate.wav "close-miked wooden switch click"
earshot realness candidate.wav
```

Describe a dry cue or short region. Give CLAP a concrete acoustic description and compare it with nearby confusions, such as a plastic toggle or a metal latch. Use the AudioSet tags as additional clues. Very short cues and dense mixes can make these scores unstable.

A high `p_real` is a classifier score. Keep the recording's actual provenance and license independently. A synth can score well and a field recording can score poorly. Goodhart's law applies to both `p_real` and CLAP. Repeatedly tuning against one score can lift the number while degrading the attack, tail or fit to picture. Compare against a small set of licensed references, inspect the envelope and spectrum, and get a blind human audition when sound quality is a release criterion.

Keep model observations out of the CI gate. Log which regions were evaluated and distinguish source provenance, model observations, deterministic measurements and a person's audition. Leave model-dependent observations absent when the optional tool is unavailable.

[earshot](https://github.com/Leonxlnx/earshot) and [real-sound](https://github.com/Leonxlnx/earshot/tree/main/skills/real-sound) are MIT licensed, Copyright (c) 2026 Leon Lin. [Upstream license](https://github.com/Leonxlnx/earshot/blob/main/LICENSE).
