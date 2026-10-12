import math

from wanderear import audio, embeddings
from wanderear.classify import Label


def _tone(freq: float, seconds: float = 0.3, rate: int = 16_000) -> audio.AudioBuffer:
    n = int(seconds * rate)
    return audio.AudioBuffer(
        [0.5 * math.sin(2 * math.pi * freq * i / rate) for i in range(n)], rate
    )


def test_band_energies_length_and_range():
    bands = audio.band_energies(_tone(1000), bands=12)
    assert len(bands) == 12
    assert max(bands) == 0.0  # peak-normalized


def test_embedding_is_normalized():
    vec = embeddings.embed(_tone(800), [Label("Stream", 0.8)])
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-6


def test_cosine_identical_is_one():
    vec = embeddings.embed(_tone(800), [Label("Stream", 0.8)])
    assert abs(embeddings.cosine(vec, vec) - 1.0) < 1e-6


def test_similar_sounds_score_higher_than_different():
    low = embeddings.embed(_tone(150), [Label("Stream", 0.9)])
    high = embeddings.embed(_tone(6000), [Label("Insects", 0.9)])
    low2 = embeddings.embed(_tone(160), [Label("Stream", 0.9)])
    assert embeddings.cosine(low, low2) > embeddings.cosine(low, high)


def test_label_vector_ignores_unknown_gracefully():
    vec = embeddings.label_vector([Label("NotARealLabel", 0.5)])
    assert len(vec) == len(embeddings.LABEL_VOCAB)
    assert sum(vec) > 0