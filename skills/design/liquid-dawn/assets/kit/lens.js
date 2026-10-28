// Liquid Dawn kit · liquid lens: a drop of clear glass that refracts what is under it (the 1-12 reference). A WebGL
// overlay samples a SOURCE canvas (the content to bend: paper, type, fields) through a dome: the centre magnifies, the
// rim bends the content round the edge, and the three colour channels refract by slightly different amounts, so the
// rim breaks into a rainbow fringe. A rim highlight, an inner shadow and a soft drop shadow make it read as a solid
// drop. Drag it with a spring; a press squashes it. lensRefract() is the same maths in JS, for tests and fallbacks.
import { Sp } from "./core.js";

/** Where a point at normalised radius d (0 centre .. 1 rim) samples from, as a fraction of the lens radius, for one
 *  colour channel. mag < 1 magnifies the centre; bend pushes the rim outward; disp separates the channels. Pure. */
export function lensRefract(d, { mag = 0.72, bend = 0.55, disp = 0.06, channel = 0 } = {}) {
  const k = bend * (1 + disp * channel);
  return d * mag + d ** 4 * k;
}

const VS = `attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }`;
const FS = `precision highp float;
uniform sampler2D src; uniform vec2 res; uniform vec2 c; uniform vec2 rad; uniform float mag, bend, disp, frost; uniform vec3 ground;
vec4 sampleRefract(vec2 q, float d, float ch){
  float s = d * mag + pow(d, 4.) * bend * (1. + disp * ch);   // = lensRefract() in JS; keep the two in step
  vec2 dir = d > 1e-4 ? q / d : vec2(0.);
  return texture2D(src, (c + dir * s * rad) / res);
}
// premultiplied "over": a layer of colour l (premultiplied) and alpha la, over (c, a)
void over(inout vec3 col, inout float a, vec3 l, float la){ col = l + col * (1. - la); a = la + a * (1. - la); }
void main(){
  vec2 q = (gl_FragCoord.xy - c) / rad; float d = length(q);
  if (d > 1.18) discard;
  if (d > 1.) {               // soft drop shadow, offset down
    vec2 qs = (gl_FragCoord.xy - c - vec2(0., -rad.y * .07)) / rad; float ds = length(qs);
    float a = (1. - smoothstep(.98, 1.16, ds)) * .16; gl_FragColor = vec4(vec3(.18, .2, .24) * a, a); return;
  }
  // the glass covers what it bends: start from the page ground (opaque), then lay the refracted source over it with
  // the source's own premultiplied alpha. A transparent source therefore shows the ground, bent content only, and
  // never the unbent source through the drop (no double image) and never a black disc.
  // Each channel refracts from its own position, so each is composited over the ground with ITS OWN coverage
  // (a single shared alpha would add ink onto ground where only one channel hits an edge: a halo).
  vec4 sr = sampleRefract(q, d, -1.);
  vec4 sg = sampleRefract(q, d, 0.);
  vec4 sb = sampleRefract(q, d, 1.);
  vec3 col = vec3(sr.r + ground.r * (1. - sr.a), sg.g + ground.g * (1. - sg.a), sb.b + ground.b * (1. - sb.a));
  float a = 1.;
  float z = sqrt(max(0., 1. - d * d));
  float milk = frost * (.25 + .35 * (1. - z));                              // a whisper of milk, thicker toward the rim
  over(col, a, vec3(milk), milk);
  float sh = .12 * smoothstep(.55, 1., d) * smoothstep(-.2, .9, -q.y);       // inner shadow along the lower rim
  over(col, a, vec3(0.), sh);
  float rim = smoothstep(.9, 1., d) * .55 * (.6 + .4 * q.y);                 // bright rim, brighter on top
  over(col, a, vec3(rim), rim);
  float spec = smoothstep(.42, .0, length(q - vec2(-.38, .46))) * .55;       // the top-left specular
  over(col, a, vec3(spec), spec);
  float aa = 1. - smoothstep(.985, 1., d);
  gl_FragColor = vec4(col * aa, a * aa);
}`;

/**
 * createLens(overlay, source, opts) → { paint(state), follow(x, y), press(on), step(dt), state, supported }
 *  overlay: a canvas over `source`, same CSS box (the lens draws here; the rest stays transparent). If the boxes
 *           differ, paint() draws nothing and sets lens.mismatch; a tainted source sets lens.tainted.
 *  Call step(dt) in the loop's step and paint() in its paint, after the source canvas is drawn. Place it with
 *  snap(x, y) or follow(x, y) (CSS px in the overlay); unplaced, it starts at the centre. The source may be
 *  transparent: under the drop the lens paints `ground` (an [r, g, b] 0..255; default: the first opaque background
 *  of the overlay's ancestors, in any colour syntax, re-read each paint so a mode switch follows) and lays the
 *  refracted source over it, so the glass covers what it bends. The ground is flat: if the page shows a wash or a
 *  grid behind a transparent source, draw them into the source so the drop bends them too.
 *  source:  the canvas whose pixels the lens bends (re-uploaded each paint).
 *  opts: { r, mag, bend, disp, frost } — r in CSS px.
 */
export function createLens(overlay, source, { r = 74, mag = 0.72, bend = 0.55, disp = 0.06, frost = 0.06, preserve = false, ground = null } = {}) {
  r = Math.max(1, r); // a zero radius would divide by zero in the shader
  const gl = overlay.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: true, preserveDrawingBuffer: preserve });
  const pos = { x: new Sp(0), y: new Sp(0), sx: new Sp(1), sy: new Sp(1) };
  const L = { supported: !!gl, tainted: false, mismatch: false, state: { x: 0, y: 0, r, squash: 0 } };
  if (!gl) {
    L.paint = () => {};
    L.step = () => {};
    L.follow = () => {};
    L.press = () => {};
    return L;
  }
  const sh = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const prog = gl.createProgram();
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS));
  gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog);
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]])
    gl.texParameteri(gl.TEXTURE_2D, k, v);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
  const U = Object.fromEntries(["src", "res", "c", "rad", "mag", "bend", "disp", "frost", "ground"].map((n) => [n, gl.getUniformLocation(prog, n)]));
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

  let placed = false;
  L.follow = (x, y) => {
    placed = true;
    pos.x.set(x);
    pos.y.set(y);
  };
  L.snap = (x, y) => {
    placed = true;
    pos.x.snap(x);
    pos.y.snap(y);
    Object.assign(L.state, { x, y });
  };
  L.press = (on) => {
    pos.sx.set(on ? 1.08 : 1);
    pos.sy.set(on ? 0.93 : 1);
  };
  L.step = (dt) => {
    pos.x.step(dt, 0.32, 0.86);
    pos.y.step(dt, 0.32, 0.86);
    pos.sx.step(dt, 0.28, 0.55);
    pos.sy.step(dt, 0.28, 0.55);
    Object.assign(L.state, { x: pos.x.v, y: pos.y.v });
  };
  L.paint = () => {
    const d = Math.min(2, globalThis.devicePixelRatio || 1);
    const w = overlay.clientWidth;
    const h = overlay.clientHeight;
    if (overlay.width !== Math.round(w * d) || overlay.height !== Math.round(h * d)) {
      overlay.width = Math.round(w * d);
      overlay.height = Math.round(h * d);
    }
    if (!placed) L.snap(w / 2, h / 2); // a lens nobody placed starts at the centre, not the corner
    gl.viewport(0, 0, overlay.width, overlay.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    // the texture is sampled in the overlay's coordinates, so the two must share a CSS box
    L.mismatch = Math.abs(source.clientWidth - w) > 0.5 || Math.abs(source.clientHeight - h) > 0.5;
    if (L.mismatch) return;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    try {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    } catch {
      L.tainted = true; // a source canvas tainted by cross-origin media cannot be uploaded: show no lens, keep running
      return;
    }
    L.tainted = false;
    // source and overlay share a CSS box; the texture spans the source's pixels, the overlay's own resolution maps 1:1
    gl.uniform1i(U.src, 0);
    gl.uniform2f(U.res, overlay.width, overlay.height);
    gl.uniform2f(U.c, pos.x.v * d, overlay.height - pos.y.v * d);
    gl.uniform2f(U.rad, r * d * pos.sx.v, r * d * pos.sy.v);
    gl.uniform1f(U.mag, mag);
    gl.uniform1f(U.bend, bend);
    gl.uniform1f(U.disp, disp);
    const g = ground ?? pageGround(overlay);
    gl.uniform3f(U.ground, g[0] / 255, g[1] / 255, g[2] / 255);
    gl.uniform1f(U.frost, frost);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };
  return L;
}

/** The colour the page shows behind `el`: its nearest ancestor with an opaque background (else white). Any CSS colour
 *  syntax works (oklch, color(), hex, named): the computed value is resolved by painting it into a 1 × 1 canvas. */
const groundCache = new Map();
export function cssColorToRGBA(css) {
  let v = groundCache.get(css);
  if (v) return v;
  const c = document.createElement("canvas");
  c.width = c.height = 1;
  const x = c.getContext("2d", { willReadFrequently: true });
  x.clearRect(0, 0, 1, 1);
  x.fillStyle = "#000";
  x.fillStyle = css; // an invalid colour leaves the previous fill
  x.fillRect(0, 0, 1, 1);
  const d = x.getImageData(0, 0, 1, 1).data;
  v = [d[0], d[1], d[2], d[3]];
  groundCache.set(css, v);
  return v;
}
export function pageGround(el) {
  for (let n = el?.parentElement; n; n = n.parentElement) {
    const bg = getComputedStyle(n).backgroundColor;
    if (!bg || bg === "transparent") continue;
    const [r, g, b, a] = cssColorToRGBA(bg);
    if (a >= 254) return [r, g, b];
  }
  return [255, 255, 255];
}

/** Wire pointer drag onto an element: the lens follows while held, and squashes on press. Live preview only. */
export function dragLens(el, lens, onMove = () => {}) {
  let held = false;
  const at = (e) => {
    const b = el.getBoundingClientRect();
    return [e.clientX - b.left, e.clientY - b.top];
  };
  el.addEventListener("pointerdown", (e) => {
    held = true;
    el.setPointerCapture?.(e.pointerId);
    lens.press(true);
    lens.follow(...at(e));
    onMove();
  });
  el.addEventListener("pointermove", (e) => {
    if (!held) return;
    lens.follow(...at(e));
    onMove();
  });
  const up = () => {
    held = false;
    lens.press(false);
    onMove();
  };
  el.addEventListener("pointerup", up);
  el.addEventListener("pointercancel", up);
  return () => held;
}
