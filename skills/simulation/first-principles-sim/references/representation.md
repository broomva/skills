# Choosing the representation and the renderer

The skill's rule for display is short: the renderer or the audio output reads simulated state
and nothing else. This file is about the choices that rule leaves open: how to hold the state,
what to draw it with, and whether the graphics processor should also compute it.

The two worked examples both used WebGL2, and that is a coincidence of their state, not a
default. The cloud chamber's state is hundreds of thousands of droplets, and points are the
cheapest honest picture of particles. vinyl draws a disc. A plucked string needs no picture at
all.

## Start from the state

The physics decides the state, and the state decides the representation. Choose the renderer
last.

| State the physics produces | Hold it as | Show it with |
|---|---|---|
| Particles: droplets, grains, bodies, molecules | Arrays of position, size, velocity | Points, or one small shape drawn many times (instancing) |
| A field on a regular grid: temperature, vapor, fluid velocity | A 2D or 3D array | A colour-mapped image; for 3D, a slice or a ray-marched volume |
| A surface: membrane, water surface, cut groove | A height field or a mesh | A lit mesh |
| Rays or a wave field: optics | Ray paths, or a complex amplitude on a grid | Lines, or intensity on a sensor plane |
| A trajectory or time series: orbits, circuits, a neuron's voltage | A list of samples | A 2D line plot |
| Sound | A stream of samples | Nothing. The audio is the observation; add a waveform or spectrum only if it helps |

Many simulations need no 3D and no graphics processor. An orbit, a circuit and a string are
honestly shown on a 2D canvas or as SVG, and those are easier to test.

## Two jobs: drawing and computing

Keep these apart when you decide.

- **Drawing.** The simulation runs on the processor, and the graphics processor only draws the
  result. This is what the cloud chamber does: transport, nucleation and droplet growth are
  TypeScript, and WebGL2 draws one point per droplet.
- **Computing.** The simulation itself runs on the graphics processor. This is faster for the
  right problems and harder to verify for all of them.

Default to drawing only. Move a stage to the graphics processor when the processor is measurably
too slow for it, and not before.

## What each choice does to verification

This is the reason the choice belongs in this skill.

- **A stage on the processor is an ordinary unit test.** You call the function and compare its
  numbers with the reference table.
- **A stage on the graphics processor has to be read back.** You render into a texture, read
  the pixels, and compare. Results can differ slightly between graphics drivers, so a tolerance
  that passes on one machine may fail on another.
- **Shaders compute in 32-bit floating point.** A stage whose check needs more precision than
  that cannot run there.

So: keep every stage you check against a `reference` or an `independent` claim on the
processor. Use the graphics processor for display, and for stages checked only by
`conservation` or `control` claims, with tolerances set from more than one machine.

Whatever draws the picture, the rendered output is still measured, headless, against the same
anchors (step 5 of the arc). List that check under `tests.gates` in the ledger.

## Where WebGL2 fits

- **Drawing many particles.** Points or instanced shapes, with brightness or size computed per
  particle from its state.
- **Showing a field.** A 2D array as a texture; a 3D array as a 3D texture that a fragment
  shader marches through.
- **Lit surfaces.** A height field or a mesh.
- **Per-pixel optics.** Marching rays through simple analytic shapes, thin-film colours,
  refraction in a sphere.
- **Stepping a field on a regular grid.** Heat diffusion, reaction-diffusion, shallow-water
  waves, 2D smoke, the wave equation on a membrane. Each cell reads its neighbours from one
  texture and writes its new value to another, and the two textures swap each step.
- **Advancing particles that do not interact.** Transform feedback writes each particle's new
  state from its old one.

Two things to check before stepping a field in WebGL2:

- Rendering into a floating-point texture is not part of core WebGL2. It needs the
  `EXT_color_buffer_float` extension. Test for it and fall back to the processor.
- Blending into a floating-point texture is a separate extension, `EXT_float_blend`.

## Where it does not, why, and what to use

| Problem | Why WebGL2 is the wrong tool | Use |
|---|---|---|
| Particles that interact: N-body gravity, smoothed-particle fluids, grains in contact, molecular dynamics | WebGL2 has no compute shaders and no general buffers a shader can both read and write, so neighbour search and sorting have to be faked through textures | WebGPU compute shaders; or the processor, with WebAssembly and web workers |
| Irregular meshes: finite elements, adaptive grids, sparse linear solves | Shaders are built for regular grids; indirect addressing through textures is slow and fragile | A solver on the processor (JavaScript or WebAssembly); draw the result with WebGL2 |
| Work that needs high precision: long orbital integrations, stiff chemistry, ill-conditioned solves | The shading language has no 64-bit floating point | The processor, where JavaScript numbers and WebAssembly `f64` are 64-bit |
| Event-by-event Monte Carlo with branching: particle transport, showers | Every history takes a different path and a different number of steps, which graphics processors handle badly | The processor. The cloud chamber's transport runs there for this reason |
| Sound | Audio needs sample-accurate timing on its own thread, which a drawing pipeline cannot give | Web Audio with an AudioWorklet, as vinyl does |
| Physically exact light: global illumination, caustics through complex geometry | No ray-tracing support, so the whole path tracer would live in one fragment shader | A path tracer on WebGPU, or render offline |
| Plain plots | More machinery than the picture needs, and harder to test | A 2D canvas or SVG |
| Runs too large for a browser tab | Memory and time limits | Compute offline or on a server, store the result, and display the stored result |

When the result is computed elsewhere and only displayed, the stored result is a file the
package ships. Say in the README that the page replays it, and keep the code that produced it
in the package so the report command can regenerate the numbers.

## WebGPU

WebGPU adds compute shaders and buffers that a shader can read and write, which is what
interacting particles and irregular data need. Its shading language has no 64-bit floating
point either, and its results still have to be read back to be checked.

Browser support was uneven when this was written (2026-11-14): on by default in Chrome and Edge
since version 113, in Firefox on Windows since version 141 with other platforms following, and
in Safari since version 26. Check the current state before depending on it, and keep a WebGL2 or
processor path for browsers without it.

- <https://web.dev/blog/webgpu-supported-major-browsers>
- <https://github.com/gpuweb/gpuweb/wiki/Implementation-Status>
- <https://developer.mozilla.org/en-US/docs/Web/API/EXT_color_buffer_float>

## The order to decide in

1. What state does the physics produce? Pick its representation from the first table.
2. Can the processor compute it fast enough? If so, compute there and only draw.
3. Does the picture need 3D or more than a few thousand marks? If not, use a 2D canvas or SVG.
4. If it does, draw with WebGL2.
5. If the processor is too slow: a regular grid or non-interacting particles can move to
   WebGL2; interacting particles or irregular data need WebGPU.
6. For each stage that moved, check that its claim kind still allows it (see verification
   above), and record the display's own limits as `convention` claims: the sprite size, the
   phase function, the colour map.
