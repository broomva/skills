"""Factory helper that returns a `client_factory` callable.

`GarminTraceSource(client_factory=...)` expects a no-arg callable that
returns a configured Garmin client. This helper wraps the FakeGarminClient
construction so tests can write:

    source = GarminTraceSource(client_factory=make_fake_client_factory())

…and the same factory exposes the underlying client for inspection:

    factory, client = make_fake_client_factory_with_handle()
    use_case.execute(...)
    assert client.call_methods()[0] == "login"
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tests.fixtures.garmin.fake_client import FakeGarminClient

__all__ = ["make_fake_client_factory", "make_fake_client_factory_with_handle"]


def make_fake_client_factory(
    client: FakeGarminClient | None = None,
    **overrides: Any,
) -> Callable[[], FakeGarminClient]:
    """Return a `client_factory` callable suitable for `GarminTraceSource`.

    If `client` is given, every call returns that exact instance — the test
    can hold the same handle and assert on `client.call_log` after the
    use-case runs.

    If `client` is None, the first call constructs a fresh
    `FakeGarminClient(**overrides)` and every subsequent call returns the
    same instance. Singleton-per-factory is the right shape because the
    real adapter caches its `Garmin` instance for the lifetime of a sync
    run.
    """
    if client is not None and overrides:
        raise ValueError(
            "Pass either `client` OR keyword overrides — not both. "
            "(Overrides are ignored when a concrete client is supplied.)"
        )

    held: list[FakeGarminClient] = [client] if client is not None else []

    def factory() -> FakeGarminClient:
        if not held:
            held.append(FakeGarminClient(**overrides))
        return held[0]

    return factory


def make_fake_client_factory_with_handle(
    **overrides: Any,
) -> tuple[Callable[[], FakeGarminClient], FakeGarminClient]:
    """Return both the factory and a handle to the underlying client.

    The handle is the instance the factory will return; mutate
    `client.raise_on_call` after construction to schedule failures, or
    inspect `client.call_log` after the use-case runs.
    """
    client = FakeGarminClient(**overrides)
    factory = make_fake_client_factory(client=client)
    return factory, client
