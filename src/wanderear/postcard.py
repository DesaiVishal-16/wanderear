"""The postcard: the artifact you keep from a moment outdoors."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .classify import Label
from .narrate import Narration


@dataclass
class Postcard:
    id: str
    created_at: str
    duration_s: float
    context: dict
    labels: list[dict]
    postcard: dict
    embedding: list[float] | None = None
    audio_path: str | None = None
    spectrogram_path: str | None = None
    classifier: str = "unknown"
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def season_for(month: int, lat: float | None = None) -> str:
    northern = lat is None or lat >= 0
    seasons = ["winter", "winter", "spring", "spring", "spring", "summer",
               "summer", "summer", "autumn", "autumn", "autumn", "winter"]
    name = seasons[month - 1]
    if not northern:
        name = {"winter": "summer", "summer": "winter",
                "spring": "autumn", "autumn": "spring"}[name]
    return name


def time_of_day(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 15:
        return "midday"
    if 15 <= h < 19:
        return "afternoon"
    if 19 <= h < 22:
        return "evening"
    return "night"


def build_context(location: dict | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc).astimezone()
    return {
        "season": season_for(now.month, (location or {}).get("lat")),
        "local_time": time_of_day(now),
        "iso_time": now.isoformat(),
        "location": location or {},
    }


def build_postcard(
    labels: list[Label],
    narration: Narration,
    duration_s: float,
    classifier: str,
    context: dict | None = None,
    now: datetime | None = None,
    embedding: list[float] | None = None,
) -> Postcard:
    now = now or datetime.now(timezone.utc)
    context = context or build_context(now=now)
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    return Postcard(
        id=f"{stamp}_{uuid.uuid4().hex[:6]}",
        created_at=now.isoformat(),
        duration_s=round(duration_s, 2),
        context=context,
        labels=[{"name": lab.name, "confidence": lab.confidence} for lab in labels],
        postcard={"title": narration.title, "body": narration.body,
                  "narrator": narration.narrator},
        classifier=classifier,
        embedding=embedding,
    )