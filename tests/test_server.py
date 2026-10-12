import importlib.util
import io
import json
import math
import struct
import threading
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest


def _load_server():
    path = Path(__file__).resolve().parents[1] / "web" / "server.py"
    spec = importlib.util.spec_from_file_location("we_web_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wav_bytes(freq=900.0, seconds=0.4, rate=16_000) -> bytes:
    n = int(seconds * rate)
    ints = [int(0.5 * 32767 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(ints)}h", *ints))
    return buf.getvalue()


@pytest.fixture()
def server(tmp_path, monkeypatch):
    module = _load_server()
    monkeypatch.setattr(module, "HOME", tmp_path)
    monkeypatch.setattr(module, "INDEX", tmp_path / "index.jsonl")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base
    finally:
        httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


def _post(url, data: bytes, content_type="audio/wav"):
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


def test_status(server):
    status, info = _get(f"{server}/api/status")
    assert status == 200
    assert "passthrough" in info["classifiers"]


def test_analyze_upload_creates_postcard(server):
    status, card = _post(
        f"{server}/api/analyze?name=tone.wav&classifier=passthrough&narrator=template",
        _wav_bytes(),
    )
    assert status == 201
    assert card["id"]
    assert card["postcard"]["title"]
    assert card["labels"]

    status, cards = _get(f"{server}/api/postcards")
    assert status == 200
    assert len(cards) == 1
    assert cards[0]["id"] == card["id"]

    status, results = _get(f"{server}/api/search?like={card['id']}&limit=3")
    assert status == 200
    assert results[0]["postcard"]["id"] == card["id"]
    assert results[0]["score"] == pytest.approx(1.0, abs=1e-3)


def test_search_unknown_id(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(f"{server}/api/search?like=nope")
    assert err.value.code == 404


def test_analyze_empty_body(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        _post(f"{server}/api/analyze?name=empty.wav", b"")
    assert err.value.code == 400