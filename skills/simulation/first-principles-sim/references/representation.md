# Choosing the representation and the renderer

The skill's rule for display is short: the renderer or the audio output reads simulated state
and nothing else. This file is about the choices that rule leaves open: how to hold the state,
what to draw it with, and whether the graphics processor should also compute it.

The two worked examples both used WebGL2, and that is a coincidence of their state, not a
default. The cloud chamber's state is a large array of droplets, and points are the cheapest
honest picture of particles. vinyl draws a disc. A plucked string needs no picture at all.

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

Mind the precision of the array, not only of the language. A JavaScript number is 64-bit, but
state stored in a `Float32Array` is 32-bit. The cloud chamber keeps droplet positions and radii
that way, which is fine for drawing and would not be for a long integration.

## Two jobs: drawing and computing

Keep these apart when you decide.

- **Drawing.** The simulation runs on the processor, and the graphics processor only draws the
  result. This is what the cloud chamber does: transport, nucleation and droplet growth are
  TypeScript, and WebGL2 draws one point per array entry. An entry can stand for several real
  droplets (about 15 on an alpha track), and that is recorded as a convention.
- **Computing.** The simulation itself runs on the graphics processor. This is faster for the
  right problems and harder to verify for all of them.

Default to drawing only. Move a stage to the graphics processor when the processor is measurably
too slow for it, and not before.

## What each choice does to verification

This is the reason the choice belongs in this skill.

- **A stage on the processor is an ordinary unit test.** You call the function and compare its
  numbers with the reference table.
- **A stage on the graphics processor has to be read back.** A field is rendered into a
  floating-point texture and its pixels read; particles advanced by transform feedback are read
  from their buffer. Reading a float texture needs the same extension as writing one (below).
  An ordinary 8-bit canvas keeps 8 bits per channel, which is enough to measure where a track
  is and not enough to check a number.
- **Shader arithmetic is at most 32-bit, and often less exact than that.** Medium precision can
  be 16-bit on phones, and built-in functions are not required to round correctly. Results
  differ slightly between graphics drivers, so a tolerance that passes on one machine may fail
  on another.
- **A headless browser usually renders in software.** Headless Chromium falls back to a software
  rasteriser unless told otherwise, and the cloud chamber's render gate runs that way by
  default. A green headless gate shows the shader is right. It says nothing about real drivers.

So: keep every stage you check against a `reference` or an `independent` claim on the
processor. Use the graphics processor for display, and for stages checked only by
`conservation` or `control` claims, with tolerances set from more than one real machine.

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
- **Modest numbers of interacting particles.** All-pairs gravity and simple position-based
  fluids work with state held in float textures, each particle reading all the others. This
  stops scaling once you need neighbour lists or sorting.
- **Path tracing of moderate scenes.** A fragment shader can trace paths with the scene's
  acceleration structure stored in textures. Several published WebGL2 path tracers do this.

Check three extensions before stepping a field in WebGL2, and fall back to the processor if one
is missing:

- `EXT_color_buffer_float`: rendering into a floating-point texture is not part of core WebGL2.
- `EXT_float_blend`: blending into a 32-bit float texture. 16-bit float targets blend without
  it.
- `OES_texture_float_linear`: linear filtering of 32-bit float textures. Smoke and fluid
  solvers that sample between cells need it.

## Where it does not, why, and what to use

| Problem | Why WebGL2 is a poor fit | Use |
|---|---|---|
| Many interacting particles needing neighbour search: smoothed-particle fluids at scale, grains in contact, molecular dynamics | WebGL2 has no compute shaders and no buffers a shader can both read and write, so building and sorting neighbour lists has to be faked through textures | WebGPU compute shaders; or the processor, with WebAssembly and web workers |
| Irregular meshes: finite elements, adaptive grids, sparse linear solves | A fragment shader can read from anywhere but writes only to its own pixel. Assembly and sparse updates need scattered writes | A solver on the processor (JavaScript or WebAssembly); draw the result with WebGL2 |
| Work that needs high precision: long orbital integrations, stiff chemistry, ill-conditioned solves | The shading language has no 64-bit floating point | The processor, with 64-bit numbers held in `Float64Array` or WebAssembly `f64` |
| Event-by-event Monte Carlo with branching: particle transport, showers | Every history takes a different path and a different number of steps, which fits a fixed fragment pipeline badly. Dedicated GPU transport codes exist, but they are built on compute, not on drawing | The processor, as the cloud chamber does; WebGPU compute if it must be faster |
| Sound | Audio runs on its own thread with sample-accurate timing, which a drawing pipeline cannot give | Web Audio with an AudioWorklet, as vinyl does |
| Path tracing of large or complex scenes | Neither WebGL2 nor WebGPU has hardware ray tracing. WebGPU's compute shaders and storage buffers make the acceleration structure and the scheduling of rays far easier to build | A compute-shader path tracer on WebGPU, or render offline |
| Plain plots | More machinery than the picture needs, and harder to test | A 2D canvas or SVG |
| Runs too large for a browser tab | Memory and time limits | Compute offline or on a server, store the result, and display the stored result |

Path tracing is an unbiased estimate that converges with more samples. It is not exact, and
the number of samples per pixel belongs in the ledger as a convention.

When the result is computed elsewhere and only displayed, the stored result is a file the
package ships. Say in the README that the page replays it, and keep the code that produced it
in the package so the report command can regenerate the numbers.

## WebGPU

WebGPU adds compute shaders and buffers that a shader can read and write, which is what
neighbour search and irregular data need. Its shading language has no 64-bit floating point
either, and its results still have to be read back to be checked.

Browser support was uneven when this was written (2026-11-14), and it depends on the operating
system as well as the browser version:

- **Chrome and Edge:** on by default from version 113 on Windows, macOS and ChromeOS; from 121
  on Android 12 and later with certain graphics chips; on Linux from 144 for some hardware, with
  the rest behind a flag.
- **Firefox:** from 141 on Windows; on macOS from 145 for Apple-silicon machines on macOS 26,
  widening in 147; Linux and Android not yet on by default.
- **Safari:** from Safari 26 on macOS 26, iOS 26, iPadOS 26 and visionOS 26.

Check the current state before depending on it, and keep a WebGL2 or processor path for
browsers without it.

Sources, read 2026-11-14:

- WebGPU support: <https://web.dev/blog/webgpu-supported-major-browsers> and
  <https://github.com/gpuweb/gpuweb/wiki/Implementation-Status>
- Float render targets: <https://developer.mozilla.org/en-US/docs/Web/API/EXT_color_buffer_float>
- Float blending: <https://developer.mozilla.org/en-US/docs/Web/API/EXT_float_blend>

## The order to decide in

1. What state does the physics produce? Pick its representation from the first table.
2. Can the processor compute it fast enough? If so, compute there and only draw.
3. Does the picture need 3D or more than a few thousand marks? If not, use a 2D canvas or SVG.
4. If it does, draw with WebGL2.
5. If the processor is too slow: a regular grid, non-interacting particles or a modest number
   of interacting ones can move to WebGL2; neighbour search, sorting or irregular data need
   WebGPU.
6. For each stage that moved, check that its claim kind still allows it (see verification
   above), and record the display's own limits as `convention` claims: the sprite size, the
   phase function, the colour map, the samples per pixel.
