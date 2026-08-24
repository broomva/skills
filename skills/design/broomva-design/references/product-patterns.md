# Product patterns

Use this reference to translate the Broomva foundation into the product's actual domain. These patterns are composition guidance, not rigid templates.

## Universal framing

Before composing a surface, name:

1. The user's primary job.
2. The product objects they recognize.
3. The decision or action the surface should enable.
4. The information that must remain visible while they act.
5. The platform conventions users already expect.

Keep the visual foundation stable while changing density, hierarchy, and components to fit those answers.

## Commerce and transactions

- Make product identity, price, availability, fulfillment, and the next purchase action unambiguous.
- Use matte cards for browsable collections; do not make every product tile a decorative glass object.
- Keep cart and checkout summaries close to the action they explain.
- Use functional green, amber, and red for actual order or payment outcomes, always paired with text.
- Preserve trust: disclose totals, recurring terms, inventory constraints, and destructive actions before commitment.

Typical objects: products, variants, collections, carts, orders, payments, subscriptions, reservations.

## Editorial, knowledge, and media

- Give reading surfaces a comfortable `640–768px` measure and let media expand only when it carries meaning.
- Use typography and rhythm before container chrome. Long-form content should not become a stack of cards.
- Keep navigation quiet and preserve location through breadcrumbs, collection context, or a compact rail.
- Use Cal Sans selectively for a publication or feature title, never for dense body copy.
- Treat metadata, citations, transcripts, and related content as supporting structure, not decorative noise.

Typical objects: articles, notes, documents, collections, authors, media, chapters, sources.

## Analytics, monitoring, and operations

- Lead with the decision the data supports, not the number of charts available.
- Use broad canvases for comparison while preserving a clear reading order and keyboard traversal.
- Keep filters, date ranges, units, freshness, and definitions visible near the data they modify.
- Do not encode a series or state by color alone. Pair hue with labels, shapes, patterns, or direct annotation.
- Prefer tables when exact comparison matters and charts when shape or change matters.

Typical objects: metrics, dimensions, events, alerts, cohorts, reports, resources, incidents.

## Onboarding, accounts, and settings

- Present one coherent decision group at a time and show the effect of changes before saving when risk is meaningful.
- Keep labels persistent; placeholder text never substitutes for field labels.
- Separate reversible preferences from security, billing, permissions, and destructive actions.
- Use progress only when a real bounded sequence exists. Name steps instead of inventing percentages.
- Make saved, unsaved, failed, and permission-limited states explicit.

Typical objects: profiles, organizations, memberships, permissions, integrations, preferences, plans.

## Communication and collaboration

- Keep conversation or activity content readable and preserve authorship, time, delivery state, and reply context.
- A persistent input may use the feature radius and earned elevation when it is the product's focal control.
- Use presence and unread indicators sparingly; do not turn every live signal into glow.
- Keep attachments, mentions, reactions, moderation, and destructive actions accessible without hover-only controls.
- Distinguish system events from human-authored content through structure and copy, not arbitrary color.

Typical objects: messages, threads, channels, participants, files, calls, notifications.

## Agentic work

Load `agentic-work.md` only when autonomous or long-running work is a primary product object. The extension adds canonical work states, receipts, Undertow, tidepool, lifecycle rails, and human-intervention patterns without changing the foundation.

## New domains

For domains not listed here, map recognizable product objects to the same foundation roles. Add a domain extension only when at least three recurring compositions cannot be expressed clearly through existing semantics. A domain extension may add vocabulary, components, or motion; it may not redefine the core palette, type scale, spacing ladder, elevation model, or accessibility baseline.
