// Vendored from @broomva/scroll-cinema v0.2.0 (github.com/broomva/scroll-cinema).
// Vendored rather than depended on because the package is not published to npm
// and CI installs with --frozen-lockfile against the public registry, so a
// file: dependency resolves on this laptop and nowhere else. The runtime has no
// dependencies of its own, so the whole of it is these three files.
export type { Placement } from "./map";
export {
  bindTargets,
  clamp,
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
export type {
  ScrollCinema,
  ScrollCinemaDebug,
  ScrollCinemaOptions,
} from "./scrubber";
export { createScrollCinema } from "./scrubber";
