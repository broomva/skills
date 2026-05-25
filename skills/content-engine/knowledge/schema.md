# Content Engine Schema

> The LLM is the compiler: `raw/` is source code, `compiled/` is executable.
>
> Inspired by Karpathy's LLM Wiki concept -- knowledge files that are written for
> machines to read and act on, not humans to browse. Every compiled file is a
> prompt-ready artifact that an AI tool can consume directly.

## 1. Compilation Model

The content engine treats brand identity, character consistency, and scene
direction as **source code** that gets compiled into **tool-executable prompts**.

```
knowledge/
  raw/                          # Source code (human-authored)
    brand-assets/               #   Mood boards, color swatches, reference images
    character-refs/             #   Face photos, pose refs, LoRA training sets
    style-inspiration/          #   Aesthetic references, competitor screenshots
    scene-briefs/               #   Freeform scene descriptions, client briefs
  compiled/                     # Executable (LLM-compiled)
    brands/                     #   One .md per brand identity
    characters/                 #   One .md per character
    styles/                     #   One .md per style preset
```

### Compilation Flow

```
raw/brand-assets/broomva/       ──┐
raw/style-inspiration/broomva/  ──┤──▶  compiled/brands/broomva.md
templates/brand-dna.md          ──┘

raw/character-refs/carlos/      ──┐
templates/character-sheet.md    ──┤──▶  compiled/characters/carlos.md
compiled/brands/broomva.md      ──┘     (inherits brand context)
```

Each compiled file is self-contained: a generation tool should be able to produce
correct output by reading ONLY the compiled file, without needing to traverse
`raw/` at runtime.

## 2. Provenance Tracking

Every compiled file MUST include a frontmatter block that traces back to its
sources. This enables staleness detection and re-compilation.

```yaml
---
name: "Broomva"
type: brand-dna
compiled: "2026-04-07T14:30:00Z"
compiler_version: "0.1.0"
sources:
  - path: "raw/brand-assets/broomva/color-palette.png"
    sha256: "a1b2c3..."
    modified: "2026-04-01T10:00:00Z"
  - path: "raw/brand-assets/broomva/mood-board-v2.jpg"
    sha256: "d4e5f6..."
    modified: "2026-04-03T08:15:00Z"
  - path: "raw/style-inspiration/broomva/dark-glass-refs/"
    sha256: "directory:7a8b9c..."
    modified: "2026-04-05T12:00:00Z"
tools:
  - nano-banana-pro
  - soul-cinema
  - comfyui
template: "templates/brand-dna.md"
template_version: "1.0.0"
---
```

### Source Hash Rules

- **Files**: SHA-256 of file contents.
- **Directories**: SHA-256 of sorted concatenation of all file hashes within,
  prefixed with `directory:`.
- **External URLs**: Record the URL and fetch timestamp. No hash (use
  `url:<fetch_timestamp>` format).

### Re-compilation Triggers

When any source file's hash changes, the compiled output is considered stale.
The `sources[].modified` timestamps allow quick checks without re-hashing.

## 3. Compilation Triggers

### Manual (Current)

```bash
/content-engine compile --brand broomva
/content-engine compile --character carlos
/content-engine compile --all
```

The `/content-engine compile` command:
1. Reads the appropriate template from `templates/`.
2. Scans `raw/` for source materials matching the target.
3. Uses the LLM to synthesize source materials into template sections.
4. Writes the compiled output with full provenance frontmatter.
5. Validates the output against linting rules (see section 6).

### Hook-Based (Future — BRO-5xx)

When integrated with the bstack hook system:
- **Pre-generation hook**: Auto-recompile if staleness detected before any
  generation request.
- **Watch mode**: File-system watcher on `raw/` that marks compiled files as
  stale and optionally triggers re-compilation.
- **CI gate**: PR checks that verify all compiled files are fresh relative to
  their sources.

## 4. Template Inheritance

Templates define the structure of compiled files. They use `{placeholder}`
syntax for values the compiler fills in.

### Inheritance Chain

```
templates/brand-dna.md           Base brand template
  └─▶ compiled/brands/*.md      Compiled per-brand identity

templates/character-sheet.md     Base character template
  └─▶ compiled/characters/*.md  Compiled per-character sheet
       (inherits from parent brand via `brand_ref` field)

templates/scene-brief.md         Per-scene template
  └─▶ (used at generation time, not pre-compiled)
       (references both character + brand compiled files)

templates/campaign-plan.md       Multi-scene orchestration
  └─▶ (used at planning time)
       (references brand + multiple characters + multiple scene briefs)
```

### Inheritance Rules

1. **Brand is root**: Every character inherits a brand context. The character
   sheet's `brand_ref` field points to a compiled brand file.
2. **Characters are leaves**: Characters never inherit from other characters.
   They inherit from exactly one brand.
3. **Scenes reference, not inherit**: Scene briefs reference a character and
   brand but do not inherit their structure. They are ephemeral (used once per
   generation).
4. **Campaigns orchestrate**: Campaign plans reference multiple scenes. They
   are the only template that composes across multiple characters.

### Template Versioning

Templates include a `template_version` field in their frontmatter. When a
template changes:
- **Minor version bump** (1.0 -> 1.1): Compiled files remain valid but may
  benefit from re-compilation.
- **Major version bump** (1.x -> 2.0): All compiled files using this template
  MUST be re-compiled.

## 5. Tool-Specific Prompt Fragments

Each compiled file contains a `## Tool-Specific Prompts` section with
subsections for every supported generation tool. This is the core innovation:
the same brand identity produces different prompt text for different tools.

### Supported Tools

| Tool | Slug | Type | Primary Use |
|------|------|------|-------------|
| Nano Banana Pro | `nano-banana-pro` | Image gen (consistent characters) | Character portraits, product shots |
| Soul Cinema | `soul-cinema` | Video gen (cinematic) | Cinematic scenes, mood videos |
| Weavy | `weavy` | Image gen (stylized) | Social media graphics, illustrations |
| ComfyUI | `comfyui` | Image gen (workflow-based) | Complex compositions, LoRA-based |
| Gemini Imagen | `gemini-imagen` | Image gen (Google) | Blog illustrations, quick assets |
| Veo | `veo` | Video gen (Google) | B-roll, transitions |
| Remotion | `remotion` | Video composition (code) | Programmatic video, captions |
| LTX Video | `ltx-video` | Video gen (local) | Local video generation |

### Fragment Format

Each tool subsection follows this structure:

```markdown
### {tool_name}

**Positive prompt:**
{The exact positive prompt text to feed this tool, incorporating brand-specific
vocabulary, style descriptors, and technical parameters the tool expects.}

**Negative prompt:**
{Things to explicitly exclude — tool-specific negative prompt syntax.}

**Parameters:**
- resolution: {recommended resolution for this tool}
- guidance_scale: {if applicable}
- steps: {if applicable}
- model/checkpoint: {if applicable}
- lora: {if applicable, with weight}

**Notes:**
{Any tool-specific quirks, known issues, or tips for this brand/character
combination.}
```

### Fragment Compilation Rules

1. Each fragment is **self-contained** -- it does not reference other fragments
   or require the reader to look at another section.
2. Fragment vocabulary matches the tool's training data. Example: Nano Banana
   Pro uses face-embedding language; ComfyUI uses node/workflow language.
3. Negative prompts are tool-specific. Some tools have no negative prompt
   support; those sections are omitted.
4. Parameters reflect the brand's optimal settings for that tool, discovered
   through iteration and recorded in `raw/` notes.

## 6. Linting Rules

The content engine linter validates compiled files for structural correctness,
freshness, and cross-reference integrity.

### Structural Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `S001` | error | Frontmatter must include `name`, `type`, `compiled`, `sources`, `tools` |
| `S002` | error | `type` must be one of: `brand-dna`, `character-sheet`, `style-preset` |
| `S003` | error | `sources` array must not be empty |
| `S004` | error | `compiled` must be a valid ISO 8601 timestamp |
| `S005` | warning | `compiler_version` should be present |
| `S006` | error | Every tool listed in `tools` must have a matching `### {tool}` subsection |
| `S007` | warning | Tool subsections should follow the fragment format (positive/negative/parameters) |

### Freshness Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `F001` | warning | Compiled file older than 30 days triggers staleness warning |
| `F002` | error | Compiled file older than 90 days is considered expired |
| `F003` | warning | Source file modified after compiled timestamp marks file as stale |
| `F004` | info | Re-compilation recommended when template version has minor bump |
| `F005` | error | Re-compilation required when template version has major bump |

### Cross-Reference Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `X001` | error | Character `brand_ref` must point to an existing compiled brand file |
| `X002` | warning | Brand referenced by a character should list all tools the character uses |
| `X003` | error | Scene brief `character_ref` must point to an existing compiled character |
| `X004` | error | Scene brief `brand_ref` must point to an existing compiled brand |
| `X005` | warning | Campaign `character_refs` should all resolve to compiled characters |

### Orphan Detection

| Rule | Severity | Description |
|------|----------|-------------|
| `O001` | warning | Raw source file not referenced by any compiled file (orphaned source) |
| `O002` | info | Compiled file whose sources have all been deleted (orphaned compiled) |
| `O003` | warning | Template not used by any compiled file (orphaned template) |

### Running the Linter

```bash
/content-engine lint                    # Lint all compiled files
/content-engine lint --brand broomva    # Lint a specific brand
/content-engine lint --fix              # Auto-fix what can be fixed (timestamps, missing sections)
/content-engine lint --severity error   # Only show errors, suppress warnings/info
```

## 7. File Naming Conventions

- **Brands**: `compiled/brands/{slug}.md` where slug is lowercase kebab-case
  (e.g., `broomva.md`, `arcan-glass.md`).
- **Characters**: `compiled/characters/{slug}.md` (e.g., `carlos.md`,
  `broomva-avatar.md`).
- **Styles**: `compiled/styles/{slug}.md` (e.g., `dark-glass.md`,
  `neon-minimal.md`).
- **Raw sources**: `raw/{category}/{brand-or-character-slug}/` directories
  containing any file type (images, text, PDFs).

## 8. Compilation Idempotency

Running compilation twice with the same inputs MUST produce the same output
(same content, updated timestamp). This means:

- The compiler does not inject random elements.
- Tool-specific prompts are deterministic given the same source materials.
- The only field that changes between identical compilations is `compiled`
  timestamp.

If source materials change, the compiled output MUST change to reflect them.
The `sources[].sha256` hashes provide the mechanism to detect this.

## 9. Migration Path

### Phase 1 (Current) -- Manual Compilation
- Human writes raw materials in `raw/`.
- Human runs `/content-engine compile`.
- LLM reads raw materials + template, produces compiled file.
- Human reviews and commits.

### Phase 2 -- Semi-Automatic
- File watcher detects changes in `raw/`.
- System marks affected compiled files as stale.
- Human approves re-compilation.

### Phase 3 -- Fully Automatic
- Hook-based triggers auto-recompile on `raw/` changes.
- CI validates compiled files are fresh on every PR.
- Generation tools read compiled files directly without human intervention.
