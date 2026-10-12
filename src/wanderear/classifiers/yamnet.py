from __future__ import annotations

import csv
import os
from pathlib import Path

from .. import audio
from ..classify import Label, register


def _model_dir() -> Path:
    env = os.environ.get("WANDEREAR_YAMNET_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[3] / "data" / "models"


@register
class YamNetClassifier:
    """YAMNet (AudioSet) via ONNX Runtime — 521 audio event classes.

    Expects `yamnet.onnx` and `yamnet_class_map.csv` (or a labels .txt) in
    ``WANDEREAR_YAMNET_DIR`` (default: <repo>/data/models). Raises at construction
    time if unavailable so ``get_classifier('auto')`` can fall back.
    """

    name = "yamnet"
    _SAMPLE_RATE = 16_000
    _WINDOW_SECONDS = 0.975

    def __init__(self) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("yamnet needs onnxruntime + numpy") from exc

        self._np = np
        model_dir = _model_dir()
        model_path = model_dir / "yamnet.onnx"
        labels_path = model_dir / "yamnet_class_map.csv"
        if not model_path.exists():
            raise FileNotFoundError(
                f"missing {model_path}; download YAMNet ONNX model into {model_dir}"
            )
        self._session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self._labels = self._load_labels(labels_path)
        self._window = int(self._SAMPLE_RATE * self._WINDOW_SECONDS)
        self._hop = self._window // 2

    @staticmethod
    def _load_labels(path: Path) -> list[str]:
        if path.exists():
            with path.open(newline="") as fh:
                rows = list(csv.DictReader(fh))
            return [r.get("display_name", "") for r in rows]
        alt = path.with_suffix(".txt")
        if alt.exists():
            return [line.strip() for line in alt.read_text().splitlines() if line.strip()]
        raise FileNotFoundError(f"no label map next to model ({path})")

    def classify(self, buffer: audio.AudioBuffer, top_n: int = 5) -> list[Label]:
        np = self._np
        samples = np.asarray(buffer.samples, dtype="float32")
        if samples.size < self._window:
            samples = np.pad(samples, (0, self._window - samples.size))

        input_name = self._session.get_inputs()[0].name
        aggregated = np.zeros(len(self._labels), dtype="float32")
        count = 0
        for start in range(0, samples.size - 1, self._hop):
            chunk = samples[start : start + self._window]
            if chunk.size < self._window:
                break
            scores = self._session.run(None, {input_name: chunk[None, :].astype("float32")})[0]
            aggregated += np.asarray(scores).reshape(-1)[: len(self._labels)]
            count += 1
        if count == 0:
            return [Label("Ambient hum", 0.5)]
        aggregated /= count

        order = np.argsort(aggregated)[::-1][:top_n]
        labels = [
            Label(self._labels[i], round(float(aggregated[i]), 3))
            for i in order
            if aggregated[i] > 1e-4
        ]
        return labels or [Label("Ambient hum", 0.5)]