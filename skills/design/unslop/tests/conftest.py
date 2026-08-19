"""Shared fixtures: two synthetic repos — SLOPPY (every tell present) and CRAFTED (clears the floor)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _w(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def sloppy_repo(tmp_path: Path) -> Path:
    root = tmp_path / "sloppy"
    _w(root, "package.json", json.dumps({
        "name": "sloppy", "dependencies": {"next": "15.0.0", "react": "19.0.0", "lucide-react": "0.5.0",
                                            "@heroicons/react": "2.0.0", "class-variance-authority": "0.7.0"},
        "devDependencies": {"tailwindcss": "4.0.0", "typescript": "5.0.0"}}))
    _w(root, "src/app/layout.tsx", """
import { Inter, Space_Grotesk } from "next/font/google";
const inter = Inter({ subsets: ["latin"] });
export default function RootLayout({ children }) { return <html className={inter.className}><body>{children}</body></html>; }
""")
    _w(root, "src/app/page.tsx", """
import { Check, Sparkles } from "lucide-react";
import { ArrowRightIcon } from "@heroicons/react/24/solid";
export default async function Home() {
  const data = await fetch("https://api.example.com/stats").then(r => r.json());
  return (
    <main className="bg-gradient-to-r from-purple-500 to-black rounded-2xl rounded-md rounded-lg rounded-xl rounded-full rounded-sm rounded-3xl">
      <section className="hero">
        <h1>Supercharge your workflow — effortlessly ✨</h1>
        <p>It's not a tool, it's a movement. Lorem ipsum dolor sit amet — the future is here — today.</p>
        <button>Get started free 🚀</button>
        <ul><li>✓ 10x faster</li><li>✓ 99.9% uptime</li><li>✓ Seamless</li></ul>
        <img src="https://images.unsplash.com/photo-123" alt="team" />
      </section>
      <section className="testimonials">
        <blockquote>"Amazing" — John Doe, CEO at Acme Inc.</blockquote>
      </section>
      <section id="pricing"><div>Free</div><div>Pro</div><div>Enterprise</div></section>
      <div style={{color:"#123456", background:"#abcdef", borderColor:"#0f0f0f"}} className="shadow-lg shadow-md shadow-xl shadow-2xl shadow-sm shadow-inner" />
    </main>
  );
}
""")
    _w(root, "src/components/Card.tsx", """
import { Star } from "lucide-react";
export function Card() {
  return <div className="rounded-[13px] backdrop-blur-lg animate-bounce" style={{color:"#111111",background:"#222222",border:"#333333 #444444 #555555 #666666 #777777 #888888 #999999 #aaaaaa"}}>TODO: copy</div>;
}
""")
    _w(root, "src/app/globals.css", """
@keyframes float { from { transform: translateY(0) } to { transform: translateY(-10px) } }
body { font-family: Inter, -apple-system, sans-serif; background: linear-gradient(135deg, #7c3aed, #000); }
.glass { backdrop-filter: blur(20px); }
""")
    _w(root, "src/lib/api.ts", "export async function load() { return fetch('/api/x').then(r => r.json()); }\n")
    return root


@pytest.fixture
def crafted_repo(tmp_path: Path) -> Path:
    root = tmp_path / "crafted"
    _w(root, "package.json", json.dumps({
        "name": "crafted", "dependencies": {"next": "15.0.0", "react": "19.0.0", "lucide-react": "0.5.0", "@tanstack/react-query": "5.0.0"},
        "devDependencies": {"tailwindcss": "4.0.0"}}))
    _w(root, "DESIGN.md", "# Ledgerline\n\nTypography: Signifier (self-hosted) for display; body uses the system stack deliberately.\nIcons: Lucide, 1.5px stroke, chosen for the operate surface.\n")
    _w(root, "PRODUCT.md", "# Ledgerline\nBookkeeping for two-person studios.\n")
    _w(root, "src/app/layout.tsx", """
import "./globals.css";
export default function RootLayout({ children }) { return <html><body>{children}<footer><a href="/terms">Terms</a><a href="/privacy">Privacy</a></footer></body></html>; }
""")
    _w(root, "src/app/globals.css", """
@font-face { font-family: 'Signifier'; src: url('/fonts/Signifier.woff2') format('woff2'); font-display: swap; }
:root { --font-display: 'Signifier', Georgia, serif; --color-ink: #1b1f2a; --color-paper: #f7f5f0; --radius-control: 0.375rem; --radius-card: 0.75rem; }
h1, h2 { font-family: 'Signifier', Georgia, serif; }
body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
.fade { animation: fade 240ms ease-out; }
@keyframes fade { from { opacity: 0 } to { opacity: 1 } }
@media (prefers-reduced-motion: reduce) { .fade { animation: none; } }
""")
    _w(root, "src/app/page.tsx", """
import { Receipt } from "lucide-react";
export default function Home() {
  return <main className="rounded-md"><h1>Ledgerline</h1><p>Bookkeeping for two-person studios.</p><img src="/images/logo.svg" alt="" /><video src="/media/ledgerline-demo.mp4" controls /><img src="/screenshots/dashboard.png" alt="The Ledgerline dashboard with March reconciled" /></main>;
}
""")
    _w(root, "src/app/terms/page.tsx", "export default function Terms() { return <article><h1>Terms of service</h1></article>; }\n")
    _w(root, "src/app/privacy/page.tsx", "export default function Privacy() { return <article><h1>Privacy policy</h1></article>; }\n")
    _w(root, "src/app/ledger/page.tsx", """
import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
export default function Ledger() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["ledger"], queryFn: () => fetch("/api/ledger").then(r => r.json()) });
  if (isLoading) return <Skeleton aria-busy="true" />;
  if (isError) return <p role="alert">Could not load the ledger. Retry.</p>;
  if (data.length === 0) return <p>No entries yet. Add your first receipt.</p>;
  return <ul className="rounded-md">{data.map(d => <li key={d.id}>{d.memo}</li>)}</ul>;
}
""")
    _w(root, "src/app/ledger/loading.tsx", "export default function Loading() { return <div aria-busy=\"true\" />; }\n")
    _w(root, "src/app/error.tsx", "'use client';\nexport default function Error() { return <p>Something went wrong.</p>; }\n")
    ev = root / ".unslop" / "evidence"
    ev.mkdir(parents=True)
    for name in ("index-1280.png", "index-390.png", "ledger-1280.png", "ledger-390.png",
                 "terms-1280.png", "terms-390.png", "privacy-1280.png", "privacy-390.png"):
        (ev / name).write_bytes(b"\x89PNG" + b"\x00" * 9000)
    return root


@pytest.fixture
def evidence_dir(crafted_repo: Path) -> Path:
    return crafted_repo / ".unslop" / "evidence"
