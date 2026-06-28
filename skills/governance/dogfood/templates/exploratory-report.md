# Exploratory Dogfood Report: {APP_NAME}

> Produced by `/dogfood explore` (web-stack execution mode). The bstack Dogfood Plan's **Evidence** row references this file; the Dogfood Receipt's anti-rationalization check is "yes" when this report is non-trivial.
>
> Structure adapted from the dogfood skill in the agent-skills catalog (`~/.agents/skills/dogfood/templates/dogfood-report-template.md`).

| Field | Value |
|-------|-------|
| **Date** | {DATE} |
| **App URL** | {URL} |
| **Session** | {SESSION_NAME} |
| **Scope** | {SCOPE} |
| **Parent ticket** | {LINEAR_ID or PR #} |
| **Driver** | agent-browser session |

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| **Total** | **0** |

## Anti-rationalization receipt

| Check | Answer |
|---|---|
| Did I actually click the app like a user would? | yes / no |
| Multi-modal evidence captured (screenshots + console)? | yes / no |
| Deploy-state exercised (preview URL or production)? | yes / no |
| Session was non-trivial (≥5 issues attempted) OR end-to-end coverage of the changed surface? | yes / no |

## Issues

<!-- Copy this block for each issue. Interactive issues need video + step-by-step screenshots. Static issues only need a single screenshot — set Repro Video to N/A. -->

### ISSUE-001: {Short title}

| Field | Value |
|-------|-------|
| **Severity** | critical / high / medium / low |
| **Category** | visual / functional / ux / content / performance / console / accessibility |
| **URL** | {page URL where issue was found} |
| **Repro Video** | {path to video, or N/A for static issues} |

**Description**

{What is wrong, what was expected, what actually happened.}

**Repro Steps**

<!-- Each step has a screenshot. A reader should be able to follow visually. -->

1. Navigate to {URL}
   ![Step 1](screenshots/issue-001-step-1.png)

2. {Action — e.g. click "Settings" in the sidebar}
   ![Step 2](screenshots/issue-001-step-2.png)

3. {Action — e.g. type "test" in the search field and press Enter}
   ![Step 3](screenshots/issue-001-step-3.png)

4. **Observe:** {what goes wrong}
   ![Result](screenshots/issue-001-result.png)

---
