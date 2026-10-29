# Changelog

All notable changes to the `liquid-dawn` skill. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

- Phone specimen: clear and smoked liquid-metal glass sign-in surfaces.
- Orb studies: clear dew, deforming liquid metal and circulating ASCII tide, with bounded live optical controls.
- Research: first-party glass implementation notes and explicit limits on unverified reference internals.
- Paper specimen: refractive daylight agent core, four glass/metal surfaces, and three video-to-type treatments.
- Film controls support manual dissolve, glass windows and a type bridge; playback pauses offscreen and uses posters under reduced motion.
- The cinema study bundles the generated toile/sky clips and compressed posters under `assets/media/cinema/`, with source provenance and hashes.

## [0.1.0] - 2026-10-28

### Added
- DESIGN.md contract for Liquid Dawn, the calm daylight sibling of Liquid Midnight (BRO-3570).
- Tokens (`tokens.json` → generated `tokens.css`): Dawn and Dusk modes (followOS() follows the OS), nature palette, pearl metal.
- `materials.css`: dew glass, pearl rim, capsule and chips, refractive lens (+ SVG lens), ring button, wash, grid,
  clearing, composer, type, and reduced-transparency / more-contrast / reduced-motion fallbacks.
- Render kit: pure nature fields (tide, breeze, cloud, ripple, clearing, refract), ASCII field with lenses and
  fringes, glyph-tile shoals and islands, pretext pages (pebble and well lenses, flow-around), the render loop.
- Vendored `@chenglou/pretext` 1.0.0 (MIT) and Manrope, Inter, JetBrains Mono (OFL).
- Specimen page, `serve.mjs`, `render.mjs`, `build_tokens.mjs`, and tests.
- Hero recipes (`kit/heroes.js`: dawn, caustic, currents, lagoon, horizon, tide) and the recipe gallery.
- Cinema (`kit/cinema.js`): the ASCII shader on a scroll-scrubbed film, dissolving to type at page breaks.
- Type themes (`data-ld-type`: manrope, inter-tight, geist, instrument) with vendored OFL faces and a type gallery.
- Paper direction (`specimen/paper.html`): glyph mosaics from pictures (`mosaic.js`), a WebGL liquid lens with
  dispersion (`lens.js`), the spark orb for agents (`spark.js`), engraving and dither print (`engrave.js`).
