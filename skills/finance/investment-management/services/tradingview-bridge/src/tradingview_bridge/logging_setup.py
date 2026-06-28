"""Structured logging — structlog with JSON output.

Named `logging_setup.py` (not `logging.py`) to avoid shadowing the stdlib
`logging` module, which is a common foot-gun in Python projects.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

import structlog

from .settings import get_settings


def configure_logging(stream: TextIO | None = None) -> Any:
    """Configure structlog + stdlib logging once at startup.

    Returns the root bound logger. Modules should import `structlog.get_logger()`
    directly rather than passing the logger around.

    Args:
        stream: where structured logs go. Defaults to stdout (the server, where
            uvicorn captures stdout). The ``operate`` CLI passes ``sys.stderr``
            so that stdout stays a clean JSON data channel — logs are
            diagnostics (stderr), command output is data (stdout), per Unix
            convention. This is what makes ``operate tick | jq`` work.

    Returns `Any` because structlog's BoundLogger inference is dynamic and
    typing.cast / structlog.stdlib.BoundLogger don't align cleanly with what
    `make_filtering_bound_logger` produces at runtime.
    """
    out = stream if stream is not None else sys.stdout
    settings = get_settings()
    log_level = getattr(logging, settings.log_level)

    # stdlib logging — surface uvicorn / fastapi logs through structlog too
    logging.basicConfig(
        format="%(message)s",
        stream=out,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=out),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger("tradingview_bridge")
