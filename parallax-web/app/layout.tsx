import type { Metadata } from "next";
import "./globals.css";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
// This repository does not publish the site, so there is no canonical origin to
// assert. Set NEXT_PUBLIC_SITE_URL at publish time; until then the metadata base
// is local and says so rather than pointing at an address nothing here serves.
const site = process.env.NEXT_PUBLIC_SITE_URL ?? `http://localhost:3000${base}/`;

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
