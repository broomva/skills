# Hydra-synth cheatsheet

Quick reference for `hydra-synth`'s most-used functions. Full API at
<https://hydra.ojack.xyz/api/>.

## Sources (start of a chain)

```javascript
osc(freq, sync, offset)            // sine-wave grid; freq=density, sync=scroll speed
shape(sides, radius, smooth)       // polygon
gradient(speed)                    // color gradient
voronoi(scale, speed, blending)    // voronoi cells
noise(scale, offset)               // perlin-ish
src(o0)                            // feedback from previous frame (o0..o3)
solid(r, g, b)                     // solid color
```

## Geometry transforms

```javascript
.rotate(angle, speed)
.scale(amount, xMult, yMult)
.kaleid(nSides)
.scroll(x, y, speedX, speedY)
.scrollX(x, speed)
.scrollY(y, speed)
.repeat(repeatX, repeatY, offsetX, offsetY)
.repeatX(reps, offset)
.repeatY(reps, offset)
.pixelate(pixelX, pixelY)
```

## Color transforms

```javascript
.invert(amount)
.contrast(amount)
.brightness(amount)
.luma(threshold, tolerance)
.posterize(bins, gamma)
.shift(r, g, b, a)
.color(r, g, b, a)
.colorama(amount)
.thresh(threshold, tolerance)
.saturate(amount)
.hue(amount)
.r() .g() .b() .a()           // extract single channel
```

## Modulation (warp by another signal)

```javascript
.modulate(src, amount)             // most general
.modulateRotate(src, mult, offset)
.modulateScale(src, mult, offset)
.modulateScrollX(src, amount, speed)
.modulateScrollY(src, amount, speed)
.modulateKaleid(src, nSides)
.modulateRepeat(src, repeatX, repeatY, offsetX, offsetY)
.modulatePixelate(src, mult, offset)
.modulateHue(src, amount)
```

## Blend / composition

```javascript
.blend(src, amount)                 // mix two sources
.add(src, amount)
.mult(src, amount)
.sub(src, amount)
.diff(src)
.mask(src, reps, offset)
.layer(src)                         // stack on top respecting alpha
```

## Outputs

```javascript
.out()                              // → output 0 (main display)
.out(o0)                            // explicit output 0
.out(o1)                            // → output 1 (read back via src(o1))
render(o1)                          // switch displayed output
render()                            // show all 4 in a grid
```

## Time + audio-reactivity + mouse

```javascript
() => time * 0.1                    // `time` is a global, ticks each frame
() => Math.sin(time)                // any JS expression as parameter

// FFT (mic / system audio)
a.setBins(4)                        // create 4 frequency bins
a.show()                            // visualize bins in corner of canvas
a.fft[0]                            // first band's energy (bass)
a.fft[3]                            // last band's energy (treble)
() => a.fft[0] * 8 + 4              // drive a parameter from bass

// Audio detection settings (rarely needed)
a.setSmooth(0.4)                    // smoothing factor
a.setCutoff(2)                      // ignore values below this

// Mouse
mouse.x                             // normalized 0..width
mouse.y                             // normalized 0..height
```

## External sources

```javascript
s0.initCam()                        // webcam
s0.initVideo("https://...")         // video URL (must support CORS)
s0.initImage("https://...")         // image URL
s0.initScreen()                     // browser-permission screen capture
src(s0).out()                       // route the source
```

## Useful patterns

```javascript
// Tunnel (industrial)
osc(60, 0.1, 1.5)
  .kaleid(8)
  .repeat(2, 2)
  .scrollY(0, () => -time * 0.1)
  .scale(0.5).colorama(0.1).contrast(1.5).out()

// Aggressive vortex
shape(4, 0.5, 0.001)
  .repeat(20, 10)
  .scrollY(0, () => -time * 0.15)
  .modulate(noise(3, 0.5))
  .scale(2).colorama(0.5).out()

// Wireframe lattice
osc(20, 0.05, 0.5)
  .kaleid(() => 4 + Math.sin(time*0.3)*3)
  .modulate(o0, 0.1)
  .luma(0.3).invert().out()

// Audio-reactive — bass drives kaleid segments
a.setBins(4)
osc(10, 0.1, 1)
  .kaleid(() => a.fft[0]*8 + 4)
  .modulate(noise(3)).out()

// Slow voronoi for ambient
voronoi(5, 0.1, 0.3)
  .colorama(0.05)
  .scale(2)
  .modulate(noise(2, 0.1), 0.05)
  .out()

// Glitchy pixel posterize
osc(40, 0.05, 0.5)
  .modulate(noise(5))
  .pixelate(20, 20)
  .posterize(4)
  .invert().out()
```

## Order matters

- `.scrollY` BEFORE `.kaleid` → warps a moving source through a kaleidoscope
- `.scrollY` AFTER `.kaleid` → scrolls the whole kaleidoscope output
- `.modulate` AFTER `.kaleid` → modulates the already-symmetric image
- `.modulate` BEFORE `.kaleid` → kaleidoscope a modulated source
