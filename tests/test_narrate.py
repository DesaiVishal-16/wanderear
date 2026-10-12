import json

from wanderear.narrate import GemmaNarrator


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload):
    return lambda url, timeout=0: _Resp(payload)


def test_available_true_when_model_pulled(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"models": [{"name": "gemma3:4b"}]})
    )
    assert GemmaNarrator(model="gemma3:4b").available() is True


def test_available_false_when_model_missing(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"models": [{"name": "llama3:8b"}]})
    )
    assert GemmaNarrator(model="gemma3:4b").available() is False


def test_available_false_on_connection_error(monkeypatch):
    def boom(url, timeout=0):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert GemmaNarrator().available() is False


def test_use_installed_gemma_swaps_to_e2b(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"models": [{"name": "gemma3n:e2b"}, {"name": "llama3:8b"}]}),
    )
    narrator = GemmaNarrator(model="gemma3:4b")
    assert narrator.use_installed_gemma() is True
    assert narrator.model == "gemma3n:e2b"


def test_get_narrator_auto_uses_installed_gemma(monkeypatch):
    from wanderear.narrate import get_narrator

    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"models": [{"name": "gemma3n:e2b"}]})
    )
    narrator = get_narrator("auto")
    assert narrator.name == "gemma"
    assert narrator.model == "gemma3n:e2b"


def test_get_narrator_explicit_gemma_errors_without_model(monkeypatch):
    import pytest

    from wanderear.narrate import get_narrator

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"models": []}))
    with pytest.raises(RuntimeError):
        get_narrator("gemma")