# Glass and orb studies — 2026-10-28

## Published technique and its limits

[Jesse Vermeulen's Liquid Glass reference](https://www.inspora.design/posts/liquid-glass)
links to the creator behind [Outpace's implementation write-up](https://glass.outpacestudios.com/).
Outpace describes a convex squircle dome, Snell-law displacement concentrated at the rim,
and a filtered, counter-positioned copy of the backdrop. Their account credits
[Aave's architecture](https://aave.com/design/building-glass-for-the-web).
Aave also documents using WebGL when the source is a canvas or video. These are first-party
implementation descriptions, not a claim that every Inspora glass clip uses the same engine.

[Zsolt Kacso's recorder](https://experiments.thisiswhitespace.com/liquid-glass-recorder)
is described on the creator's index as cursor-bending glass with voice-reactive glow.
The demo page provides no readable implementation article. Its source product is paid;
we did not acquire or copy it. The exact recorder shader stack remains unverified.

The [ASCII black-hole reference](https://www.inspora.design/posts/black-hole-mp4)
describes a text-warp animation; the [shark reference](https://www.inspora.design/posts/shark-ascii-animation)
describes glyph sharks around a chat UI. Their listings do not establish the rendering engines.
Polar coordinate glyph flow is our implementation choice, not an attribution to either creator.

## Our adaptation

- Clear dew: live source-canvas refraction with a chromatic rim and spring displacement.
- Liquid metal: a bounded three-lobe dome deformation over an authored cream/steel/lagoon reflection environment.
  This is a stylized reflection study, not a physically traced HDR environment.
- ASCII tide: slowly circulating polar glyph rings, refracted through the same lens.
- Phone controls: clear and smoked CSS glass with travelling metallic bevels. They are material studies;
  their CSS backdrop blur does not claim the WebGL orb's optical accuracy.

All three orb variants share one source canvas and one WebGL context. Optical controls reject
non-finite values and excessive deformation. The existing spherical lens is unchanged at morph=0.
No microphone access is requested: this is an ambient/pointer study, not a voice recorder.

## Media and verification

`assets/media/cinema/provenance.json` records generated source identity and SHA-256 hashes for
both five-second clips and four compressed posters. These files are bundled, unlike the earlier
local-only explore directory. The toile and sky clips remain separate authored transitions;
the type handoff between their unrelated scenes is a visual study, not a verified continuous
scroll-cinema keyframe chain.

The paper E2E checks actual variant pixel changes, both decoded clips, the manual dissolve,
Dawn/Dusk, metallic button rims, accessible CTA contrast, reduced-motion posters, actual decoded seeks and mobile overflow. Performance probes require live sampling to stay bounded and offscreen orb/material paint calls to stop. Shared unit/render
tests continue to cover the existing lens and deterministic kit.
