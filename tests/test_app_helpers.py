from types import SimpleNamespace

import pytest

import app as campus_app


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  A@B.C  ", "a@b.c"),
    ],
)
def test_normalize_email_strips_and_lowercases(value, expected):
    email = campus_app.normalize_email(value)

    assert email == expected


def test_debug_enabled_defaults_to_true_when_unset(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)

    enabled = campus_app.debug_enabled()

    assert enabled is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        (" YES ", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("maybe", False),
    ],
)
def test_debug_enabled_accepts_common_true_strings(monkeypatch, raw, expected):
    monkeypatch.setenv("FLASK_DEBUG", raw)

    enabled = campus_app.debug_enabled()

    assert enabled is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com/watch", True),
        ("http://example.com", True),
        ("ftp://example.com", False),
        ("http:///missing-host", False),
        ("notaurl", False),
        ("", False),
        (None, False),
    ],
)
def test_is_video_link_requires_http_and_a_host(value, expected):
    is_link = campus_app.is_video_link(value)

    assert is_link is expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("סיכום 2_1.pdf", "סיכום 2_1.pdf"),
        ("notes.pdf", "notes.pdf"),
        ("folder/סיכום.pdf", "סיכום.pdf"),
        ("..\\..\\סיכום.pdf", "סיכום.pdf"),
        ("  סיכום.pdf  ", "סיכום.pdf"),
        ("a\x00b.pdf", "ab.pdf"),
        ("", ""),
        (None, ""),
        ("...", ""),
        ("ח" * 300 + ".pdf", ("ח" * 300 + ".pdf")[:255]),
    ],
)
def test_display_upload_name_keeps_hebrew_and_drops_paths(filename, expected):
    assert campus_app.display_upload_name(filename) == expected


def test_stored_upload_name_keeps_a_lowercased_suffix(monkeypatch):
    monkeypatch.setattr(campus_app.uuid, "uuid4", lambda: SimpleNamespace(hex="abc123"))

    stored = campus_app.stored_upload_name("סיכום.PDF")

    assert stored == "abc123.pdf"


def _payload_material(**overrides):
    values = {
        "id": 1,
        "file_name": "notes.pdf",
        "course": SimpleNamespace(name="פיזיקה"),
        "lecturer": None,
        "academic_year": 2024,
        "material_type_label": "סיכומים",
        "ai_summary": None,
        "confidence": None,
        "is_link": False,
        "file_path": "",
        "status": "approved",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_material_payload_uses_a_clear_empty_summary():
    with campus_app.app.test_request_context():
        payload = campus_app.material_payload(_payload_material())

    assert payload["ai_summary"] == campus_app.EMPTY_AI_SUMMARY
    assert payload["confidence"] is None


def test_material_payload_includes_summary_and_confidence():
    with campus_app.app.test_request_context():
        payload = campus_app.material_payload(
            _payload_material(ai_summary="סיכום על ניוטון", confidence=82)
        )

    assert payload["ai_summary"] == "סיכום על ניוטון"
    assert payload["confidence"] == 82


def test_stored_upload_name_allows_a_missing_suffix(monkeypatch):
    monkeypatch.setattr(campus_app.uuid, "uuid4", lambda: SimpleNamespace(hex="abc123"))

    stored = campus_app.stored_upload_name("README")

    assert stored == "abc123"
