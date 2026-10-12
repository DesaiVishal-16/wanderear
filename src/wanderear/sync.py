"""Optional sync: push local postcards + media to a gallery endpoint.

Fully opt-in. The local store stays the source of truth; sync is idempotent
(re-running never duplicates). Works against ``web/server.py`` or the Render
gallery. Uses only the standard library so it never blocks the offline path.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .store import LocalStore


def _request(url: str, method: str = "GET", data: bytes | None = None,
             content_type: str = "application/json", timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", content_type)
    token = os.environ.get("WANDEREAR_SYNC_TOKEN")
    if token:
        req.add_header("X-WanderEar-Token", token)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def remote_ids(endpoint: str, timeout: float = 30.0) -> set[str]:
    data = _request(f"{endpoint.rstrip('/')}/api/postcards", timeout=timeout)
    items = data if isinstance(data, list) else data.get("postcards", [])
    return {c.get("id") for c in items if isinstance(c, dict) and c.get("id")}


def sync(store: LocalStore, endpoint: str, timeout: float = 30.0) -> dict:
    """Upload postcards (and their media) not yet present on the endpoint."""
    endpoint = endpoint.rstrip("/")
    try:
        existing = remote_ids(endpoint, timeout)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"cannot reach gallery at {endpoint}: {exc}") from exc

    uploaded = 0
    media_uploaded = 0
    for card in store.all():
        if card["id"] in existing:
            continue
        _request(
            f"{endpoint}/api/postcards",
            method="POST",
            data=json.dumps(card).encode(),
            timeout=timeout,
        )
        uploaded += 1
        for key in ("audio_path", "spectrogram_path"):
            path = card.get(key)
            if not path:
                continue
            path = Path(path)
            if not path.exists():
                continue
            try:
                _request(
                    f"{endpoint}/api/media/{path.name}",
                    method="POST",
                    data=path.read_bytes(),
                    content_type="application/octet-stream",
                    timeout=timeout,
                )
                media_uploaded += 1
            except (urllib.error.URLError, OSError):
                pass
    return {"uploaded": uploaded, "media": media_uploaded, "already": len(existing)}