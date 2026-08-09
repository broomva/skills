# Platform adaptation

The Broomva contract is semantic. CSS and React are one concrete adapter, not the design system itself. Use `tokens.json` as the machine-readable canonical role map, then translate those roles into the target platform's conventions while preserving the identity and accessibility baseline.

## Invariants on every platform

- Blue-axis light and dark foundations remain recognizably coupled.
- Resonant AI Blue remains the scarce interaction and information accent.
- System UI typography is the default; Cal Sans is an opt-in display accent.
- Spacing follows the 4px ladder and geometry stays restrained.
- Working surfaces are matte; glass requires real elevation.
- Functional color never carries meaning alone.
- Focus, selection, error, disabled, loading, and reduced-motion behavior remain perceptible.
- The blackhole mark keeps its aspect ratio, clear space, and intended contrast.

## Responsive web

- Use semantic CSS tokens and the public component entry point.
- Treat `375px`, `768px`, and `1440px` as baseline inspection widths, then add product-specific breakpoints from content pressure rather than device names.
- Preserve DOM order when recomposing layouts so keyboard and screen-reader order remain coherent.
- Use `prefers-color-scheme` only as an initial preference; allow an explicit theme choice when the product supports themes.
- Use `prefers-reduced-motion` and avoid `transition: all`.

## Native mobile

- Map semantic colors into the platform theme system, including high-contrast and dark appearances.
- Prefer native navigation, sheets, menus, text fields, switches, and accessibility semantics unless a custom control is necessary to express the brand.
- Use the platform's minimum hit target and dynamic type behavior even when it exceeds the web adapter's nominal dimensions.
- Respect safe areas, software keyboards, text scaling, right-to-left layout, and reduced-motion settings.
- Translate frost through native material APIs where available; otherwise use an opaque elevated surface rather than imitating blur poorly.

## Desktop and Tauri-style applications

- Preserve desktop expectations for resizable windows, keyboard shortcuts, menus, dense data, hover, focus, and multi-pane navigation.
- Let the sidebar and header respond to window width; do not assume the archived `200px` and `52px` shell dimensions fit every desktop product.
- Use platform-native window chrome or a fully accessible custom title bar. Never mix the two ambiguously.
- Ensure operations remain discoverable without touch-first layouts or hidden hover-only controls.

## Embedded and constrained surfaces

For email, widgets, wearables, TV, kiosks, or low-capability webviews:

- Preserve color roles, typography hierarchy, spacing rhythm, and copy voice before attempting effects.
- Replace unsupported OKLCH values with tested platform equivalents at the adapter boundary; keep the canonical OKLCH source documented.
- Replace glass with opaque elevation and replace motion with static structural cues when capabilities or performance are limited.
- Reduce the component set to the user job. Do not ship an application shell into a constrained surface.

## Adapter checklist

Document these decisions in the target project:

1. Semantic color mapping and theme behavior.
2. Typography mapping and text-scaling behavior.
3. Spacing, radii, and elevation mapping.
4. Navigation and overlay conventions.
5. Input methods, focus, and accessibility semantics.
6. Motion and reduced-motion behavior.
7. Unsupported effects and their intentional fallbacks.

An adapter is conformant when the product remains recognizably Broomva and behaves correctly for its platform. Pixel identity with the web CSS is neither required nor sufficient.
