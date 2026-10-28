// Liquid Midnight render kit · WebGL glass plasma orb + 2D fallback.
// Extracted from broomva/agent-workspaces deck/index.html @187972f, lines 1447-1546 (Apache-2.0).
// Orbs are batched: between ORB.begin(ctx) and ORB.end(), orb() queues one quad per orb and end() draws them all in one
// WebGL pass on a layer canvas stacked directly above the 2D canvas (and below its glass panels): one GPU sync per frame.
// Off-batch orbs (a brand pill, a button) render as sprites through a shared 256² canvas. Output is a pure function of the
// attributes, so captures stay deterministic. On WebGL failure or context loss everything falls back to orb2d().
import { al, C, clamp, ctx, glow, lerp, TAU } from "./core.js";
import { FS, VS } from "./orb-shaders.js";

/** 2D fallback orb: dark sphere, swirling filaments, fresnel rim, specular, orbit arcs (r ≥ 14). */
export function orb2d(x, y, r, c, t, a = 1) {
  const g0 = ctx.globalAlpha;
  const R = Math.max(5, r * 0.58);
  ctx.globalAlpha = g0 * a;
  glow(x, y, R * 2.7, c, 0.3);
  const b = ctx.createRadialGradient(x - R * 0.2, y - R * 0.25, R * 0.05, x, y, R);
  b.addColorStop(0, al(c, 0.5));
  b.addColorStop(0.55, al(C.deep, 0.9));
  b.addColorStop(0.86, al(c, 0.3));
  b.addColorStop(1, al(c, 0.92));
  ctx.fillStyle = b;
  ctx.beginPath();
  ctx.arc(x, y, R, 0, TAU);
  ctx.fill();
  if (R >= 9) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, R * 0.97, 0, TAU);
    ctx.clip();
    const op = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = "lighter";
    for (let k = 0; k < 4; k++) {
      const a0 = t * (0.55 + 0.21 * k) + k * 1.71;
      const ex = x + Math.cos(a0) * R * 0.95;
      const ey = y + Math.sin(a0) * R * 0.95;
      const b1 = a0 + 1.3 + Math.sin(t * 0.8 + k) * 0.6;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.bezierCurveTo(x + Math.cos(b1) * R * 0.5, y + Math.sin(b1) * R * 0.5, ex + Math.cos(a0 - 1) * R * 0.3, ey + Math.sin(a0 - 1) * R * 0.3, ex, ey);
      ctx.strokeStyle = al(c, 0.5);
      ctx.lineWidth = Math.max(1, R * 0.075);
      ctx.stroke();
      ctx.strokeStyle = "oklch(0.97 0.03 240 / .4)";
      ctx.lineWidth = Math.max(0.6, R * 0.024);
      ctx.stroke();
    }
    for (let k = 0; k < 2; k++) glow(x + Math.cos(t * 0.7 + k * 3) * R * 0.38, y + Math.sin(t * 0.9 + k * 3) * R * 0.38, R * 0.55, c, 0.32);
    glow(x, y, R * 0.32, "oklch(0.98 0.03 240)", 0.55);
    ctx.globalCompositeOperation = op;
    ctx.restore();
  }
  const rim = ctx.createLinearGradient(x - R, y - R, x + R, y + R);
  rim.addColorStop(0, "oklch(0.98 0.02 240 / .85)");
  rim.addColorStop(0.5, al(c, 0.15));
  rim.addColorStop(1, al(c, 0.75));
  ctx.strokeStyle = rim;
  ctx.lineWidth = Math.max(1, R * 0.06);
  ctx.beginPath();
  ctx.arc(x, y, R, 0, TAU);
  ctx.stroke();
  const sx = x - R * 0.36;
  const sy = y - R * 0.42;
  const sp = ctx.createRadialGradient(sx, sy, 0, sx, sy, R * 0.3);
  sp.addColorStop(0, "oklch(1 0 0 / .8)");
  sp.addColorStop(1, "oklch(1 0 0 / 0)");
  ctx.fillStyle = sp;
  ctx.beginPath();
  ctx.ellipse(sx, sy, R * 0.3, R * 0.17, -0.6, 0, TAU);
  ctx.fill();
  if (r >= 14) {
    ctx.strokeStyle = c;
    ctx.lineWidth = 1;
    ctx.globalAlpha = g0 * a * 0.45;
    ctx.beginPath();
    ctx.arc(x, y, R * 1.45, t * 0.6, t * 0.6 + 1.5);
    ctx.stroke();
    ctx.globalAlpha = g0 * a * 0.18;
    ctx.beginPath();
    ctx.arc(x, y, R * 1.45, t * 0.6 + 2, t * 0.6 + 3.6);
    ctx.stroke();
  }
  ctx.globalAlpha = g0;
}

/** onLost/onRestored: called when the GPU context drops or returns, so the host can repaint. */
export const ORB = (() => {
  const F = 14;
  const RGB = new Map();
  let onChange = () => {};
  function rgb(c) {
    if (RGB.has(c)) return RGB.get(c);
    const x = document.createElement("canvas").getContext("2d");
    x.fillStyle = c;
    x.fillRect(0, 0, 1, 1);
    const d = x.getImageData(0, 0, 1, 1).data;
    const v = [d[0] / 255, d[1] / 255, d[2] / 255];
    RGB.set(c, v);
    return v;
  }
  /* one renderer per canvas: compiles the program once, rebuilds after a context restore */
  function renderer(cv) {
    const R = { cv, gl: null, ok: null, buf: null };
    R.init = () => {
      R.ok = false;
      try {
        const gl = (R.gl = cv.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: false, preserveDrawingBuffer: true }));
        if (!gl) return;
        if (!cv._wired) {
          cv._wired = 1;
          cv.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            R.ok = false;
            onChange();
          });
          cv.addEventListener("webglcontextrestored", () => {
            R.ok = null;
            onChange();
          });
        }
        const sh = (ty, src) => {
          const s = gl.createShader(ty);
          gl.shaderSource(s, src);
          gl.compileShader(s);
          if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
          return s;
        };
        const pr = gl.createProgram();
        gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS));
        gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS));
        gl.linkProgram(pr);
        if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
        gl.useProgram(pr);
        R.buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, R.buf);
        let off = 0;
        for (const [n, k] of [
          ["aPos", 2],
          ["aLoc", 2],
          ["aT", 1],
          ["aSeed", 1],
          ["aA", 3],
          ["aB", 3],
          ["aV", 1],
          ["aAl", 1],
        ]) {
          const l = gl.getAttribLocation(pr, n);
          gl.enableVertexAttribArray(l);
          gl.vertexAttribPointer(l, k, gl.FLOAT, false, F * 4, off * 4);
          off += k;
        }
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        R.ok = true;
      } catch (e) {
        console.warn("orb: WebGL unavailable, using the 2D fallback", e);
        R.ok = false;
      }
    };
    R.ready = () => {
      if (R.ok === null) R.init();
      return R.ok && !R.gl.isContextLost();
    };
    R.draw = (data, n, w, h) => {
      const gl = R.gl;
      gl.viewport(0, 0, w, h);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (!n) return;
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.TRIANGLES, 0, n * 6);
    };
    return R;
  }
  /* one quad = 6 vertices × F floats; corners in clip space, local coords span the sprite (±1.7 sphere radii) */
  function quad(out, o, x0, y0, x1, y1, t, seed, A, B, v, a) {
    const C4 = [
      [x0, y0, -1.7, 1.7],
      [x1, y0, 1.7, 1.7],
      [x0, y1, -1.7, -1.7],
      [x1, y0, 1.7, 1.7],
      [x1, y1, 1.7, -1.7],
      [x0, y1, -1.7, -1.7],
    ];
    for (const [px, py, lx, ly] of C4) {
      out.set([px, py, lx, ly, t, seed, A[0], A[1], A[2], B[0], B[1], B[2], v, a], o);
      o += F;
    }
    return o;
  }
  /* A = colour lifted 40% toward cyan (filaments, caustics); B = colour at 80% (body); violet rim tint .45 on blue orbs */
  function colors(c) {
    const v = rgb(c);
    const blue = v[2] > v[0] * 1.6 && v[2] > v[1] * 1.05;
    return [[lerp(v[0], 0.42, 0.4), lerp(v[1], 0.86, 0.4), lerp(v[2], 1, 0.4)], [v[0] * 0.8, v[1] * 0.8, v[2] * 0.85], blue ? 0.45 : 0.08];
  }
  let SR = null;
  const spriteRenderer = () => {
    if (!SR) {
      const spriteCv = document.createElement("canvas");
      spriteCv.width = spriteCv.height = 256;
      SR = renderer(spriteCv);
    }
    return SR;
  };
  /* one batch layer + renderer per source canvas, so several canvases can batch in the same frame */
  const layers = new Map();
  let target = null;
  /* release a layer as soon as its canvas leaves the DOM (SPA unmounts), not only on the next attach() */
  let watcher = null;
  const watch = (orb) => {
    if (watcher || typeof MutationObserver === "undefined") return;
    watcher = new MutationObserver(() => {
      for (const [k] of layers) if (!k.isConnected) orb.detach(k);
      if (!layers.size) {
        watcher.disconnect();
        watcher = null;
      }
    });
    watcher.observe(document.documentElement, { childList: true, subtree: true });
  };
  const queue = [];
  return {
    rgb,
    colors,
    onChange(fn) {
      onChange = fn;
    },
    get ok() {
      return spriteRenderer().ready();
    },
    /** Overlay a WebGL layer on canvas `cv`'s drawing area (inside its border and padding), absolutely positioned and
     *  inserted right after it. Stacking: the orbs paint above everything drawn on that canvas, and below later
     *  POSITIONED siblings (e.g. `.lm-glass` cards). Non-positioned later siblings paint below the layer.
     *  The layer mirrors the canvas's opacity, visibility and z-index, so fading the canvas fades its orbs.
     *  Call once per frame before begin(). Layers of canvases that left the DOM are released automatically;
     *  call detach(cv) to release one explicitly (browsers cap live WebGL contexts at about 16). */
    attach(cv) {
      for (const [k] of layers) if (k !== cv && !k.isConnected) this.detach(k);
      let e = layers.get(cv);
      if (!e) {
        const layer = document.createElement("canvas");
        layer.className = "lm-orb-layer";
        layer.setAttribute("aria-hidden", "true");
        e = { layer, LR: renderer(layer) };
        layers.set(cv, e);
        watch(this);
      }
      const { layer } = e;
      if (layer.previousElementSibling !== cv) cv.after(layer);
      const cs = getComputedStyle(cv);
      const px = (k) => Number.parseFloat(cs[k]) || 0;
      const st = layer.style;
      // a fixed canvas gets a fixed layer at its viewport box; everything else rides the canvas's offset box.
      // Not supported: CSS transforms on the canvas or its ancestors between it and the offset parent (the layer
      // would not follow them). Put transforms on a wrapper that contains both, or use the sprite path (no attach).
      const fixed = cs.position === "fixed";
      st.position = fixed ? "fixed" : "absolute";
      st.pointerEvents = "none";
      st.margin = "0";
      const box = fixed ? cv.getBoundingClientRect() : { left: cv.offsetLeft, top: cv.offsetTop };
      st.left = `${box.left + cv.clientLeft + px("paddingLeft")}px`;
      st.top = `${box.top + cv.clientTop + px("paddingTop")}px`;
      st.width = `${cv.clientWidth - px("paddingLeft") - px("paddingRight")}px`;
      st.height = `${cv.clientHeight - px("paddingTop") - px("paddingBottom")}px`;
      st.opacity = cs.opacity;
      st.visibility = cs.visibility;
      st.zIndex = cs.zIndex;
      if (layer.width !== cv.width || layer.height !== cv.height) {
        layer.width = cv.width;
        layer.height = cv.height;
      }
      return layer;
    },
    /** Release canvas `cv`'s layer: lose its WebGL context and remove it from the DOM. */
    detach(cv) {
      const e = layers.get(cv);
      if (!e) return;
      e.LR.gl?.getExtension("WEBGL_lose_context")?.loseContext();
      e.layer.remove();
      layers.delete(cv);
      if (target?.e === e) target = null;
    },
    /** number of live batch layers (diagnostics, tests) */
    get layers() {
      return layers.size;
    },
    begin(c2d) {
      const e = layers.get(c2d.canvas);
      target = e?.LR.ready() ? { c2d, e } : null;
      queue.length = 0;
    },
    batching(c2d) {
      return target !== null && c2d === target.c2d;
    },
    push(o) {
      queue.push(o);
    },
    end() {
      if (!target) return;
      const { layer, LR } = target.e;
      const n = queue.length;
      const data = new Float32Array(n * 6 * F);
      const W = layer.width;
      const H = layer.height;
      let off = 0;
      for (const q of queue) {
        const x0 = (q.x / W) * 2 - 1;
        const x1 = ((q.x + q.w) / W) * 2 - 1;
        const y0 = 1 - (q.y / H) * 2;
        const y1 = 1 - ((q.y + q.w) / H) * 2;
        off = quad(data, off, x0, y0, x1, y1, q.t, q.seed, q.A, q.B, q.v, q.a);
      }
      LR.draw(data, n, W, H);
      target = null;
    },
    /** single orb as a sprite (for canvases outside the batch); returns {cv, s} or null */
    sprite(px, t, seed, c) {
      const sr = spriteRenderer();
      if (!sr.ready()) return null;
      const s = Math.min(256, Math.max(8, Math.ceil(px)));
      const [A, B, v] = colors(c);
      const data = new Float32Array(6 * F);
      quad(data, 0, -1, 1, -1 + (2 * s) / 256, 1 - (2 * s) / 256, t, seed, A, B, v, 1);
      sr.draw(data, 1, 256, 256);
      return { cv: sr.cv, s };
    },
  };
})();

/** Draw an orb of nominal radius r (the sphere is .62 r; the bloom reaches 1.7× that) in colour c at time t. */
export function orb(x, y, r, c, t, a = 1) {
  const R = Math.max(5, r * 0.62);
  const E = R * 1.7;
  if (ORB.batching(ctx)) {
    const m = ctx.getTransform();
    const [A, B, v] = ORB.colors(c);
    ORB.push({
      x: m.a * (x - E) + m.c * (y - E) + m.e,
      y: m.b * (x - E) + m.d * (y - E) + m.f,
      w: 2 * E * m.a,
      t: t * 0.6,
      seed: (r * 0.731) % 1,
      A,
      B,
      v,
      a: clamp(ctx.globalAlpha * a, 0, 1),
    });
    return;
  }
  const k = ctx.getTransform().a || 1;
  const sp = ORB.sprite(2 * E * k, t * 0.6, (r * 0.731) % 1, c);
  if (!sp) return orb2d(x, y, r, c, t, a);
  const g = ctx.globalAlpha;
  ctx.globalAlpha = g * a;
  ctx.drawImage(sp.cv, 0, 0, sp.s, sp.s, x - E, y - E, 2 * E, 2 * E);
  ctx.globalAlpha = g;
}
