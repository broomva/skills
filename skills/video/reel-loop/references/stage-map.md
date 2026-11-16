# Stage map: what does each stage, here and elsewhere

Surveyed on 2026-11-16 for BRO-3795. Every URL below was opened that day. Tags:

- **HIGH:** the primary README, code or docs were read.
- **MED:** vendor docs or a secondary summary.

Stars and activity are as of the survey date.

## The reference: what the reel shows

`@davidmadrazo.ia`, Instagram reel `DfpHUNFiKke`, 2026-11-12, 56 s, Spanish. Read
from 11 frames and a whisper.cpp Spanish transcript (HIGH for what is on screen).
The tool on screen is called "content-os". A Claude notification titled "Turno de
madrugada" fires at 03:55. The panels shown, in order:

| Panel | On screen | Loop stage |
|---|---|---|
| Descubridor | Reel grid, "3.754 reels" seen | 1 Sense |
| Elegidos | Creator, Views, "Su normal", "× su normal". 1.1 M vs 2.1 K normal | 2 Outliers |
| Desmontaje | Transcript plus shots cut at 1.5 s … 34.5 s, the first one labeled GANCHO | 3 Deconstruct |
| guion-maquina.md | HOOK / STRUCTURE / BODY / CTA sections; "método viral: 72 reglas solo para el gancho" (the narration says 120+) | 4 Script |
| Montaje · reel 53 | 6 scenes plus "voz de David" waveform | 5 Produce |
| Agenda | 14 published this week, "Publicar en Instagram" | 8 Publish |
| Pruebas | "otro gancho / otro color / otro encuadre" | 10 Trial |
| Reels de hoy | 5 checks, then **APROBAR** | 7 Approve |
| Closing shot | Comment "MÁQUINA" to get a DM | DM funnel (out of scope) |

The creator's paid product (`drazo-studio`, server-side, license key) is probably
what the reel shows. That is **inference**: neither repo names "content-os".

## Per-stage options

| Stage | This skill composes | External, best-of-breed | Notes |
|---|---|---|---|
| 1 Sense | Business Discovery `view_count`; a person's browser; pasted counts | `apify/instagram-reel-scraper` (paid, public reels, MED); `instaloader` (MIT, HIGH; 429s and checkpoints land on the logged-in account) | Official API cannot discover accounts by niche, so seed `niche.tsv` by hand. |
| 2 Outliers | `reel_loop.py outliers` (leave-one-out median) | `crecer` `virales.py`: median including the reel, bar ×4, min 20 000, 45 days (HIGH, read); AttentionOS "scored as `x` against that account's rolling median" (HIGH, README) | Many tools use views ÷ followers instead. That rule measures a different thing; do not mix them. |
| 3 Deconstruct | `video_ingest.py` (contact sheet + transcript) + `script-card.md` | `w-avw/instagram-viral-reels-research-claude-skill` (MIT; frames + Whisper, outlier ≥700 k and ≥5× followers); HyperFrames `/reverse-any-video` (paid tier) | Skip the download when the owner disabled downloads. |
| 4 Script | `script-card.md` + `rules/hooks.md` + `humanizer`/`unslop` | `crecer` `ganchos`/`guion`; AttentionOS scripting with deterministic validators; `vyralcontent/content-skills`, `rediumvex/viral-hooks-skill` | The rulebook is the account's own, grown from its winners, not a bought "viral method". |
| 5 Produce | `omnivoice` (local clone), `content-engine`, `video-cut`, `brainrot-for-good` captions | `hassancs91/claude-faceless-shorts-creator` (MIT, Remotion + ElevenLabs word-synced captions); `heygen-com/hyperframes` (Apache-2.0, HTML → video for agents; skills send telemetry); Remotion `createTikTokStyleCaptions`; `gyoridavid/short-video-maker` (MCP, English-only, stale) | Voice cloning needs consent; ElevenLabs' use policy requires it explicitly. |
| 6 QC | `content-engine/scripts/check_vertical_layout.py` | — | |
| 7 Approve | the card's `approval` block, checked by the gate | AttentionOS approvals: "At `review_all`, every post waits for approval. At `review_key`, only campaign posts wait" (docs/modules/publishing.md) | Ours holds every post and binds the approval to the sha256 of the rendered file. It cannot prove who wrote the approval. |
| 8 Publish | `reel_loop.py publish`: gate, resumable container, rupload of the gated bytes, poll, `media_publish` | Postiz (AGPL, REST + hosted MCP), Upload-Post (own Meta app), Blotato, Ayrshare — all MED | All of them pass trial settings through to Meta's `trial_params` (MED, vendor docs). None documents a way to graduate a MANUAL trial. They upload whatever file or URL they are given, so `reel-loop` does not route through them. |
| 9 Measure | Graph API media insights | AttentionOS analytics (Zernio / Graph API) | |
| 10 Trial | `reel_loop.py winners` → 3 variants with `SS_PERFORMANCE` | AttentionOS `trial-reels` (9 variants/day); `artemnovitckii/claude-editing-skills` `/trial-reels` (3 variants, render only) | Contested: `ericosiu/ai-marketing-skills` `trial-reel-distribution` reposts the winner unchanged ("Variant testing answers the wrong question"). Run it as an experiment. |
| DM funnel | out of scope | AttentionOS `community`; ManyChat | Meta: one private reply per comment, within 7 days. |

## Verified URLs

- https://github.com/davidmadrazo/crecer-instagram (MIT; 9 Claude Code skills; "No publica nada sin tu sí")
- https://github.com/evanbaker315/AttentionOS (MIT; 255★; pushed 2026-11-12; "research → strategy → scripting → (human films) → editing → publishing → community → analytics")
- https://github.com/w-avw/instagram-viral-reels-research-claude-skill
- https://github.com/shafeela-bot/ig-radar-plugin (no license file)
- https://github.com/hassancs91/claude-faceless-shorts-creator
- https://github.com/artemnovitckii/claude-editing-skills
- https://github.com/ericosiu/ai-marketing-skills (`trial-reel-distribution/SKILL.md`)
- https://github.com/heygen-com/hyperframes
- https://www.remotion.dev/docs/captions/create-tiktok-style-captions
- https://github.com/gyoridavid/short-video-maker
- https://github.com/harry0703/MoneyPrinterTurbo
- https://github.com/mutonby/openshorts
- https://github.com/instaloader/instaloader
- https://apify.com/apify/instagram-reel-scraper
- https://apify.com/nerolabs/viral-outlier-finder ("Views divided by the creator's median views (the video itself left out)")
