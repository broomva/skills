# Figma MCP Reference

Figma is the industry-standard design tool with multiple MCP server options for agent integration.

## MCP Server Options

### Official Figma MCP (Recommended)

Hosted by Figma — no local installation required.

```bash
# Claude Code setup
claude mcp add --transport http figma https://mcp.figma.com/mcp

# Or via plugin
claude plugin install figma@claude-plugins-official
```

**Auth:** OAuth via browser (no personal access token needed)
**Rate limits:** Dev/Full seats on paid plans get Tier 1 API limits; free/view seats get 6 calls/month

**Tools (13):**

| Tool | Purpose |
|------|---------|
| `get_design_context` | Extract layout/styling for frames. Default: React + Tailwind. Configurable to Vue, HTML+CSS, iOS, etc. |
| `generate_figma_design` | Capture live web UI and import as editable Figma layers |
| `get_variable_defs` | Read variables/styles (colors, spacing, typography) |
| `get_code_connect_map` | Map Figma components → codebase components |
| `add_code_connect_map` | Create new component mappings |
| `get_code_connect_suggestions` | AI-detect mapping suggestions |
| `send_code_connect_mappings` | Confirm/finalize mappings |
| `get_screenshot` | Visual snapshot of selection |
| `create_design_system_rules` | Generate agent-readable design rules |
| `get_metadata` | Sparse XML of layer structure (for large designs) |
| `get_figjam` | FigJam diagram metadata + screenshots |
| `generate_diagram` | Create FigJam from Mermaid/natural language |
| `whoami` | Authenticated user info |

### Framelink (Community, Most Popular)

13,800+ stars. Compresses Figma API response by ~90% for better LLM accuracy.

```bash
claude mcp add figma-framelink -- npx figma-developer-mcp --figma-api-key=YOUR_KEY
```

**Tool:** `get_figma_data(url)` — takes a Figma URL, returns compressed design context

### TalkToFigma (Bidirectional Read/Write)

6,500+ stars. Requires Figma Desktop plugin + WebSocket relay.

**40+ tools** including: create shapes/frames/text, set fill/stroke, manage auto-layout, clone nodes, export images, bulk text replacement.

### Figma Console MCP

1,100+ stars. 63+ tools with full read+write, variable management, component instantiation, visual debugging.

## Code Connect

Bridges Figma components to codebase components. The key differentiator for production-quality agent output.

**Supported frameworks:** React, React Native, HTML (Angular, Vue), SwiftUI, Jetpack Compose, Storybook

**Workflow:**
1. `get_code_connect_suggestions` — auto-detect Figma → code component mappings
2. Review and confirm suggestions
3. `get_code_connect_map` — agent uses real components instead of generating from scratch

**Requires:** Organization or Enterprise plan with Full Design or Dev Mode seat

## Design Tokens Pipeline

### Figma Variables API
- GET local/published variables, POST to create/update/delete
- Supports color, number, string, boolean types
- Multiple modes (light/dark themes)
- **Enterprise plan required** for API access

### Export Flow
```
Figma Variables
    → REST API / lukasoppermann plugin
    → DTCG JSON format ($value, $type, $description)
    → Style Dictionary transform
    → CSS custom properties / SASS / iOS / Android
```

### DTCG Token Types
- **Primitive:** color, dimension, fontFamily, fontWeight, duration, cubicBezier, number
- **Composite:** shadow, border, gradient, typography, transition, strokeStyle
- **References:** `{group.token}` syntax for aliases

## Agent Workflow with Figma

### Design-to-Code (Read)
1. Receive Figma frame URL from designer
2. `get_design_context(url)` → structured layout/styling data
3. `get_code_connect_map(url)` → map to existing codebase components
4. `get_variable_defs(url)` → extract design tokens
5. Generate production code using DESIGN.md tokens + Figma structure + mapped components

### Code-to-Design (Write)
1. Build feature in code, render locally
2. `generate_figma_design(url)` → capture rendered UI as editable Figma layers
3. Designer reviews and refines in Figma
4. Agent picks up changes for next iteration

### Design System Rules
1. `create_design_system_rules(url)` → generate rules file
2. Save to `.cursor/rules/` or project root
3. Agent references rules during all code generation

## Best Practices

1. **Work one frame at a time** — paste individual frame URLs, not entire pages
2. **Use Code Connect first** — map components before generating code
3. **Specify your framework** — "Generate in React + Tailwind" not just "generate code"
4. **Keep screenshots enabled** — visual validation alongside structured data
5. **Export tokens, don't hardcode** — use the Variables API → Style Dictionary pipeline
6. **Link dev resources** — connect Figma nodes to GitHub PRs, Jira tickets, Storybook
