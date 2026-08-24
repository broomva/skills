import type { Metadata } from "next";
import "./globals.css";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
// The address the site is actually reachable at today. This repository does not
// publish it -- GitHub goes on serving broomva/parallax's Pages build after that
// repo is archived read-only -- but that is where a reader following a share card
// still lands, so it is the honest canonical origin until something republishes.
//
// The default is deliberately NOT localhost. A localhost fallback reads as
// cautious and ships worse: the exported HTML then declares
// `og:url = http://localhost:3000/` to every crawler and chat client that
// unfurls it, which is not "no claim", it is a wrong claim that nobody can
// follow. Override with NEXT_PUBLIC_SITE_URL when the site moves (BRO-2271).
// Deliberately NOT composed with `base`. The two are different things: `base` is
// the path prefix assets are served under, while this is the one canonical
// address of the site. Composing them yields /parallax/parallax/ in any build
// that sets NEXT_PUBLIC_BASE_PATH=/parallax, which is exactly the build that
// publishes.
const site = process.env.NEXT_PUBLIC_SITE_URL ?? "https://broomva.github.io/parallax/";

export const metadata: Metadata = {
  metadataBase: new URL(site),
  title: "Parallax — simulation results you accept before they are active",
  description:
    "Point Parallax at a context. It proposes an ontology built from what is actually there, a human accepts it, and only then does it roll the model forward under candidate decisions. Every answer is typed observed or simulated.",
  applicationName: "Parallax",
  // The document is light. The two dark surfaces on it -- the opening and the
  // motion panels -- are dark because they are a film and a set of readouts,
  // not because the page is following the OS.
  colorScheme: "light",
  openGraph: {
    title: "Parallax — simulation results you accept before they are active",
    description:
      "A simulation runtime whose design target is not being right. It is being unable to lie about being a simulator.",
    url: site,
    siteName: "Parallax",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Parallax",
    description:
      "Simulation results you accept before they are active. Every answer typed observed or simulated.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="light">
      <body>{children}</body>
    </html>
  );
}
