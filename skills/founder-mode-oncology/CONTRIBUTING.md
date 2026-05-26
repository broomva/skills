# Contributing to Founder Mode Oncology

Thank you for your interest in improving this skill. Contributions from clinicians, researchers, bioinformaticians, patients, and caregivers are especially valued.

## How to Contribute

### Improving References

The `references/` directory contains the detailed knowledge base. To improve an existing reference:

1. Fork this repository.
2. Edit the relevant file under `references/`.
3. Cite your sources -- peer-reviewed publications, FDA documents, or tool documentation.
4. Open a pull request with a clear description of what changed and why.

Do **not** modify `SKILL.md` directly unless the change is structural (e.g., adding a new pillar or section). `SKILL.md` summarizes the references; update the reference first, then propose a corresponding `SKILL.md` change if needed.

### Adding New Treatment Modalities

If a treatment category is missing (e.g., a new class of therapy, a novel diagnostic modality):

1. Add detailed content to the appropriate reference file, or create a new file under `references/` if no existing file fits.
2. Include: mechanism of action, clinical evidence, access pathway, combination compatibility, and monitoring approach.
3. Add links to relevant GitHub repositories, clinical trial registries (clinicaltrials.gov), or FDA databases where applicable.
4. Update `references/open-source-tools.md` if the modality involves new computational tools.

### Submitting Corrections

Medical knowledge evolves. If you find outdated information, incorrect dosing, withdrawn drugs, or factual errors:

1. Open an issue describing the error, citing the correct information and its source.
2. If you can fix it yourself, open a pull request instead.
3. Label corrections with the `correction` label if possible.

For urgent safety-related corrections (e.g., a listed drug combination is now known to be dangerous), open an issue with `[SAFETY]` in the title.

### General Guidelines

- **Be specific**: Include citations, tool versions, and links.
- **Keep the tone clinical**: This skill is used by AI agents assisting real decisions. Precision matters.
- **Preserve structure**: Follow the existing format of whichever file you edit.
- **One concern per PR**: Keep pull requests focused on a single topic.

## Issue Templates

When opening an issue, use one of these formats:

**Correction**:
- File affected: `references/_____.md`
- Current text (quote)
- Correct information
- Source / citation

**New content proposal**:
- Topic / modality
- Why it belongs in this skill
- Key references (2--3 links)

**Tool update**:
- Tool name and repository link
- What changed (new version, deprecated, superseded)
- Impact on the pipeline described in this skill

## Code of Conduct

Be respectful. This project exists to help people navigate cancer treatment. Contributions should prioritize accuracy, clarity, and patient benefit.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
