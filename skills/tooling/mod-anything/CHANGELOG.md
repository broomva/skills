# Changelog

All notable changes to the `mod-anything` skill. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the skill uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-05

### Added

- The loop: intake, recon, route ladder (data and config, sanctioned API, patch from inside,
  hooks and wires, reimplement), lab, vertical slice verified in the running original,
  stall breaker with re-rank, packaging, field note, publish check.
- `scripts/modlog.py`: the run journal and stall breaker. `fail` exits 3 on the third
  identical failure on a route. `note` scaffolds a field note; `lint-note --root` checks it is
  complete, that every evidence path cited under `## Verification` exists inside the tree
  that will ship, and that its single `Disclosure:` line is `none found` or `cleared` with a
  real date that has arrived.
- `scripts/publish_check.py`: a fail-closed filter before sharing. Only an allowlist of file
  types ships (source, docs, small data files, screenshots). It blocks binaries, captures,
  dependency folders, app and plugin bundles, well-known credential file names,
  secrets (gitleaks and built-in patterns), decompiler output, home paths, hardware
  addresses and deny-file terms, matched as written. It decodes nothing; it lists journals,
  evidence, fixtures, build output, images, SVGs and the types that usually embed encoded
  content (HTML, notebooks, plists, source maps) for a
  person to read.
- `scripts/recon_macos_app.py`: recon adapter for macOS `.app` bundles (stack, extension
  points, Electron fuses, protections, update channel, state folders, ranked routes).
- References: the ladder, the envelope (rules, legal summary, disclosure), the field-note
  format, and a macOS apps playbook.
- Examples: recon output for three apps, and a rung-2 Obsidian plugin with a scripted lab and
  evidence regenerated from synthetic fixtures. One field note from that run.
