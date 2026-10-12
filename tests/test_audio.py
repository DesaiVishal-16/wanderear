import math

from wanderear import audio


def _tone(freq: float, seconds: float = 0.5, rate: int = 16_000) -> audio.AudioBuffer:
    n = int(seconds * rate)
    samples = [0.5 * math.sin(2 * math.pi * freq * i / rate) for i in range(n)]
    return audio.AudioBuffer(samples, rate)


def test_duration():
    assert _tone(440).duration == 0.5


def test_rms_of_tone():
    assert 0.3 < audio.rms(_tone(440)) < 0.4


def test_zero_crossing_rate_higher_for_high_freq():
    assert audio.zero_crossing_rate(_tone(4000)) > audio.zero_crossing_rate(_tone(200))


def test_peak_frequency_of_tone():
    peak = audio.peak_frequency(_tone(1000, seconds=0.25))
    assert abs(peak - 1000) < 400


def test_spectral_flatness_range():
    flat = audio.spectral_flatness(_tone(440))
    assert 0.0 <= flat <= 1.0


def test_wav_roundtrip(tmp_path):
    clip = _tone(440)
    path = tmp_path / "tone.wav"
    audio.save_wav(clip, str(path))
    loaded = audio.load(str(path))
    assert len(loaded.samples) == len(clip.samples)
    assert loaded.sample_rate == clip.sample_rate