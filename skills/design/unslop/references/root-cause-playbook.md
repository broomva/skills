# Root-cause playbook — fix the class, not the example

`unslop_survey.py` emits `roots[]`: each default attributed to the file that declares it, with the number
of downstream sites. The rule: **one edit at the root, zero edits at call sites** wherever the codebase
lets you. Editing forty `className`s to change a font is the failure mode this skill exists to kill
(`research/entities/pattern/fix-the-class-not-the-example.md`).

| Root kind | Where the default usually lives | Root fix | Call-site fix (only if no root exists) |
|---|---|---|---|
| **font** | `next/font/google` import in `layout.tsx` · `--font-sans` in `globals.css` · `fontFamily` in `tailwind.config` · `<link>` to Google Fonts · `+layout.svelte` | Decide the face in DESIGN.md → self-host (`@font-face` / `next/font/local`, woff2, `font-display`, `size-adjust` fallback) → change the ONE declaration → delete the Google Fonts link | replace per-element `font-family` with the token |
| **icons** | `lucide-react` imports across components; a second library sneaking in | Pick one system in DESIGN.md (stroke, sizes 16/20/24) → remove the second library → if Lucide stays, *say so* | wrap in one `<Icon>` component so the library is a single import |
| **color** | hex literals in components; `bg-[#…]`; Tailwind palette names (`purple-500`) used as brand | Semantic tokens in `globals.css` (`--color-ink/paper/accent/…`, OKLCH) + tailwind theme mapping → components use roles only | replace literal → token |
| **radius** | mixed `rounded-*` per component | ≤4 tokens: control / card / dialog / pill; theme `borderRadius` mapped to them | replace arbitrary radii → nearest token |
| **shadow / elevation** | `shadow-lg` everywhere; glow halos; thin border + wide shadow | ≤5 levels, one vocabulary (border *or* shadow), offset + soft blur, hue-tinted; a `--shadow-*` set | replace ad-hoc shadows → level token |
| **gradient / glass / orbs / dot grid** | hero section, `bg-gradient-to-*`, `backdrop-blur` on cards, `radial-gradient` blobs, `bg-[radial-gradient(...)]` grid | Decide the *visual world* (impeccable `new-work`); gradients/glass only where the world earns them; cards matte; dialogs/palettes may frost | delete the decoration; do not "soften" it |
| **motion** | `transition-all`, `animate-bounce`, framer on every section, no reduced-motion | One easing set + duration bands as tokens; `prefers-reduced-motion` block at the root stylesheet; one authored moment per surface | remove scattered entrances |
| **copy voice** | em dashes, emoji, ✓, "it's not X, it's Y", eyebrows, buzzwords in JSX text and content files | Write the voice paragraph in PRODUCT.md (sentence case, verb+noun, plain) → rewrite copy files/i18n messages once → components read strings | rewrite inline strings |
| **template structure** | hero → 3 feature cards → 3 tiers → testimonials → CTA | Derive structure from what the product *does* (impeccable `shape` / `new-work`); cards are the lazy container | — |
| **legal** (class D) | no `/terms`, `/privacy`; footer links to `#` | Add real routes **from a human/legal owner's text**; footer links; never generate policy text as if it were real | — |
| **states** (class D) | `fetch` with no loading/error/empty | Route-level `loading.tsx`/`error.tsx` (Next) or `{#await}` (Svelte) + Skeleton/aria-busy per async component; ≥500ms delay before showing; error names problem + recovery and preserves input | — |
| **product evidence** (class D) | stock/unsplash, placeholder screenshots, no video | Capture the real product (Playwright screenshots of real states, a 20s screen recording); if there is no product yet, say "coming" honestly rather than fake it | — |
| **placeholders / claims** (class D) | lorem, John Doe, Acme, 99.9%, 10,000+ users, testimonials with no photos | Real content or nothing; metrics only with a source; testimonials only with name + role + permission | — |

## Order of operations (why root first)

1. **Direction** (DESIGN.md / PRODUCT.md) — without it every fix is a coin flip toward a different default.
2. **Tokens** (font, color, radius, shadow, easing) — one edit each, cascades to every surface.
3. **Structure + copy** — page-level, per surface.
4. **States + legal + evidence** — the class-D work; needs the human for the parts that must be true.
5. **Render + gate** — the floor is checked on the *built* result, not the intention.

## Anti-rationalizations

| Excuse | Reality |
|---|---|
| "I'll just fix the 12 components that use Inter." | The 13th will use it tomorrow. Change the declaration; the components never knew the face. |
| "The gradient looks fine here." | If the axis was free and you reached for the default, you weren't deciding. Rewrite the element, don't soften it. |
| "I'll generate a privacy policy so the gate passes." | That converts a class-D tell into a class-C one (fake content). The gate WARNs on legal for a reason: it needs a human owner. |
| "Skeletons are overkill for this app." | The check is *presence of designed states*, and the threshold is 500ms before showing. A flash is worse than nothing; nothing is worse than a designed state. |
| "The tell list says no Lucide, so switch icon sets." | The list detects, it doesn't ban. Keep Lucide and *state the decision*; the gate reads DESIGN.md. |
