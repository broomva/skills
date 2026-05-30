"""Interceptor driver — a thin, mockable wrapper around the `interceptor` CLI.

The `interceptor` CLI controls a real Chrome from inside an extension (zero CDP
fingerprint, stays logged into the user's session). It is the only programmatic
path to TradingView's built-in Paper Trading broker, which has no inbound API.

This module exists so the TradingView-Paper client depends on a small `Driver`
**Protocol**, not on the CLI directly. That makes the client unit-testable: CI
has no browser, so tests inject a FakeDriver and assert the *sequence* of driver
calls. The real `InterceptorDriver` is exercised only by the live dogfood (which
needs a browser + a logged-in session).

Selector resilience: TradingView's element refs (`e21`, …) are assigned per
read and are not stable across sessions. The client therefore never hardcodes a
ref — it calls `find(role, name)`, which re-reads the tree and resolves the
current ref by semantic role + name. If the DOM shifts, the *names* are far more
stable than the refs.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from typing import NamedTuple, Protocol, runtime_checkable

import structlog

log = structlog.get_logger("tradingview_bridge.interceptor_driver")

# Compact-tree element: `[ref|role|name|attr=val ...]`
_ELEMENT_RE = re.compile(r"\[([^|\]]+)\|([^|\]]+)\|([^|\]]*?)(?:\|[^\]]*)?\]")


class Element(NamedTuple):
    """One node from the Interceptor compact accessibility tree."""

    ref: str
    role: str
    name: str


def parse_elements(tree: str) -> list[Element]:
    """Parse the Interceptor compact tree into (ref, role, name) tuples."""
    out: list[Element] = []
    for m in _ELEMENT_RE.finditer(tree):
        out.append(
            Element(ref=m.group(1).strip(), role=m.group(2).strip(), name=m.group(3).strip())
        )
    return out


def find_ref(tree: str, role: str, name: str, *, exact: bool = False) -> str | None:
    """Return the ref of the first element matching role + name, or None.

    `name` matching is case-insensitive; substring by default, exact when asked.
    """
    name_lower = name.lower()
    for el in parse_elements(tree):
        if el.role != role:
            continue
        el_name = el.name.lower()
        if (exact and el_name == name_lower) or (not exact and name_lower in el_name):
            return el.ref
    return None


class InterceptorError(RuntimeError):
    """Raised when the interceptor CLI is unavailable or a command fails."""


@runtime_checkable
class Driver(Protocol):
    """The minimal browser-control surface the TradingView-Paper client needs."""

    async def open(self, url: str, *, reuse: bool = True) -> str: ...
    async def read_tree(self) -> str: ...
    async def read_text(self) -> str: ...
    async def find(self, role: str, name: str, *, exact: bool = False) -> str | None: ...
    async def act(self, ref: str) -> None: ...
    async def type(self, ref: str, value: str) -> None: ...
    async def screenshot(self, path: str) -> None: ...


class InterceptorDriver:
    """Real driver — shells out to the `interceptor` CLI via asyncio subprocess."""

    def __init__(self, binary: str = "interceptor", timeout_s: float = 30.0) -> None:
        self._binary = binary
        self._timeout_s = timeout_s

    def available(self) -> bool:
        """True if the interceptor binary is on PATH."""
        return shutil.which(self._binary) is not None

    async def _run(self, *args: str) -> str:
        if not self.available():
            raise InterceptorError(
                f"`{self._binary}` CLI not found on PATH. The TradingView-Paper "
                "adapter requires the Interceptor browser extension + CLI. Use "
                "TVBRIDGE_BROKER_MODE=mock where no browser is available (e.g. CI)."
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_s)
        except (TimeoutError, OSError) as e:
            raise InterceptorError(f"interceptor {' '.join(args)} failed: {e}") from e
        if proc.returncode != 0:
            raise InterceptorError(
                f"interceptor {' '.join(args)} exited {proc.returncode}: "
                f"{stderr.decode('utf-8', errors='replace')[:300]}"
            )
        return stdout.decode("utf-8", errors="replace")

    async def open(self, url: str, *, reuse: bool = True) -> str:
        args = ["open", url, "--text-only"]
        if reuse:
            args.append("--reuse")
        return await self._run(*args)

    async def read_tree(self) -> str:
        return await self._run("read", "--tree-format", "compact", "--tree-only")

    async def read_text(self) -> str:
        return await self._run("read", "--text-only")

    async def find(self, role: str, name: str, *, exact: bool = False) -> str | None:
        tree = await self.read_tree()
        return find_ref(tree, role, name, exact=exact)

    async def act(self, ref: str) -> None:
        await self._run("act", ref, "--no-read")

    async def type(self, ref: str, value: str) -> None:
        await self._run("act", ref, value, "--no-read")

    async def screenshot(self, path: str) -> None:
        # interceptor exposes screenshots via the extension; fall back to a
        # no-op-safe call. The dogfood uses `interceptor` directly for capture.
        await self._run("screenshot", "--output", path)
