import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from wanderear.classify import Label
from wanderear.narrate import Narration
from wanderear.postcard import build_context, build_postcard
from wanderear.store import LocalStore
from wanderear.sync import sync


class _Handler(BaseHTTPRequestHandler):
    postcards: list = []
    media: dict = {}

    def log_message(self, *a):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/postcards":
            return self._json(_Handler.postcards)
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.path == "/api/postcards":
            _Handler.postcards.append(json.loads(body))
            return self._json({"ok": True}, 201)
        if self.path.startswith("/api/media/"):
            _Handler.media[self.path.rsplit("/", 1)[-1]] = body
            return self._json({"ok": True}, 201)
        self.send_error(404)


def _start_server():
    _Handler.postcards = []
    _Handler.media = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_sync_uploads_once(tmp_path):
    server = _start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        store = LocalStore(home=tmp_path)
        store.ensure()
        media = store.media / "clip.wav"
        media.write_bytes(b"RIFFfakewav")
        narration = Narration("creek", "body", "template")
        card = build_postcard([Label("Stream", 0.9)], narration, 4.0, "test", build_context())
        store.save(card, [media])

        result = sync(store, url)
        assert result["uploaded"] == 1
        assert len(_Handler.postcards) == 1
        assert "clip.wav" in _Handler.media

        again = sync(store, url)
        assert again["uploaded"] == 0
        assert again["already"] == 1
    finally:
        server.shutdown()