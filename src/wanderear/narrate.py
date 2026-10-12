"""Narrators turn a label set + offline context into postcard prose.

``GemmaNarrator`` uses a locally-served open-weight model (Ollama). The
``TemplateNarrator`` is deterministic and always available.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .classify import Label
from .config import settings

FIELD_GUIDE = Path(__file__).resolve().parents[2] / "data" / "field_guide" / "nature_glossary.json"


@dataclass
class Narration:
    title: str
    body: str
    narrator: str


class Narrator(Protocol):
    name: str

    def narrate(self, labels: list[Label], context: dict) -> Narration:
        ...


def _load_guide() -> dict:
    try:
        return json.loads(FIELD_GUIDE.read_text())
    except Exception:
        return {}


def _phrase(labels: list[Label], guide: dict) -> str:
    parts = []
    for label in labels:
        if label.confidence < settings.min_confidence:
            continue
        blurb = guide.get(label.name, {}).get("blurb", label.name.lower())
        parts.append(blurb)
    return ", ".join(parts[:4]) if parts else "a quiet, hard-to-place ambience"


def _when(context: dict) -> str:
    time = context.get("local_time") or "daylight"
    season = context.get("season")
    return f"{time} in {season}" if season else time


class TemplateNarrator:
    name = "template"

    def narrate(self, labels: list[Label], context: dict) -> Narration:
        guide = _load_guide()
        top = labels[0].name if labels else "ambience"
        place = context.get("location", {}).get("label")
        where = f" near {place}" if place else ""
        title = f"{_when(context).title()}: {top}"
        body = (
            f"A {_when(context)} soundscape{where}. "
            f"You are hearing {_phrase(labels, guide)}. "
            f"Strongest presence: {top}."
        )
        return Narration(title=title, body=body, narrator=self.name)


class GemmaNarrator:
    name = "gemma"

    def __init__(self, model: str | None = None, url: str | None = None) -> None:
        self.model = model or settings.ollama_model
        self.url = (url or settings.ollama_url).rstrip("/")

    def installed_models(self) -> list[str]:
        """Names of models the local Ollama server has pulled ([] if unreachable)."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2) as resp:
                tags = json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []
        return [m.get("name", "") for m in tags.get("models", []) if m.get("name")]

    def available(self) -> bool:
        """True only if the server is up *and* the configured model is pulled."""
        names = self.installed_models()
        base = self.model.split(":")[0]
        return any(n == self.model or n.split(":")[0] == base for n in names)

    def use_installed_gemma(self) -> bool:
        """Point at any installed Gemma model if the configured one is absent.

        Lets the app 'just work' with whatever open Gemma the user has pulled
        (e.g. gemma3n:e2b) instead of requiring an exact tag.
        """
        if self.available():
            return True
        for name in self.installed_models():
            if "gemma" in name.lower():
                self.model = name
                return True
        return False

    def narrate(self, labels: list[Label], context: dict) -> Narration:
        label_text = ", ".join(f"{lab.name} ({lab.confidence:.2f})" for lab in labels)
        prompt = (
            "You are a naturalist writing a tiny 'sound postcard' about a moment "
            "recorded outdoors. Use ONLY the detected sounds listed below; never "
            "invent species or sounds that are not given. Write 2-3 warm sentences "
            "in present tense. Then a short 3-6 word title on its own line prefixed "
            "with 'TITLE:'.\n\n"
            f"Detected sounds: {label_text}\n"
            f"Time: {context.get('local_time', 'unknown')}\n"
            f"Season: {context.get('season', 'unknown')}\n"
            f"Place: {context.get('location', {}).get('label') or 'unspecified'}\n"
        )
        payload = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False}
        ).encode()
        req = urllib.request.Request(
            f"{self.url}/api/generate", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = json.loads(resp.read()).get("response", "").strip()

        title, body = self._split(text, labels)
        return Narration(title=title, body=body, narrator=self.model)

    @staticmethod
    def _split(text: str, labels: list[Label]) -> tuple[str, str]:
        title = ""
        body_lines = []
        for line in text.splitlines():
            if line.strip().upper().startswith("TITLE:"):
                title = line.split(":", 1)[1].strip()
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip() or text.strip()
        if not title:
            title = f"{labels[0].name} at rest" if labels else "A moment outside"
        return title, body


def get_narrator(name: str = "auto") -> Narrator:
    if name == "template":
        return TemplateNarrator()
    if name in ("gemma", "auto"):
        narrator = GemmaNarrator()
        if narrator.use_installed_gemma():
            return narrator
        if name == "gemma":
            raise RuntimeError(
                "no Gemma model found in the local Ollama server; "
                "try: ollama pull gemma3:4b (or gemma3n:e2b)"
            )
    return TemplateNarrator()