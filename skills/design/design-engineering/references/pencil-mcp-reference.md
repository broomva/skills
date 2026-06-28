# Pencil MCP Reference

Pencil is an AI-native vector design tool that runs in your IDE (VS Code, Cursor) or as a standalone desktop app. Design files (`.pen`) are JSON, live in Git, and are read/written via a local MCP server.

## Architecture

```
Claude Code ← MCP Client → MCP Server (Pencil, local) → Design Canvas (WebGL)
```

No cloud dependency. The MCP server starts automatically when Pencil is open and auto-configures in `.claude.json`.

## MCP Tools (14 total)

### Context & Discovery

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `get_editor_state()` | Active editor, current selection, context | Always first — understand what's open |
| `open_document(path)` | Open .pen file or create new (`"new"`) | When no file is open |
| `batch_get(patterns, nodeIds)` | Read nodes by pattern match or IDs | Discover structure, read properties |
| `get_variables()` | Read variables and themes | Before designing — load token context |
| `get_guidelines(topic)` | Design rules for a topic | Before designing — load best practices |
| `get_style_guide_tags` | List available style guide tags | Before choosing aesthetic direction |
| `get_style_guide(tags, name)` | Get style guide by tags or name | Choose visual direction for new designs |

### Design Operations

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `batch_design(operations)` | Insert/copy/update/replace/move/delete/image | All design modifications |
| `set_variables(vars)` | Add/update variables and themes | Set design tokens from DESIGN.md |
| `find_empty_space_on_canvas(...)` | Find placement space in a direction | Before adding new frames |

### Validation

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `get_screenshot(nodeId)` | Visual snapshot of any node | After every major design step |
| `snapshot_layout(...)` | Computed layout rectangles | Verify positioning, detect clipping |
| `search_all_unique_properties(...)` | Audit property values across trees | Find leaked raw values for tokenization |
| `replace_all_matching_properties(...)` | Bulk-replace property values | Tokenize raw values, global refactors |

## batch_design Operation Syntax

Max **25 operations per call**. Sequential execution; rollback on error.

### Insert
```
foo=I("parentId", { type: "frame", layout: "vertical", width: 390, height: 844, fill: "#1a1a2e" })
```
- Always needs a parent (`"document"` for top-level)
- Never specify `id` — auto-generated
- Returns binding for reference in later operations

### Copy
```
bar=C("nodeId", "parent", { positionDirection: "right", positionPadding: 100 })
```
- Copies a node. If reusable, creates a connected `ref` instance
- Use `descendants` map to override child properties (do NOT use separate `U()` on descendants)

### Replace
```
baz=R("instanceId/childId", { type: "text", content: "New content" })
```
- Replaces a node entirely. Ideal for swapping parts of component instances

### Update
```
U("nodeId", { content: "Updated text", fill: "#0066ff" })
U(foo+"/childId", { fontSize: 24 })
```
- Modifies existing properties. Cannot change `id`, `type`, or `ref`
- Use slash-separated paths for nested component instances

### Delete
```
D("nodeId")
```

### Move
```
M("nodeId", "newParent", 2)
```
- Moves to new parent at specified index

### Generate Image
```
G("nodeId", "ai", "modern glass office with blue ambient lighting")
G("nodeId", "stock", "coffee shop interior")
```
- Applies image fill to frame/rectangle. Two modes: `"ai"` (generated) or `"stock"` (Unsplash)
- There is NO `image` node type — images are fills on frames/rectangles

## .pen Node Types

| Type | Purpose |
|------|---------|
| `frame` | Primary container (like `div`), supports layout |
| `group` | Groups children without layout behavior |
| `rectangle` | Shape primitive |
| `ellipse` | Circle/oval shape |
| `line` | Line segment |
| `polygon` | Multi-sided shape |
| `path` | SVG-like vector path |
| `text` | Text content with typography |
| `note` | Annotations for AI context |
| `connection` | Lines connecting nodes |
| `icon_font` | Material Icons |
| `ref` | Component instance (references a `reusable: true` node) |

## Layout System

Flexbox-like layout on frames:

| Property | Values | Default |
|----------|--------|---------|
| `layout` | `"vertical"` / `"horizontal"` / `"none"` | `"none"` (absolute) |
| `gap` | Number (px) | 0 |
| `padding` | Number or per-side | 0 |
| `justifyContent` | `"start"` / `"center"` / `"end"` / `"space_between"` / `"space_around"` | `"start"` |
| `alignItems` | `"start"` / `"center"` / `"end"` | `"start"` |

### Sizing Behaviors

- Fixed pixel value: `width: 390`
- Fit content: `width: "fit_content"`
- Fill container: `width: "fill_container"` (optionally with min: `"fill_container(500)"`)

## get_guidelines Topics

| Topic | Use When |
|-------|----------|
| `design-system` | Building SaaS apps, dashboards, reusable components |
| `code` | Generating code from .pen files |
| `table` | Working with data tables |
| `tailwind` | Tailwind v4 CSS implementation |
| `landing-page` | Promotional websites, marketing pages |
| `mobile-app` | Mobile apps or mobile-responsive websites |
| `web-app` | Web applications |
| `slides` | Presentation slides |

## Variables and Themes

Variables are reusable design tokens. Types: **color** (hex), **number**, **string**, **boolean**.

- Reference with dollar-prefix: `"$color.background"`
- Theme support: variables can have different values per theme (light/dark)
- `set_variables` to create from DESIGN.md tokens
- `get_variables` to extract for CSS generation

## Best Practices

1. **Start with `get_editor_state()`** — always know your context
2. **Load guidelines** before designing (`get_guidelines` for your project type)
3. **Set variables first** — import DESIGN.md tokens via `set_variables`
4. **Screenshot after every major step** — visual validation prevents drift
5. **Max 25 ops per batch_design** — split large designs by logical sections
6. **Realistic content** — never use "Lorem ipsum" or placeholder text
7. **Semantic layer names** — "UserAvatarImage" not "Rectangle 12"
8. **Desktop-first at 1440px** — unless mobile-first is specified
9. **Mark reusable patterns** — `reusable: true` for component library building
10. **Structure first, content second** — build frame hierarchy before adding text and images
