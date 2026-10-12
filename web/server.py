"""Local web app + optional hosted gallery for WanderEar.

Serves the interactive SPA in ``web/`` and a small JSON API. It doubles as the
hosted (Render) gallery: image/audio + postcards, plus a local-only analyze
endpoint so you can record or upload a soundscape straight from the browser.

Endpoints
  GET  /healthz                    → liveness probe (200 when serving)
  GET  /api/status                 → environment + capability summary
  GET  /api/postcards              → JSON list of postcards
  POST /api/postcards              → append a postcard (idempotent by id)
  POST /api/analyze?name=&classifier=&narrator=
                                   → turn uploaded audio into a postcard
  GET  /api/search?like=<id>&limit= → rank saved postcards by similarity
  GET  /media/<name>               → serve a stored wav/png
  POST /api/media/<name>           → store an uploaded wav/png

Everything works offline. The cloud gallery is optional.

Auth: when ``WANDEREAR_SYNC_TOKEN`` is set, the write endpoints
(``POST /api/postcards`` and ``POST /api/media/*``) require either an
``X-WanderEar-Token`` header or ``Authorization: Bearer <token>``. Reads stay
public. ``wanderear sync`` sends the token automatically.
"""

from __future__ import annotations

import hmac
import json
import os
import signal
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SRC = Path(__file__).resolve().parent.parent / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

HOME = Path(os.environ.get("WANDEREAR_HOME", Path.home() / ".wanderear"))
INDEX = HOME / "index.jsonl"
WEB = Path(__file__).resolve().parent
TOKEN = os.environ.get("WANDEREAR_SYNC_TOKEN")

_MAX_UPLOAD = 64 * 1024 * 1024  # 64 MB
_MEDIA_SUFFIXES = {".wav", ".flac", ".png", ".jpg", ".jpeg"}


def _read_index() -> list[dict]:
    if not INDEX.exists():
        return []
    return [json.loads(line) for line in INDEX.read_text().splitlines() if line.strip()]


def _append(card: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    existing = {c.get("id") for c in _read_index()}
    if card.get("id") in existing:
        return
    with INDEX.open("a") as fh:
        fh.write(json.dumps(card) + "\n")


class Handler(SimpleHTTPRequestHandler):
    server_version = "WanderEar"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    # ------------------------------------------------------------------ helpers
    def _json(self, payload, status=200, cors=False):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        """True when no token is configured, or the request carries it."""
        if not TOKEN:
            return True
        supplied = self.headers.get("X-WanderEar-Token", "")
        if not supplied:
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                supplied = auth[len("Bearer "):]
        return hmac.compare_digest(supplied, TOKEN)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return b""
        if length > _MAX_UPLOAD:
            raise ValueError("upload too large")
        return self.rfile.read(length)

    def _query(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    # ------------------------------------------------------------------- routes
    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/healthz":
            return self._json({"status": "ok"})
        if route == "/api/postcards":
            return self._json(_read_index(), cors=True)
        if route == "/api/status":
            return self._json(_status(), cors=True)
        if route == "/api/search":
            return self._search()
        if route == "/api/analyze":
            return self._json({"error": "use POST /api/analyze with audio bytes"}, 405)
        if route.startswith("/media/"):
            return self._serve_media(self.path[len("/media/"):])
        return super().do_GET()

    def _serve_media(self, name: str):
        target = (HOME / "media" / os.path.basename(name)).resolve()
        media_root = (HOME / "media").resolve()
        if not str(target).startswith(str(media_root)) or not target.exists():
            return self.send_error(404)
        data = target.read_bytes()
        self.send_response(200)
        ctype = "image/png" if target.suffix == ".png" else "audio/wav"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        route = urlparse(self.path).path
        if route == "/api/postcards":
            if not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            try:
                card = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json({"error": "invalid json"}, 400)
            _append(card)
            return self._json({"ok": True, "id": card.get("id")}, 201)
        if route == "/api/analyze":
            return self._analyze()
        if route.startswith("/api/media/"):
            if not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            name = os.path.basename(self.path[len("/api/media/"):])
            if Path(name).suffix.lower() not in _MEDIA_SUFFIXES:
                return self._json({"error": "unsupported media type"}, 415)
            try:
                data = self._read_body()
            except ValueError as exc:
                return self._json({"error": str(exc)}, 413)
            (HOME / "media").mkdir(parents=True, exist_ok=True)
            (HOME / "media" / name).write_bytes(data)
            return self._json({"ok": True, "name": name}, 201)
        return self.send_error(404)

    # ----------------------------------------------------------------- pipeline
    def _search(self):
        from wanderear import embeddings
        from wanderear.classify import Label
        from wanderear.store import LocalStore

        query = self._query()
        like = (query.get("like") or [""])[0]
        try:
            limit = max(1, min(50, int((query.get("limit") or ["5"])[0])))
        except ValueError:
            limit = 5
        store = LocalStore(HOME)
        item = store.get(like) if like else None
        if not item:
            return self._json({"error": f"no postcard with id {like!r}"}, 404)
        vector = item.get("embedding")
        if not vector:
            vector = embeddings.label_vector(
                [Label(lab["name"], lab["confidence"]) for lab in item.get("labels", [])]
            )
        results = store.search(vector, limit=limit)
        return self._json(
            [{"score": round(score, 4), "postcard": card} for card, score in results],
            cors=True,
        )

    def _analyze(self):
        query = self._query()
        name = (query.get("name", ["clip.webm"])[0]) or "clip.webm"
        classifier = (query.get("classifier", ["auto"])[0]) or "auto"
        narrator = (query.get("narrator", ["auto"])[0]) or "auto"
        try:
            data = self._read_body()
        except ValueError as exc:
            return self._json({"error": str(exc)}, 413)
        if not data:
            return self._json({"error": "empty upload"}, 400)

        from wanderear import audio
        from wanderear.pipeline import analyze
        from wanderear.store import LocalStore

        suffix = Path(name).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            buffer = audio.load(tmp_path)
        except Exception as exc:
            return self._json({"error": f"could not read audio: {exc}"}, 400)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        try:
            card = analyze(
                buffer,
                classifier=classifier,
                narrator=narrator,
                store=LocalStore(home=HOME),
            )
        except Exception as exc:
            return self._json({"error": str(exc)}, 500)
        return self._json(card.to_dict(), 201, cors=True)

    # keep the noise down in the console
    def log_message(self, *args):
        if os.environ.get("WANDEREAR_VERBOSE"):
            super().log_message(*args)


def _status() -> dict:
    info: dict = {"home": str(HOME), "postcards": len(_read_index())}
    try:
        from wanderear import __version__

        info["version"] = __version__
    except Exception:
        info["version"] = "unknown"
    try:
        from wanderear.classify import list_classifiers

        info["classifiers"] = list_classifiers()
    except Exception:
        info["classifiers"] = ["passthrough"]
    try:
        from wanderear.narrate import GemmaNarrator

        narrator = GemmaNarrator()
        info["gemma"] = narrator.use_installed_gemma()
        info["model"] = narrator.model if info["gemma"] else None
    except Exception:
        info["gemma"] = False
        info["model"] = None
    return info


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8000))
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True

    def _shutdown(signum, frame):  # pragma: no cover - signal path
        httpd.shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            pass

    print(f"WanderEar web app on http://{host}:{port} (home={HOME})")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
