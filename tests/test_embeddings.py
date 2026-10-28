import pytest

from agent import embeddings


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, values):
        self.embeddings = [_FakeEmbedding(values)]


class _FakeModels:
    def __init__(self, values=None, error=None):
        self.values = values or [0.1, 0.2]
        self.error = error
        self.calls = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return _FakeEmbedResponse(self.values)


class _FakeClient:
    last = None

    def __init__(self, api_key):
        self.api_key = api_key
        self.models = _FakeClient.last_models
        _FakeClient.last = self


class _FakeCollection:
    def __init__(self, error=None, query_result=None):
        self.error = error
        self.query_result = query_result or {"ids": [[]], "distances": [[]], "documents": [[]]}
        self.upserts = []

    def upsert(self, **kwargs):
        if self.error:
            raise self.error
        self.upserts.append(kwargs)

    def query(self, **kwargs):
        if self.error:
            raise self.error
        self.last_query = kwargs
        return self.query_result


@pytest.fixture
def gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def test_embed_text_returns_none_without_an_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    vector = embeddings.embed_text("פיזיקה סיכום")

    assert vector is None


def test_embed_text_returns_none_for_blank_text(gemini_key):
    vector = embeddings.embed_text("   ")

    assert vector is None


def test_embed_text_returns_gemini_values(monkeypatch, gemini_key):
    models = _FakeModels(values=[0.4, 0.5, 0.6])
    _FakeClient.last_models = models
    monkeypatch.setattr(embeddings, "Client", _FakeClient)

    vector = embeddings.embed_text("מבחן אינפי")

    assert vector == [0.4, 0.5, 0.6]
    assert models.calls[0]["model"] == embeddings.EMBEDDING_MODEL
    assert _FakeClient.last.api_key == "test-key"


def test_embed_text_returns_none_when_gemini_raises(monkeypatch, gemini_key):
    _FakeClient.last_models = _FakeModels(error=RuntimeError("quota"))
    monkeypatch.setattr(embeddings, "Client", _FakeClient)

    vector = embeddings.embed_text("מבחן")

    assert vector is None


def test_upsert_material_skips_when_embedding_is_missing(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_text", lambda text: None)
    collection = _FakeCollection()
    monkeypatch.setattr(embeddings, "_collection", lambda: collection)

    stored = embeddings.upsert_material(12, "פיזיקה")

    assert stored is False
    assert collection.upserts == []


def test_upsert_material_writes_the_vector_once(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [0.1, 0.2])
    collection = _FakeCollection()
    monkeypatch.setattr(embeddings, "_collection", lambda: collection)

    first = embeddings.upsert_material(12, "פיזיקה סיכום")
    second = embeddings.upsert_material(12, "פיזיקה סיכום")

    assert first is True
    assert second is True
    assert collection.upserts[0]["ids"] == ["12"]
    assert collection.upserts[1]["ids"] == ["12"]


def test_upsert_material_returns_false_when_chroma_raises(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        embeddings,
        "_collection",
        lambda: _FakeCollection(error=RuntimeError("disk")),
    )

    stored = embeddings.upsert_material(12, "פיזיקה")

    assert stored is False


def test_query_similar_returns_empty_without_a_vector(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_text", lambda text: None)

    rows = embeddings.query_similar("מבחן")

    assert rows == []


def test_query_similar_maps_chroma_hits(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [0.1, 0.2])
    collection = _FakeCollection(
        query_result={
            "ids": [["15", "9"]],
            "distances": [[0.2, 0.8]],
            "documents": [["a", "b"]],
        }
    )
    monkeypatch.setattr(embeddings, "_collection", lambda: collection)

    rows = embeddings.query_similar("מבחן", top_k=2)

    assert rows == [
        {"material_id": 15, "distance": 0.2, "document": "a"},
        {"material_id": 9, "distance": 0.8, "document": "b"},
    ]
    assert collection.last_query["n_results"] == 2


def test_query_similar_returns_empty_when_chroma_raises(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        embeddings,
        "_collection",
        lambda: _FakeCollection(error=RuntimeError("missing")),
    )

    rows = embeddings.query_similar("מבחן")

    assert rows == []
