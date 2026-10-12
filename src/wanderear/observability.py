"""Optional observability (Sentry) with zero hard dependency.

If `sentry-sdk` is installed and `SENTRY_DSN` is set, ``span()`` records child
spans with model/classifier attributes — the latency/cost evidence the write-up
needs. Otherwise it's a no-op context manager.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

_sentry = None
_initialized = False


def _init() -> None:
    global _sentry, _initialized
    if _initialized:
        return
    _initialized = True
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, traces_sample_rate=1.0)
        _sentry = sentry_sdk
    except Exception:
        _sentry = None


def enabled() -> bool:
    _init()
    return _sentry is not None


@contextmanager
def span(op: str, **data):
    """Time an operation and record it in Sentry when configured."""
    _init()
    if _sentry is None:
        yield
        return
    with _sentry.start_span(op=op) as sp:
        for key, value in data.items():
            try:
                sp.set_data(key, value)
            except Exception:
                pass
        yield