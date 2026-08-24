/**
 * Scroll-driven video scrubber.
 *
 * Two decoders, bounded memory, frame-rate-independent easing. All playback
 * arithmetic is delegated to the pure functions in `map.ts`; this module owns
 * only DOM, network and lifecycle.
 *
 * Design notes and the measurements behind the defaults:
 * docs/specs/2026-08-17-scroll-cinema-playbook.html
 */

import {
  bindTargets,
  clamp01,
  easeToward,
  fadeAt,
  placement,
  residentSet,
  shouldReveal,
  shouldSeek,
  slotFor,
  timeFor,
  trackProgress,
} from "./map";

export interface ScrollCinemaOptions {
  /** Clip URLs, in narrative order. Assumed uniform fps/duration. */
  clips: string[];
  /** Scene stills. Must be `clips.length + 1` — one per clip boundary. */
  posters: string[];
  /** Container the video layers are appended to. Should be viewport-sized. */
  stage: HTMLElement;
  /** Element whose height defines the scroll range. Defaults to the document. */
  track?: HTMLElement;
  /** Inertia time constant, seconds. */
  tau?: number;
  /** Fraction of each clip spent crossfading into the next. */
  fade?: number;
  /**
   * Maximum clips retained in memory at once — completed plus in-flight.
   *
   * **Minimum 3; smaller values are raised with a console warning.** Two clips
   * are bound during a crossfade and a third may be downloading, so a smaller
   * budget cannot be honoured — silently accepting one would make this option a
   * lie rather than a limit.
   */
  maxResident?: number;
  /** Seek deadband, seconds. Defaults to half a frame at 24fps. */
  seekEpsilon?: number;
  /**
   * `blob` fully buffers each clip for instant seeking (needs the bytes first).
   * `stream` assigns the URL directly and relies on dense-GOP range requests.
   */
  strategy?: "blob" | "stream";
  /** Fired when the active scene changes. */
  onScene?: (scene: number) => void;
  /** Override motion preference. Omit to read `prefers-reduced-motion`. */
  reducedMotion?: boolean;
  /** Injectable for tests. */
  view?: Window;
  /**
   * How long to wait for a compositor-confirmed frame before revealing anyway.
   * Fail-open: a stale frame beats a page that never shows video.
   */
  revealTimeoutMs?: number;
}

export interface ScrollCinemaDebug {
  scene: number;
  segment: number;
  local: number;
  progress: number;
  /** Number of <video> elements the engine created. Must never exceed 2. */
  decoders: number;
  /** Which segment each slot currently holds. */
  held: (number | null)[];
  /** Whether each slot has presented a frame from its current source. */
  settled: boolean[];
  /**
   * Frames actually painted by the compositor for the current source, counted
   * via requestVideoFrameCallback. Independent of `settled` -- which is what
   * gates opacity, and therefore cannot be used to check opacity.
   */
  framesPresented: number[];
  /** mediaTime of the last compositor-painted frame per slot; NaN if none. */
  lastPaintedTime: number[];
  /** |painted - requested| when each bind generation first became visible. */
  revealLag: number[];
  /** Segments currently buffered. */
  resident: number[];
  /** Segments with a fetch in flight. */
  inFlight: number[];
  /** currentTime of each slot, for asserting that scrubbing actually moves. */
  times: number[];
  /** Rendered opacity per slot. A slot may only be visible once settled. */
  opacity: number[];
  /** Cumulative `src` assignments per slot. Thrash detector: should stay low. */
  binds: number[];
  /** Object URLs created minus revoked. Leak detector: bounded by maxResident. */
  liveUrls: number;
  reducedMotion: boolean;
}

export interface ScrollCinema {
  destroy(): void;
  /** Live internals, for tests and dogfooding. */
  debug(): ScrollCinemaDebug;
}

const DEFAULTS = {
  tau: 0.096,
  fade: 0.1,
  maxResident: 3,
  seekEpsilon: 1 / 48,
  strategy: "blob" as const,
};

/**
 * Beyond this gap the tab was almost certainly backgrounded, so we snap rather
 * than integrate. Below it we use the true elapsed time — clamping every dt
 * would silently slow the easing under jank, reintroducing the frame-rate
 * dependence the exponential form exists to remove.
 */
const RESUME_GAP = 0.25;

export function createScrollCinema(options: ScrollCinemaOptions): ScrollCinema {
  const {
    clips,
    posters,
    stage,
    track,
    onScene,
    view = window,
    tau = DEFAULTS.tau,
    fade = DEFAULTS.fade,
    maxResident = DEFAULTS.maxResident,
    seekEpsilon = DEFAULTS.seekEpsilon,
    strategy = DEFAULTS.strategy,
  } = options;

  if (posters.length !== clips.length + 1) {
    throw new Error(
      `scroll-cinema: expected ${clips.length + 1} posters for ${clips.length} clips, got ${posters.length}`,
    );
  }

  const doc = stage.ownerDocument;
  const reducedMotion =
    options.reducedMotion ?? view.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

  // --- layers -------------------------------------------------------------
  // The poster is painted first and never removed. It is what makes the page
  // interactive immediately: scroll works against stills while clips arrive,
  // and it is the entire experience under reduced motion.
  /**
   * Whether a slot has presented at least one frame from its CURRENT source.
   *
   * This is deliberately not "is showing the exact frame requested this tick".
   * Clearing it on every scroll-driven seek would blank the video throughout a
   * scrub, which is far worse than briefly showing a frame a few milliseconds
   * stale. What it exists to prevent is revealing a freshly bound clip that is
   * still sitting at time 0 while the viewer is mid-segment.
   */
  const presented: boolean[] = [false, false];
  /**
   * Compositor-confirmed frame count per slot, reset on every rebind.
   *
   * `presented` is set by our own `seeked` handler and is what gates opacity,
   * so asserting "opacity > 0 implies presented" is circular. This counter
   * comes from requestVideoFrameCallback -- the browser telling us it actually
   * painted a frame -- giving the harness a source of truth it does not control.
   */
  const framesPresented: number[] = [0, 0];
  /** mediaTime of the most recent compositor-painted frame, per slot. */
  const lastPaintedTime: number[] = [Number.NaN, Number.NaN];
  /**
   * |painted - requested| at the FIRST frame each bind generation became
   * visible, or NaN if it has not been revealed yet.
   *
   * This is the moment the reveal gate exists to protect: a slot must not
   * appear showing a frame other than the one it was asked for. Staleness
   * AFTER that first reveal is deliberate -- the runtime keeps a stale frame up
   * rather than blanking mid-scrub -- so measuring it continuously would flag
   * intended behaviour.
   */
  const revealLag: number[] = [Number.NaN, Number.NaN];
  /** True once a bind generation has been shown; staleness is allowed after. */
  const revealed: boolean[] = [false, false];
  /** Whether the browser gives us compositor frame callbacks at all. */
  let rvfcSupported = false;
  /**
   * How close the painted frame must be to the requested one before a slot is
   * first shown. Derived from `seekEpsilon` (the runtime's own half-a-frame
   * deadband) rather than picked, so it tracks the configured frame rate.
   */
  const REVEAL_TOLERANCE = seekEpsilon * 4;
  /**
   * Wait this long for a compositor-confirmed frame before showing anyway.
   *
   * 1500ms is empirical: long enough that a seek-and-paint on a slow decoder
   * finishes well inside it, short enough that a viewer is not left staring at
   * a poster wondering if the page broke. An option because that balance is a
   * product decision, not a universal constant.
   */
  const revealTimeoutMs = options.revealTimeoutMs ?? 1500;
  /** When each slot was last bound, for the reveal deadline. */
  const bindAt: number[] = [0, 0];

  const poster = doc.createElement("img");
  poster.className = "sc-poster";
  poster.alt = "";
  poster.decoding = "async";
  // Deliberately NOT set here. On a restored or deep-linked scroll position the
  // first tick immediately swaps to a different scene, so assigning poster 0
  // eagerly costs a whole image request that is discarded -- which is exactly
  // what made `budget.mjs` charge two posters for first interaction.
  Object.assign(poster.style, {
    position: "absolute",
    inset: "0",
    width: "100%",
    height: "100%",
    objectFit: "cover",
  });
  stage.appendChild(poster);

  const videos: HTMLVideoElement[] = [];
  if (!reducedMotion) {
    for (let i = 0; i < 2; i++) {
      const v = doc.createElement("video");
      v.className = "sc-layer";
      v.muted = true;
      v.playsInline = true;
      v.preload = "auto";
      v.setAttribute("aria-hidden", "true");
      Object.assign(v.style, {
        position: "absolute",
        inset: "0",
        width: "100%",
        height: "100%",
        objectFit: "cover",
        opacity: "0",
      });
      // `seeked` says the SEEK completed, not that the frame was presented --
      // the compositor may still be showing the pre-seek frame. It is used as
      // the fallback reveal gate; requestVideoFrameCallback below is what
      // actually confirms presentation. Reading back `currentTime` proves
      // nothing either: the property reflects the REQUEST immediately.
      const slot = i;
      v.addEventListener("seeked", () => {
        presented[slot] = true;
      });
      // rVFC is not in every lib.dom; degrade rather than fail where absent.
      const rvfc = (
        v as HTMLVideoElement & { requestVideoFrameCallback?: (cb: () => void) => number }
      ).requestVideoFrameCallback?.bind(v) as
        | ((cb: (now: number, meta: { mediaTime?: number }) => void) => number)
        | undefined;
      if (rvfc) {
        rvfcSupported = true;
        // Record WHICH frame was painted, not just that one was. A freshly
        // bound clip presents frame 0 immediately; counting that would let the
        // harness accept a decoder showing the start of a clip the viewer is
        // supposed to be in the middle of.
        const onFrame = (_now?: number, meta?: { mediaTime?: number }) => {
          lastPaintedTime[slot] = meta?.mediaTime ?? Number.NaN;
          framesPresented[slot]++;
          rvfc(onFrame);
        };
        rvfc(onFrame);
      }
      stage.appendChild(v);
      videos.push(v);
    }
  }

  // --- state --------------------------------------------------------------
  /** Which segment each decoder slot holds. */
  const held: (number | null)[] = [null, null];
  const binds: number[] = [0, 0];
  /** segment -> object URL (or plain URL in stream mode). */
  const cache = new Map<string, string>();
  /** segment -> in-flight fetch, so contention cannot start duplicate loads. */
  const inFlight = new Map<number, Promise<string | null>>();
  /** segment -> abort handle, so a fetch can be cancelled when it leaves the window. */
  const controllers = new Map<number, AbortController>();
  /** Segments whose fetch failed permanently. Without this, a 404 is retried
   *  on every animation frame -- roughly 60 requests a second, forever. */
  const failed = new Map<number, { attempts: number; nextAt: number }>();
  /** Give up on a segment only after this many non-abort failures. */
  const MAX_ATTEMPTS = 3;
  /** Wait between attempts. Without it a brief outage burns every attempt in
   *  ~50ms of consecutive animation frames. */
  const RETRY_BACKOFF_MS = 2000;
  let liveUrls = 0;

  // The bound counts COMPLETED plus IN-FLIGHT clips together, because both hold
  // memory. During a crossfade two clips are bound (and held segments are never
  // evicted) while a third may still be downloading, so 3 is the true floor: a
  // smaller budget could not be honoured and would misreport what it documents.
  const RETAIN_FLOOR = 3;
  const retain = Math.max(RETAIN_FLOOR, Math.trunc(maxResident) || RETAIN_FLOOR);
  if (retain !== maxResident) {
    console.warn(
      `scroll-cinema: maxResident ${maxResident} is below the floor of ${RETAIN_FLOOR} ` +
        "(two clips are bound during a crossfade, a third may be downloading); " +
        `using ${retain}.`,
    );
  }

  let easedProgress = 0;
  let lastScene = -1;
  let lastFrameAt = 0;
  let rafId = 0;
  let destroyed = false;

  function trackProgressNow(): number {
    if (track) {
      // Measure against the track's own box rather than the document, so the
      // effect still maps correctly when content sits above or below it.
      // `-top` is how far the viewport has scrolled into the track.
      return trackProgress(
        -track.getBoundingClientRect().top,
        track.offsetHeight,
        view.innerHeight,
      );
    }
    return trackProgress(view.scrollY, doc.documentElement.scrollHeight, view.innerHeight);
  }
  easedProgress = trackProgressNow();

  // --- loading ------------------------------------------------------------
  const key = (segment: number) => String(segment);

  /**
   * Resolve a segment's playable URL, fetching at most once per segment.
   * Deduplication matters: without it, contention creates several object URLs
   * for one segment and every loser becomes unreachable and unrevokable.
   */
  function urlFor(segment: number): Promise<string | null> {
    const cached = cache.get(key(segment));
    if (cached) return Promise.resolve(cached);

    const existing = inFlight.get(segment);
    if (existing) return existing;

    if (strategy === "stream") {
      const url = clips[segment];
      cache.set(key(segment), url);
      return Promise.resolve(url);
    }

    const priorFailure = failed.get(segment);
    if (priorFailure) {
      if (priorFailure.attempts >= MAX_ATTEMPTS) return Promise.resolve(null);
      if (Date.now() < priorFailure.nextAt) return Promise.resolve(null);
    }

    const controller = new AbortController();
    controllers.set(segment, controller);
    const job = (async (): Promise<string | null> => {
      try {
        const res = await fetch(clips[segment], { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        if (destroyed) return null;
        // Another caller may have won while we awaited; keep exactly one URL.
        const won = cache.get(key(segment));
        if (won) return won;
        const url = URL.createObjectURL(blob);
        liveUrls++;
        cache.set(key(segment), url);
        // A success clears the record. Without this, three isolated blips across
        // a long session permanently disable a segment that is working fine.
        failed.delete(segment);
        return url;
      } catch (err) {
        // Degrade, never block: the poster stays up and the page still works.
        // An abort is a deliberate cancellation, not a broken asset, so it must
        // not poison the segment for the rest of the session.
        // A network blip or a 5xx should not disable the segment for the life of
        // the page; only give up after repeated failures. An abort is a
        // deliberate cancellation and is not counted at all.
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          const prior = failed.get(segment)?.attempts ?? 0;
          failed.set(segment, {
            attempts: prior + 1,
            nextAt: Date.now() + RETRY_BACKOFF_MS * 2 ** prior,
          });
        }
        return null;
      } finally {
        controllers.delete(segment);
        inFlight.delete(segment);
      }
    })();

    inFlight.set(segment, job);
    return job;
  }

  /**
   * Point a decoder at a segment. Only ever called for `bindTargets`, so two
   * concurrently-bound segments can never map to the same slot.
   */
  async function bind(segment: number): Promise<void> {
    if (destroyed || reducedMotion) return;
    if (segment < 0 || segment >= clips.length) return;

    const slot = slotFor(segment);
    if (held[slot] === segment) return;

    const url = await urlFor(segment);
    if (destroyed || url === null) return;
    // Re-check: a fast scroll may have rebound this slot while we awaited.
    if (held[slot] === segment) return;
    if (
      !bindTargets(placement(easedProgress, clips.length).segment, clips.length).includes(segment)
    ) {
      return;
    }

    held[slot] = segment;
    presented[slot] = false;
    framesPresented[slot] = 0;
    lastPaintedTime[slot] = Number.NaN;
    revealLag[slot] = Number.NaN;
    revealed[slot] = false;
    bindAt[slot] = performance.now();
    binds[slot]++;
    const v = videos[slot];
    v.style.opacity = "0";
    v.src = url;
    v.load();
  }

  /**
   * Let go of decoder slots whose segment has left the bind window.
   *
   * `evict()` refuses to reclaim a cache entry that a decoder still holds --
   * correctly, since dropping bytes out from under a playing element would be
   * worse. But after a RESUME_GAP snap the segment can jump several places at
   * once, and then the OLD pair is still held (so un-evictable) while the NEW
   * pair downloads: four clips resident against a documented bound of three.
   * Releasing first is what keeps that bound honest.
   */
  function release(targets: number[]): void {
    for (let slot = 0; slot < videos.length; slot++) {
      const seg = held[slot];
      if (seg === null || targets.includes(seg)) continue;
      held[slot] = null;
      presented[slot] = false;
      framesPresented[slot] = 0;
      lastPaintedTime[slot] = Number.NaN;
      revealLag[slot] = Number.NaN;
      revealed[slot] = false;
      const v = videos[slot];
      v.style.opacity = "0";
      // Unload UNCONDITIONALLY. An earlier version only detached when no
      // replacement was inbound -- but on a multi-segment snap both
      // replacements map onto the two existing slots, so that condition was
      // false for both and neither decoder ever let go. Clearing `held` alone
      // merely removed the clip from the cache accounting while the decoder
      // still owned the bytes: the reported number improved and the actual
      // residency did not. The poster covers the reload gap.
      v.removeAttribute("src");
      v.load();
    }
  }

  function evict(keep: number[]): void {
    // Cancel downloads that have left the window. Without this the memory bound
    // is only a bound on COMPLETED clips: a fast traversal can leave many
    // `res.blob()` calls buffering whole clips concurrently.
    for (const [segment, controller] of controllers) {
      if (keep.includes(segment)) continue;
      controller.abort();
      controllers.delete(segment);
    }
    // Prune in BOTH modes. Stream mode caches plain URLs rather than blobs, so
    // there is nothing to revoke -- but letting the map grow unbounded would
    // make the reported residency a fiction.
    for (const [k, url] of cache) {
      const segment = Number(k);
      if (keep.includes(segment)) continue;
      if (held[0] === segment || held[1] === segment) continue;
      if (strategy !== "stream") {
        URL.revokeObjectURL(url);
        liveUrls--;
      }
      cache.delete(k);
    }
  }

  // --- painting -----------------------------------------------------------
  const isReady = (v: HTMLVideoElement): boolean =>
    Number.isFinite(v.duration) && v.duration > 0 && v.readyState >= 2;

  function paint(segment: number, local: number, opacity: number): void {
    if (reducedMotion) return;
    if (segment < 0 || segment >= clips.length) return;
    const slot = slotFor(segment);
    const v = videos[slot];

    // Not this slot's segment, or no decodable data yet: stay transparent so
    // the poster shows through. Revealing early flashes frame 0 of a clip the
    // viewer is supposed to be in the middle of.
    if (held[slot] !== segment || !isReady(v)) {
      v.style.opacity = "0";
      return;
    }

    const t = timeFor(local, v.duration);
    const needsSeek = shouldSeek(v.currentTime, t, seekEpsilon);
    if (!v.seeking && needsSeek) v.currentTime = t;

    // Reveal only once the decoder has genuinely presented a requested frame.
    // `settled` is set by the `seeked` listener, or here when no seek was ever
    // needed (an incoming clip already sits at its start frame). Comparing
    // `currentTime` against the value just assigned to it would be circular.
    if (!presented[slot]) {
      if (!needsSeek && !v.seeking) presented[slot] = true;
      else {
        v.style.opacity = "0";
        return;
      }
    }
    // FIRST reveal must wait for a compositor-confirmed frame at the requested
    // position. `seeked` only says the seek completed; the compositor may still
    // be showing the pre-seek frame, which is how a slot could appear displaying
    // a moment a second away from where the viewer is. Once shown, staleness is
    // allowed -- blanking mid-scrub would be far worse.
    if (
      !revealed[slot] &&
      rvfcSupported &&
      !shouldReveal(
        lastPaintedTime[slot],
        t,
        REVEAL_TOLERANCE,
        performance.now() - (bindAt[slot] || 0),
        revealTimeoutMs,
      )
    ) {
      v.style.opacity = "0";
      return;
    }

    const shown = clamp01(opacity);
    if (shown > 0) revealed[slot] = true;
    if (shown > 0 && Number.isNaN(revealLag[slot])) {
      revealLag[slot] = Number.isFinite(lastPaintedTime[slot])
        ? Math.abs(lastPaintedTime[slot] - v.currentTime)
        : Number.POSITIVE_INFINITY;
    }
    v.style.opacity = String(shown);
  }

  function tick(now: number): void {
    if (destroyed) return;
    const raw = lastFrameAt ? (now - lastFrameAt) / 1000 : 0;
    lastFrameAt = now;
    // Use true elapsed time; only a tab-resume-sized gap snaps.
    const dt = raw > RESUME_GAP ? Number.POSITIVE_INFINITY : raw;

    easedProgress = easeToward(easedProgress, trackProgressNow(), dt, tau);
    const { segment, local } = placement(easedProgress, clips.length);

    // Scene index tracks the nearest *boundary*, which is what copy should
    // follow — distinct from `segment`, which is the clip being scrubbed.
    const exact = easedProgress * clips.length;
    const scene = Math.min(posters.length - 1, Math.max(0, Math.round(exact)));
    // lastScene starts at -1, so the first tick always assigns exactly one poster.
    if (scene !== lastScene) {
      lastScene = scene;
      poster.src = posters[scene];
      onScene?.(scene);
    }

    if (!reducedMotion) {
      // Bind ONLY current + next. `residentSet` is a retention policy and
      // includes the previous clip, which shares a slot with the next one.
      const targets = bindTargets(segment, clips.length);
      // Release BEFORE binding: a held-but-stale slot would otherwise pin its
      // cache entry through the whole download of its replacement.
      release(targets);
      for (const s of targets) void bind(s);
      evict(residentSet(segment, clips.length, retain));

      const f = fadeAt(local, fade);
      paint(segment, local, 1 - f);
      paint(segment + 1, 0, f);
    }

    rafId = view.requestAnimationFrame(tick);
  }

  rafId = view.requestAnimationFrame(tick);

  return {
    destroy(): void {
      if (destroyed) return;
      destroyed = true;
      view.cancelAnimationFrame(rafId);
      // Cancel in-flight downloads: without this a teardown mid-load keeps
      // pulling megabytes into a page that no longer exists.
      for (const c of controllers.values()) c.abort();
      controllers.clear();
      inFlight.clear();
      for (const v of videos) {
        v.removeAttribute("src");
        v.load();
        v.remove();
      }
      if (strategy !== "stream") {
        for (const url of cache.values()) {
          URL.revokeObjectURL(url);
          liveUrls--;
        }
      }
      cache.clear();
      poster.remove();
    },
    debug(): ScrollCinemaDebug {
      const { segment, local } = placement(easedProgress, clips.length);
      return {
        scene: lastScene,
        segment,
        local,
        progress: easedProgress,
        decoders: videos.length,
        held: [...held],
        settled: [...presented],
        framesPresented: [...framesPresented],
        lastPaintedTime: [...lastPaintedTime],
        revealLag: [...revealLag],
        resident: [...cache.keys()].map(Number).sort((a, b) => a - b),
        inFlight: [...inFlight.keys()].sort((a, b) => a - b),
        times: videos.map((v) => v.currentTime),
        opacity: videos.map((v) => Number(v.style.opacity || "0")),
        binds: [...binds],
        liveUrls,
        reducedMotion,
      };
    },
  };
}
