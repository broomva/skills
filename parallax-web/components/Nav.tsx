import { REPO } from "../lib/repo";

const LINKS: Array<[string, string]> = [
  ["How it works", "#how"],
  ["Guarantees", "#guarantees"],
  ["For agents", "#surface"],
  ["Use case", "use-cases/"],
  ["Cinema", "scroll-cinema/"],
  ["Proof", "proof/"],
  ["Demo", "demo/"],
];

export function Nav({ base }: { base: string }) {
  return (
    <header className="nav">
      <a className="brand" href={`${base}/`}>
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <title>Parallax</title>
          {/* one baseline, two rays: the mark is the measurement */}
          <path
            d="M2 15 L9 9"
            stroke="currentColor"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
          />
          <path
            d="M9 9 L16 3"
            stroke="currentColor"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
            strokeDasharray="1 3.2"
          />
          <path
            d="M9 9 L16 12"
            stroke="oklch(0.60 0.12 260)"
            strokeWidth="1.6"
            fill="none"
            strokeLinecap="round"
            strokeDasharray="1 3.2"
          />
          <circle cx="9" cy="9" r="2" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </svg>
        Parallax
      </a>
      <nav className="links" aria-label="Sections">
        {LINKS.map(([label, href]) => (
          <a key={href} href={href.startsWith("#") ? href : `${base}/${href}`}>
            {label}
          </a>
        ))}
      </nav>
      <a className="navcta" href={REPO} rel="noopener">
        Read the source
      </a>
    </header>
  );
}
