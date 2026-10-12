from wanderear import embeddings
from wanderear.classify import Label
from wanderear.narrate import Narration
from wanderear.postcard import build_context, build_postcard
from wanderear.store import LocalStore


def _card(store, title, labels, embedding):
    narration = Narration(title, "body", "template")
    card = build_postcard(labels, narration, 5.0, "test", build_context(), embedding=embedding)
    store.save(card)
    return card


def test_search_ranks_closest_first(tmp_path):
    store = LocalStore(home=tmp_path)
    a = _card(store, "stream", [Label("Stream", 0.9)], [1.0, 0.0, 0.0])
    _card(store, "insects", [Label("Insects", 0.9)], [0.0, 1.0, 0.0])

    results = store.search([0.95, 0.05, 0.0], limit=2)
    assert results[0][0]["id"] == a.id
    assert results[0][1] > results[1][1]


def test_search_handles_missing_embedding(tmp_path):
    store = LocalStore(home=tmp_path)
    narration = Narration("old", "body", "template")
    card = build_postcard([Label("Wind", 0.7)], narration, 3.0, "test", build_context())
    store.save(card)
    results = store.search(embeddings.label_vector([Label("Wind", 0.9)]))
    assert results and results[0][0]["id"] == card.id