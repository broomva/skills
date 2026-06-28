# Google Stitch Integration

Google Stitch is a free AI-native UI design platform for rapid "vibe design" — describe a goal, feeling, or inspiration, and generate high-fidelity interfaces.

## Setup

### Skills (Agent Knowledge)

```bash
# Install all 7 skills globally
npx skills add google-labs-code/stitch-skills --yes --global

# Or individual skills
npx skills add google-labs-code/stitch-skills --skill stitch-design --global
npx skills add google-labs-code/stitch-skills --skill design-md --global
npx skills add google-labs-code/stitch-skills --skill stitch-loop --global
npx skills add google-labs-code/stitch-skills --skill enhance-prompt --global
npx skills add google-labs-code/stitch-skills --skill react-components --global
```

### MCP Server

```bash
# Interactive setup wizard
npx @_davideast/stitch-mcp init

# Or manual configuration (.claude/mcp.json)
{
  "mcpServers": {
    "stitch": {
      "command": "npx",
      "args": ["@_davideast/stitch-mcp", "proxy"],
      "env": {
        "STITCH_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### SDK (Programmatic Access)

```bash
npm install @google/stitch-sdk
```

```typescript
import { stitch } from "@google/stitch-sdk";

const project = stitch.project("your-project-id");
const screen = await project.generate("A login page with dark glass theme");
const html = await screen.getHtml();
const image = await screen.getImage();

// Edit existing screen
await screen.edit("Make the button larger and add a glow effect");

// Generate variants
const variants = await screen.variants("Try different color schemes", {
  variantCount: 3,
  creativeRange: "EXPLORE", // REFINE | EXPLORE | REIMAGINE
  aspects: ["COLOR_SCHEME", "LAYOUT"]
});
```

### API Key

1. Go to https://stitch.withgoogle.com
2. Click profile icon → Stitch Settings → API Keys
3. Click "Create Key" — copy immediately (shown once)
4. Set: `export STITCH_API_KEY="your-key"` (add to `.zshrc`)

## Available Skills

| Skill | Purpose |
|-------|---------|
| `stitch-design` | Unified entry point: prompt enhancement + screen generation |
| `stitch-loop` | Multi-page website generation from a single prompt |
| `design-md` | Analyze Stitch project → generate DESIGN.md |
| `enhance-prompt` | Transform vague UI ideas into optimized Stitch prompts |
| `react-components` | Convert Stitch screens → React component systems |
| `remotion` | Generate walkthrough videos from Stitch projects |
| `shadcn-ui` | shadcn/ui integration guidance |

## MCP Server Tools

| Tool | Purpose |
|------|---------|
| `list_projects` / `get_project` | Manage Stitch projects |
| `list_screens` / `get_screen` | Access screen data |
| `generate_screen_from_text` | Create new screens from prompts |
| `fetch_screen_code` | Download raw HTML |
| `fetch_screen_image` | Download screenshots |
| `extract_design_context` | Extract "Design DNA" (fonts, colors, layouts) |
| `create_project` | Create new workspace |

## Vibe Design Methodology

Instead of wireframes, start with one of these:

- **A goal:** "increase conversion on our pricing page"
- **A feeling:** "calm and minimal, like a meditation app"
- **An inspiration:** "premium and minimalist, like Stripe's website"
- **A persona:** "playful and colorful, targeted at Gen Z"

Stitch generates multiple high-fidelity directions — not sketches.

### Generation Models

| Model | Use Case |
|-------|----------|
| Gemini 3 (default) | Standard generation |
| Gemini 2.5 Pro | Maximum fidelity |
| Gemini 2.5 Flash | Speed over quality |

## DESIGN.md Generation Pipeline

Using the `design-md` skill:

1. **Retrieval** — Fetch project screens and HTML via Stitch MCP
2. **Extraction** — Identify tokens: colors, typography, spacing, components
3. **Translation** — Convert CSS/Tailwind values into natural design language
4. **Synthesis** — Generate DESIGN.md in five-section semantic format
5. **Alignment** — Verify compliance with Stitch prompting principles

## Integration with DESIGN.md

### Applying DESIGN.md to Stitch Generation

When generating with Stitch, include DESIGN.md context in prompts:

> "Design a dashboard with the Arcan Glass aesthetic — dark translucent surfaces with
> 275-hue blue-purple undertone, AI Blue (#0066ff) primary accents, glass-morphism cards
> with backdrop blur, CalSans headings over Geist body text."

### Extracting DESIGN.md from Stitch

1. Design screens in Stitch using vibe design
2. Run `design-md` skill to analyze screens
3. Agent extracts tokens and synthesizes DESIGN.md
4. DESIGN.md travels to Pencil/Figma/code as the portable contract

## Export Options

- **HTML/CSS** — Clean, production-ready code
- **Figma** — Editable layers with proper Auto Layout
- **Screenshot** — High-resolution PNG for reference

## Free Tier Limits

- 350 standard generations/month
- 50 experimental generations/month
- Full MCP server access
- No credit card required
