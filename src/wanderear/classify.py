"""Pluggable, multi-label soundscape classifiers.

A soundscape is a *mix*, so every classifier returns the top-N labels with
confidences rather than a single class. Real backends (YAMNet, PANNs, CLAP) live
behind lazy imports; ``PassthroughClassifier`` is a dependency-free fallback so
the pipeline never hard-fails.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol

from . import audio


class Label(NamedTuple):
    name: str
    confidence: float


class Classifier(Protocol):
    name: str

    def classify(self, buffer: audio.AudioBuffer, top_n: int = 5) -> list[Label]:
        ...


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize(scores: dict[str, float], top_n: int) -> list[Label]:
    positive = {k: _clamp(v) for k, v in scores.items()}
    total = sum(positive.values())
    if total <= 1e-9:
        return [Label("Ambient hum", 0.5)]
    ranked = sorted(positive.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [Label(name, round(value / total, 3)) for name, value in ranked]


class PassthroughClassifier:
    """Dependency-light heuristic classifier.

    Not accurate — but it never fails, needs no model download, and keeps CI and
    offline demos working. Prefer the real backends when installed.
    """

    name = "passthrough"

    def classify(self, buffer: audio.AudioBuffer, top_n: int = 5) -> list[Label]:
        peak = audio.peak_frequency(buffer)
        centroid = audio.spectral_centroid(buffer)
        flatness = audio.spectral_flatness(buffer)
        zcr = audio.zero_crossing_rate(buffer)
        energy = audio.rms(buffer)

        if energy < 1e-4:
            return [Label("Silence", 1.0)]

        scores: dict[str, float] = {}
        scores["Wind"] = _clamp(0.4 * flatness + 0.6 * (1.0 - min(1.0, centroid / 3000.0)))
        scores["Rain"] = _clamp(flatness * 0.8 + zcr * 0.3)
        scores["Leaves"] = _clamp(zcr * 0.6 + flatness * 0.3)
        scores["Stream"] = _clamp(flatness + 0.3 - abs(centroid - 800.0) / 2500.0)
        if 1500.0 <= peak <= 6000.0:
            scores["Birdsong"] = _clamp(0.85 * (1.0 - flatness))
        if peak > 4000.0:
            scores["Insects"] = _clamp(0.6 * (1.0 - flatness * 0.5))
        if 150.0 <= peak <= 2000.0:
            scores["Frogs"] = _clamp(0.4 * (1.0 - flatness))
        return _normalize(scores, top_n)


_REGISTRY: dict[str, type] = {"passthrough": PassthroughClassifier}


def register(cls: type) -> type:
    _REGISTRY[cls.name] = cls
    return cls


def list_classifiers() -> list[str]:
    return sorted(set(_REGISTRY) | set(_LAZY))


_LAZY = {
    "yamnet": (".classifiers.yamnet", "YamNetClassifier"),
    "panns": (".classifiers.panns", "PannsClassifier"),
    "clap": (".classifiers.clap", "ClapClassifier"),
}


def _load(name: str) -> Classifier:
    import importlib

    module_path, class_name = _LAZY[name]
    module = importlib.import_module(module_path, package=__package__)
    return getattr(module, class_name)()


def get_classifier(name: str = "auto") -> Classifier:
    """Return a classifier. ``auto`` prefers a real model, falls back gracefully."""
    if name == "passthrough":
        return PassthroughClassifier()
    if name == "auto":
        for candidate in ("yamnet", "panns", "clap"):
            try:
                return _load(candidate)
            except Exception:
                continue
        return PassthroughClassifier()
    if name in _REGISTRY:
        return _REGISTRY[name]()
    if name in _LAZY:
        return _load(name)
    raise ValueError(f"unknown classifier: {name!r} (have: {list_classifiers()})")