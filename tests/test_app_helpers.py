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


def test_stored_upload_name_keeps_a_lowercased_suffix(monkeypatch):
    monkeypatch.setattr(campus_app.uuid, "uuid4", lambda: SimpleNamespace(hex="abc123"))

    stored = campus_app.stored_upload_name("סיכום.PDF")

    assert stored == "abc123.pdf"


def test_stored_upload_name_allows_a_missing_suffix(monkeypatch):
    monkeypatch.setattr(campus_app.uuid, "uuid4", lambda: SimpleNamespace(hex="abc123"))

    stored = campus_app.stored_upload_name("README")

    assert stored == "abc123"
