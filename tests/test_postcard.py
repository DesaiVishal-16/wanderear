from datetime import datetime, timezone

from wanderear.classify import Label
from wanderear.narrate import TemplateNarrator
from wanderear.postcard import build_context, build_postcard, season_for, time_of_day


def test_season_mapping():
    assert season_for(1) == "winter"
    assert season_for(4) == "spring"
    assert season_for(8) == "summer"
    assert season_for(10) == "autumn"


def test_time_of_day():
    dt = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)
    assert time_of_day(dt) == "morning"
    assert time_of_day(dt.replace(hour=23)) == "night"


def test_build_context_is_offline():
    ctx = build_context()
    assert "season" in ctx and "local_time" in ctx


def test_template_narrator_and_postcard():
    labels = [Label("Stream", 0.7), Label("Birdsong", 0.3)]
    ctx = build_context()
    narration = TemplateNarrator().narrate(labels, ctx)
    assert narration.title and narration.body
    card = build_postcard(labels, narration, 8.0, "passthrough", ctx)
    data = card.to_dict()
    assert data["labels"][0]["name"] == "Stream"
    assert data["postcard"]["narrator"] == "template"
    assert data["duration_s"] == 8.0


def test_get_narrator_auto_falls_back_without_server(monkeypatch):
    from wanderear import narrate

    monkeypatch.setattr(narrate.GemmaNarrator, "installed_models", lambda self: [])
    monkeypatch.setattr(narrate.GemmaNarrator, "available", lambda self: False)
    narrator = narrate.get_narrator("auto")
    assert narrator.name == "template"
    out = narrator.narrate([Label("Wind", 0.5)], build_context())
    assert out.body