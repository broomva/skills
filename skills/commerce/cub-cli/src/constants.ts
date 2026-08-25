/**
 * Store constants, recovered from the storefront's own SSR payload.
 * Override any of these with `cub config set <key> <value>` or env vars —
 * they are location-specific, not universal.
 */
export const DEFAULTS = {
  origin: "https://www.cub.com",
  endpoint: "https://www.cub.com/graphql",
  retailerSlug: "cub",
  retailerId: "142",
  /** Retailer *location* id — the prefix in item ids (`items_24999-<productId>`). */
  retailerLocationId: "24999",
  shopId: "9758",
  zoneId: "205",
  postalCode: "55113",
  coordinates: { latitude: 45.013695, longitude: -93.156822 },
  userAgent:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
} as const;

/** Minimum gap between requests. This is a personal-use client, not a crawler. */
export const MIN_REQUEST_INTERVAL_MS = 1_100;
