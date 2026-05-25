# /blog-post — Full-Stack Content Production Skill

Turn a topic into a complete publishing package: long-form post + platform-native social adaptations + multimedia assets.

## What It Does

Given a topic, idea, or content brief, this skill produces a structured content package under `/broomva/posts/` containing:

| Output | Format | Platform |
|--------|--------|----------|
| Long-form blog post | `.mdx` / `.md` | broomva.tech, Substack, Medium |
| X single post | `.md` | X/Twitter |
| X thread (5-8 tweets) | `.md` | X/Twitter |
| LinkedIn post | `.md` | LinkedIn |
| Instagram carousel | `.md` + slide specs | Instagram |
| Instagram reel script | `.md` | Instagram |
| Hero image + social cards | `.png` prompts | All platforms |
| Audio narration | `.mp3` script | broomva.tech |
| Video composition | `.mp4` script | Blog + social |
| GIF preview | `.gif` concept | Blog |
| Distribution strategy | `.md` | Cross-platform |

## Quick Start

```
/blog-post "Building an Agent OS in Rust" — developers, educate, provocative tone
```

## Compounding Skills

This skill orchestrates — it delegates to:
- `/content-creation` — storytelling, visual strategy, social patterns, AI generation
- `/deep-research` — multi-source research when needed
- `/agent-browser` — screenshots and reference extraction
- `/pencil` — carousel design, social cards
- `/remotion-best-practices` — video composition
- `/arcan-glass` — BroomVA brand styling

## Output Structure

```
/broomva/posts/{YYYY-MM-DD}-{slug}/
├── README.md, brief.md, research.md, outline.md
├── broomva-tech-post.mdx (or substack-post.md)
├── x-post.md, x-thread.md, linkedin-post.md
├── instagram-post.md, instagram-reel.md
├── media/ (prompts + generated assets)
└── strategy/ (audience, platform, distribution, CTA)
```

## Installation

```bash
npx skills add broomva/blog-post
```

## Skill Structure

```
blog-post/
├── SKILL.md              — Skill definition (pipeline, phases, agent behavior)
├── README.md              — This file
├── references/            — Deep-dive guides loaded on demand
│   ├── content-brief-intake.md
│   ├── angle-selection.md
│   ├── platform-adaptation.md
│   ├── multimedia-production.md
│   ├── quality-checklist.md
│   └── output-structure.md
├── templates/             — Reusable templates for each output file
│   ├── brief.md, broomva-tech-post.mdx, substack-post.md
│   ├── x-post.md, x-thread.md, linkedin-post.md
│   ├── instagram-post.md, instagram-reel.md
│   ├── distribution-plan.md, media-prompts.md
└── examples/              — Complete example output package
    └── 2026-03-20-agent-os-launch/
```
