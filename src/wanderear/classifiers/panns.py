"""PANNs classifier (AudioSet CNN14) via the optional `panns-inference` package.

A stronger alternative to YAMNet for the same AudioSet tag space. Lazy import;
the app falls back if the dependency is missing.
"""

from __future__ import annotations

from .. import audio
from ..classify import Label, register


@register
class PannsClassifier:
    name = "panns"

    def __init__(self) -> None:
        try:
            import numpy as np
            from panns_inference import AudioTagging, labels
        except ImportError as exc:
            raise RuntimeError(
                "panns needs the 'panns-inference' package (pip install panns-inference)"
            ) from exc
        self._np = np
        self._model = AudioTagging(checkpoint_path=None, device="cpu")
        self._labels = list(labels)

    def classify(self, buffer: audio.AudioBuffer, top_n: int = 5) -> list[Label]:
        np = self._np
        samples = np.asarray(buffer.samples, dtype="float32")[None, :]
        clipwise, _ = self._model.inference(samples)
        scores = np.asarray(clipwise).reshape(-1)[: len(self._labels)]
        order = np.argsort(scores)[::-1][:top_n]
        return [
            Label(self._labels[i], round(float(scores[i]), 3))
            for i in order
            if scores[i] > 1e-4
        ] or [Label("Ambient hum", 0.5)]