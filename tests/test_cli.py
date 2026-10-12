import math
import struct
import wave

from wanderear.cli import main


def _write_wav(path, freq=1000.0, seconds=0.4, rate=16_000):
    n = int(seconds * rate)
    ints = [int(0.5 * 32767 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(ints)}h", *ints))


def test_analyze_creates_postcard(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WANDEREAR_HOME", str(tmp_path / "home"))
    wav = tmp_path / "tone.wav"
    _write_wav(wav)
    assert main(["analyze", str(wav), "--narrator", "template", "--no-spectrogram"]) == 0
    out = capsys.readouterr().out
    assert "sounds:" in out
    assert "postcard:" in out


def test_list_after_analyze(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WANDEREAR_HOME", str(tmp_path / "home"))
    wav = tmp_path / "tone.wav"
    _write_wav(wav)
    main(["analyze", str(wav), "--narrator", "template", "--no-spectrogram"])
    capsys.readouterr()
    assert main(["list"]) == 0
    assert "tone.wav" not in capsys.readouterr().out


def test_gallery_generates_html(tmp_path, monkeypatch):
    monkeypatch.setenv("WANDEREAR_HOME", str(tmp_path / "home"))
    wav = tmp_path / "tone.wav"
    _write_wav(wav)
    main(["analyze", str(wav), "--narrator", "template", "--no-spectrogram"])
    out = tmp_path / "gallery.html"
    assert main(["gallery", "--out", str(out)]) == 0
    assert out.exists()
    assert "WanderEar" in out.read_text()


def test_doctor_runs(capsys):
    assert main(["doctor"]) == 0
    assert "doctor" in capsys.readouterr().out.lower()


def test_search_like_saved_postcard(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WANDEREAR_HOME", str(tmp_path / "home"))
    wav = tmp_path / "tone.wav"
    _write_wav(wav)
    main(["analyze", str(wav), "--narrator", "template", "--no-spectrogram"])
    capsys.readouterr()

    from wanderear.store import LocalStore

    card_id = LocalStore().all()[0]["id"]
    assert main(["search", "--like", card_id, "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert card_id in out


def test_search_file_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WANDEREAR_HOME", str(tmp_path / "home"))
    wav = tmp_path / "tone.wav"
    _write_wav(wav)
    main(["analyze", str(wav), "--narrator", "template", "--no-spectrogram"])
    assert main(["search", "--file", str(wav)]) == 0


def test_search_requires_exactly_one_source(capsys):
    assert main(["search"]) == 2