# Exploratory Issue Taxonomy

Reference for categorizing issues found during the `explore` mode of `/dogfood`. Loaded by the agent at the start of an exploratory session to calibrate what to look for and how to score severity.

> **Attribution**: severity levels, category structure, and exploration checklist adapted from the `dogfood` skill in the agent-skills catalog (~/.agents/skills/dogfood/references/issue-taxonomy.md). The original is targeted purely at web-app QA; this version is the bstack-composed shape — the same taxonomy is what populates the Dogfood Plan's *Evidence* row when the Driver is web-exploratory.

## Severity Levels

| Severity | Definition |
|----------|------------|
| **critical** | Blocks a core workflow, causes data loss, or crashes the app |
| **high** | Major feature broken or unusable, no workaround |
| **medium** | Feature works but with noticeable problems, workaround exists |
| **low** | Minor cosmetic or polish issue |

## Categories

### Visual / UI

- Layout broken or misaligned elements
- Overlapping or clipped text
- Inconsistent spacing, padding, or margins
- Missing or broken icons / images
- Dark mode / light mode rendering issues
- Responsive layout problems (viewport sizes)
- Z-index stacking issues (elements hidden behind others)
- Font rendering (wrong font, size, weight)
- Color contrast problems
- Animation glitches / jank

### Functional

- Broken links (404, wrong destination)
- Buttons or controls that do nothing on click
- Form validation rejecting valid input or accepting invalid input
- Incorrect redirects
- Features that fail silently
- State not persisted when expected (lost on refresh, navigation)
- Race conditions (double-submit, stale data)
- Broken search or filtering
- Pagination issues
- File upload / download failures

### UX

- Confusing or unclear navigation
- Missing loading indicators / feedback after actions
- Slow or unresponsive interactions (>300ms perceived delay)
- Unclear error messages
- Missing confirmation for destructive actions
- Dead ends (no way to go back or proceed)
- Inconsistent patterns across similar features
- Missing keyboard shortcuts or focus management
- Unintuitive defaults
- Missing or unhelpful empty states

### Content

- Typos or grammatical errors
- Outdated or incorrect text
- Placeholder or lorem ipsum content left in
- Truncated text without tooltip or expansion
- Missing or wrong labels
- Inconsistent terminology

### Performance

- Slow page loads (>3s)
- Janky scrolling or animations
- Large layout shifts (content jumping)
- Excessive network requests
- Memory leaks (page slows over time)
- Unoptimized images (large file sizes)

### Console / Errors

- JavaScript exceptions in console
- Failed network requests (4xx, 5xx)
- Deprecation warnings
- CORS errors
- Mixed content warnings
- Unhandled promise rejections

### Accessibility

- Missing alt text on images
- Unlabeled form inputs
- Poor keyboard navigation (can't tab to elements)
- Focus traps
- Insufficient color contrast
- Missing ARIA attributes on dynamic content
- Screen reader incompatible patterns

## Exploration Checklist (per page or feature)

1. **Visual scan** — annotated screenshot. Look for layout, alignment, rendering.
2. **Interactive elements** — click every button, link, control. Do they work? Is there feedback?
3. **Forms** — fill and submit. Test empty submission, invalid input, edge cases.
4. **Navigation** — follow all paths. Check breadcrumbs, back button, deep links.
5. **States** — empty, loading, error, full/overflow.
6. **Console** — check JS errors, failed requests, warnings.
7. **Responsiveness** — if relevant, test at different viewport sizes.
8. **Auth boundaries** — what happens when not logged in, with different roles.

## How this feeds back into the P11 contract

When `/dogfood explore` runs, every documented issue is one row of evidence for the parent Dogfood Plan's **Evidence** field. The issue report file path goes into the Plan's *Receipt anchor* row. The exploratory session output is the *empirical proof* that the work was exercised like a user would — the P11 invariant.

The dogfood **Receipt** at session end cross-references the exploratory report with the binary anti-rationalization check:

- "Did I actually click the app like a user would?" — **yes** if the exploratory session was non-trivial (≥5 issues attempted, even if 0 found in a polished app) or the session log proves end-to-end coverage of the changed surface.

## Cross-references

- `references/bstack-inheritance.md` — composition with the pre-existing dogfood (upstream attribution)
- `templates/exploratory-report.md` — the report template used by `explore` mode
- bstack `references/dogfood-patterns.md` Pattern B (Next.js) and Pattern A (Tauri+sidecar) — when exploratory mode is the right driver
