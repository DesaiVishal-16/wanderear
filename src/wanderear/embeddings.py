"""Offline soundscape embeddings + similarity.

No cloud, no extra model: we combine a peak-normalized acoustic fingerprint
(log band energies) with a weighted label vector over a fixed vocabulary. Good
enough for "find me a sound like this one" and for pushing to Atlas Vector
Search later.
"""

from __future__ import annotations

import math

from . import audio
from .classify import Label

LABEL_VOCAB: tuple[str, ...] = (
    "Wind",
    "Rain",
    "Leaves",
    "Stream",
    "Birdsong",
    "Insects",
    "Frogs",
    "Cricket",
    "Wind in trees",
    "Silence",
    "Ambient hum",
)
_BANDS = 16


def label_vector(labels: list[Label]) -> list[float]:
    vec = [0.0] * len(LABEL_VOCAB)
    index = {name: i for i, name in enumerate(LABEL_VOCAB)}
    for label in labels:
        if label.name in index:
            vec[index[label.name]] += label.confidence
        else:
            # Hash unknown labels into a stable slot so nothing is lost.
            slot = hash(label.name) % len(LABEL_VOCAB)
            vec[slot] += label.confidence
    return vec


def embed(buffer: audio.AudioBuffer, labels: list[Label]) -> list[float]:
    """Return an L2-normalized embedding combining acoustics and labels."""
    acoustic = audio.band_energies(buffer, bands=_BANDS)
    vector = [v / 40.0 for v in acoustic] + label_vector(labels)
    return _l2_normalize(vector)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(y * y for y in b[:n]))
    if na == 0 or nb == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


LABEL_DIM = len(LABEL_VOCAB)


def label_similarity(query: list[float], labels: list[Label]) -> float:
    """Compare a query embedding (or label vector) against labels only.

    Used for postcards saved before embeddings existed, so legacy data still
    ranks sensibly instead of producing misleading scores.
    """
    stored = label_vector(labels)
    query_labels = query[-LABEL_DIM:] if len(query) >= LABEL_DIM else query
    return cosine(query_labels, stored)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


def embed_fields(buffer: audio.AudioBuffer, labels: list[Label]) -> list[float]:
    """Convenience wrapper used by the pipeline."""
    return embed(buffer, labels)