from datetime import date

from agent.worker import (
    analyze_extracted_text,
    combined_confidence,
    evaluate_material,
    extract_text,
    generate_summary,
    pending_unevaluated,
    relevance_label,
    tavily_score,
)
from events import AI_EVALUATION_COMPLETED
from extensions import db
from models import STATUS_APPROVED, STATUS_PENDING, Course, Event, Material


def add_course(name="פיזיקה"):
    course = Course(name=name)
    db.session.add(course)
    db.session.commit()
    return course


def add_material(course, file_name, **overrides):
    values = {
        "academic_year": 2024,
        "material_type": "summaries",
        "file_type": "summary",
        "uploaded_at": date(2024, 1, 1),
        "status": STATUS_PENDING,
        "file_path": "stored.pdf",
        "icon_type": "pdf",
    }
    values.update(overrides)
    material = Material(file_name=file_name, course_id=course.id, **values)
    db.session.add(material)
    db.session.commit()
    return material


def test_relevance_label_flags_low_confidence_as_not_academic():
    assert "לא רלוונטי" in relevance_label(21, "reject")
    assert "רלוונטי" in relevance_label(80, "approve")


def test_generate_summary_tries_a_fallback_model(monkeypatch):
    class _Models:
        def __init__(self):
            self.calls = []

        def generate_content(self, model, contents):
            self.calls.append(model)
            if model == "gemini-3.5-flash":
                raise RuntimeError("503")
            return type("R", (), {"text": "סיכום מהמודל החלופי"})()

    class _Client:
        def __init__(self, api_key):
            self.models = _Models()
            _Client.last = self

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("agent.worker.Client", _Client)

    summary = generate_summary("חוק ניוטון", "notes.pdf")

    assert summary == "סיכום מהמודל החלופי"
    assert _Client.last.models.calls[0] == "gemini-3.5-flash"


def test_pending_unevaluated_selects_pending_without_a_summary(app_context):
    course = add_course()
    waiting = add_material(course, "wait.pdf")
    add_material(course, "done.pdf", ai_summary="כבר סוכם")
    add_material(course, "ok.pdf", status=STATUS_APPROVED)

    rows = pending_unevaluated()

    assert [item.file_name for item in rows] == ["wait.pdf"]
    assert rows[0].id == waiting.id


def test_extract_text_skips_a_remote_link(app_context, tmp_path):
    course = add_course()
    material = add_material(
        course,
        "video",
        file_path="https://youtu.be/abc",
    )

    text = extract_text(material, str(tmp_path))

    assert text == ""


def test_tavily_score_is_higher_when_hits_exist():
    assert tavily_score({"ok": True, "mode": "tavily", "results": [{"title": "a"}]}) == 80
    assert tavily_score({"ok": True, "mode": "stub", "results": []}) == 35
    assert tavily_score({"ok": False, "mode": "error", "results": []}) == 20


def test_combined_confidence_averages_the_three_signals():
    score = combined_confidence(0, {"ok": True, "mode": "tavily", "results": [{"t": "1"}]}, 70)

    assert score == 83


def test_analyze_extracted_text_returns_readonly_ai_fields(monkeypatch):
    monkeypatch.setattr("agent.worker.query_similar", lambda query, top_k=5: [])
    monkeypatch.setattr(
        "agent.worker.tavily_search",
        lambda query: {"ok": True, "mode": "stub", "results": []},
    )
    monkeypatch.setattr("agent.worker.classify_source", lambda text: {"confidence": 70})
    monkeypatch.setattr("agent.worker.generate_summary", lambda text, fallback: "סיכום קדם-שליחה")

    analysis = analyze_extracted_text("חוק ניוטון", "notes.pdf")

    assert analysis["ai_summary"] == "סיכום קדם-שליחה"
    assert analysis["ai_confidence"] == 35
    assert analysis["ai_recommendation"] == "reject"
    assert "לא רלוונטי" in analysis["relevance"]


def test_evaluate_material_embeds_extracted_text(app_context, monkeypatch, tmp_path):
    queries = []
    course = add_course()
    material = add_material(course, "notes.pdf")
    monkeypatch.setattr("agent.worker.extract_text", lambda *args: "חוק ניוטון")
    monkeypatch.setattr(
        "agent.worker.query_similar",
        lambda query, top_k=5: queries.append(query) or [],
    )
    monkeypatch.setattr(
        "agent.worker.tavily_search",
        lambda query: {"ok": True, "mode": "stub", "results": []},
    )
    monkeypatch.setattr("agent.worker.classify_source", lambda text: {"confidence": 70})
    monkeypatch.setattr("agent.worker.generate_summary", lambda text, fallback: "סיכום")

    evaluate_material(material, str(tmp_path))

    assert queries == ["חוק ניוטון"]


def test_evaluate_material_writes_ai_fields_and_an_event(app_context, monkeypatch, tmp_path):
    course = add_course()
    material = add_material(course, "notes.pdf")
    monkeypatch.setattr("agent.worker.extract_text", lambda *args: "חוק ניוטון")
    monkeypatch.setattr(
        "agent.worker.query_similar",
        lambda query, top_k=5: [{"material_id": 1, "distance": 0.0}],
    )
    monkeypatch.setattr(
        "agent.worker.tavily_search",
        lambda query: {"ok": True, "mode": "tavily", "results": [{"title": "syllabus"}]},
    )
    monkeypatch.setattr(
        "agent.worker.classify_source",
        lambda text: {"confidence": 90},
    )
    monkeypatch.setattr("agent.worker.generate_summary", lambda text, fallback: "סיכום AI")

    evaluated = evaluate_material(material, str(tmp_path))

    assert evaluated.status == STATUS_PENDING
    assert evaluated.ai_summary == "סיכום AI"
    assert evaluated.confidence == 90
    assert evaluated.ai_recommendation == "approve"
    event = Event.query.filter_by(event_type=AI_EVALUATION_COMPLETED).one()
    assert event.entity_id == material.id


def test_evaluate_material_still_writes_when_tavily_fails(app_context, monkeypatch, tmp_path):
    course = add_course()
    material = add_material(course, "notes.pdf")
    monkeypatch.setattr("agent.worker.extract_text", lambda *args: "חוק ניוטון")
    monkeypatch.setattr("agent.worker.query_similar", lambda query, top_k=5: [])
    monkeypatch.setattr(
        "agent.worker.tavily_search",
        lambda query: {"ok": False, "mode": "error", "results": []},
    )
    monkeypatch.setattr("agent.worker.classify_source", lambda text: {"confidence": 90})
    monkeypatch.setattr("agent.worker.generate_summary", lambda text, fallback: "סיכום")

    evaluated = evaluate_material(material, str(tmp_path))

    assert evaluated.ai_summary == "סיכום"
    assert evaluated.status == STATUS_PENDING
    assert evaluated.confidence == 36
    assert evaluated.ai_recommendation == "reject"
