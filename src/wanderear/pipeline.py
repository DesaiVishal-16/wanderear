"""The shared pipeline: audio -> labels -> narration -> stored postcard.

Used by both the CLI and the optional local web app so there is exactly one
implementation of "turn a soundscape into a postcard".
"""

from __future__ import annotations

from collections.abc import Callable

from . import audio, embeddings
from .postcard import build_context, build_postcard
from .store import LocalStore

WarnFn = Callable[[str], None]


def classifier_for(name: str, warn: WarnFn | None = None):
    from .classify import get_classifier

    try:
        return get_classifier(name)
    except Exception as exc:
        if warn:
            warn(f"classifier '{name}' unavailable ({exc}); using passthrough")
        return get_classifier("passthrough")


def narrator_for(name: str, warn: WarnFn | None = None):
    from .narrate import TemplateNarrator, get_narrator

    try:
        return get_narrator(name)
    except Exception as exc:
        if warn:
            warn(f"narrator '{name}' unavailable ({exc}); using template")
        return TemplateNarrator()


def analyze(
    buffer: audio.AudioBuffer,
    *,
    classifier: str = "auto",
    narrator: str = "auto",
    top_n: int = 5,
    location: dict | None = None,
    store: LocalStore | None = None,
    spectrogram: bool = True,
    warn: WarnFn | None = None,
):
    """Run the full pipeline and (by default) save the postcard locally."""
    from .observability import span

    with span("classify", classifier=classifier):
        clf = classifier_for(classifier, warn=warn)
        labels = clf.classify(buffer, top_n=top_n)

    with span("narrate", narrator=narrator):
        nar = narrator_for(narrator, warn=warn)
        context = build_context(location=location)
        narration = nar.narrate(labels, context)

    vector = embeddings.embed(buffer, labels)
    card = build_postcard(
        labels, narration, buffer.duration, clf.name, context, embedding=vector
    )

    if store is not None:
        store.ensure()
        wav = store.media / f"{card.id}.wav"
        audio.save_wav(buffer, str(wav))
        card.audio_path = str(wav)
        if spectrogram:
            png = audio.spectrogram_png(buffer, str(store.media / f"{card.id}.png"))
            if png:
                card.spectrogram_path = png
        store.save(card)

    return card