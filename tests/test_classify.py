import math

from wanderear import audio
from wanderear.classify import Label, PassthroughClassifier, get_classifier, list_classifiers


def _tone(freq: float, seconds: float = 0.3, rate: int = 16_000) -> audio.AudioBuffer:
    n = int(seconds * rate)
    return audio.AudioBuffer(
        [0.5 * math.sin(2 * math.pi * freq * i / rate) for i in range(n)], rate
    )


def test_registry_lists_passthrough():
    assert "passthrough" in list_classifiers()


def test_get_classifier_returns_backend():
    assert get_classifier("passthrough").name == "passthrough"


def test_silence_detected():
    labels = PassthroughClassifier().classify(audio.AudioBuffer([0.0] * 4000, 16_000))
    assert labels[0].name == "Silence"


def test_tone_produces_normalized_labels():
    labels = PassthroughClassifier().classify(_tone(3000), top_n=3)
    assert labels
    assert all(0.0 <= lab.confidence <= 1.0 for lab in labels)
    assert isinstance(labels[0], Label)