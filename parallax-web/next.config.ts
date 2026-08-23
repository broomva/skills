import type { NextConfig } from "next";

// This repository publishes no site. The export is built at the domain root by
// default, and NEXT_PUBLIC_BASE_PATH is set only if it is ever served under a
// path prefix. It is an env var rather than a literal because a hard-coded
// prefix breaks every asset on the page at once with no obvious cause.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  // The app is a nested package in a monorepo, so the workspace root is pinned
  // to this directory rather than inferred.
  turbopack: { root: import.meta.dirname },
  // The export is static: no Node server at serve time, everything emitted as
  // files at build time.
  output: "export",
  basePath,
  // /proof -> /proof/index.html. Without this the export writes /proof.html,
  // which a static host will serve but which breaks every relative URL inside it.
  trailingSlash: true,
  images: { unoptimized: true },
  // A build that type-errors should fail here, not in a browser.
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
