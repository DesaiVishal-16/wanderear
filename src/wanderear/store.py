"""Local store: JSON-lines index + media folder on disk.

The local store is the source of truth. Cloud sync (MongoDB Atlas) is optional
and idempotent — see ``sync.py`` (not implemented in the MVP).
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import _data_home
from .postcard import Postcard


class LocalStore:
    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home else _data_home()
        self.media = self.home / "media"
        self.index = self.home / "index.jsonl"

    def ensure(self) -> None:
        self.media.mkdir(parents=True, exist_ok=True)

    def save(self, postcard: Postcard, media_paths: list[Path] | None = None) -> Postcard:
        self.ensure()
        if media_paths:
            for path in media_paths:
                if path and path.exists():
                    target = self.media / path.name
                    if path.resolve() != target.resolve():
                        target.write_bytes(path.read_bytes())
                    if path.suffix == ".wav":
                        postcard.audio_path = str(target)
                    elif path.suffix == ".png":
                        postcard.spectrogram_path = str(target)
        with self.index.open("a") as fh:
            fh.write(json.dumps(postcard.to_dict()) + "\n")
        return postcard

    def all(self) -> list[dict]:
        if not self.index.exists():
            return []
        items = []
        for line in self.index.read_text().splitlines():
            if line.strip():
                items.append(json.loads(line))
        return items

    def get(self, postcard_id: str) -> dict | None:
        for item in self.all():
            if item["id"] == postcard_id:
                return item
        return None

    def search(self, query: list[float], limit: int = 5) -> list[tuple[dict, float]]:
        """Rank saved postcards by cosine similarity to `query` (offline).

        Postcards saved before embeddings existed fall back to a label-only
        comparison so old data still shows up.
        """
        from .embeddings import cosine, label_similarity

        scored: list[tuple[dict, float]] = []
        for item in self.all():
            vector = item.get("embedding")
            if vector:
                score = cosine(query, vector)
            else:
                from .classify import Label

                labels = [Label(lab["name"], lab["confidence"]) for lab in item.get("labels", [])]
                score = label_similarity(query, labels)
            scored.append((item, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]