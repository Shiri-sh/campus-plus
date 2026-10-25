import json

import pytest

from mcp_tools.gmail_alert.tool import call_tool, parse_credentials


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ('{"user": "a@b.c", "password": "secret"}', ("a@b.c", "secret")),
        ('{"email": "a@b.c", "app_password": "secret"}', ("a@b.c", "secret")),
        ('{"user": "a@b.c"}', None),
        ('{"user": "", "password": "secret"}', None),
        ("me@jct.ac.il:app-pass", ("me@jct.ac.il", "app-pass")),
        ("  me@jct.ac.il : secret ", ("me@jct.ac.il", "secret")),
        ("me@jct.ac.il:pass:extra", ("me@jct.ac.il", "pass:extra")),
        ("me@jct.ac.il:", None),
        ("nocolon", None),
    ],
)
def test_parse_credentials_accepts_json_or_user_colon_password(raw, expected):
    parsed = parse_credentials(raw)

    assert parsed == expected


def test_parse_credentials_rejects_broken_json():
    with pytest.raises(json.JSONDecodeError):
        parse_credentials("{not-json")


def test_call_tool_rejects_a_blank_recipient(monkeypatch):
    monkeypatch.delenv("GMAIL_MCP_CREDENTIALS", raising=False)

    result = call_tool("   ", "נושא", "גוף")

    assert result == {
        "ok": False,
        "confirmation": "recipient is required",
        "mode": "error",
    }


def test_call_tool_stubs_when_credentials_are_missing(monkeypatch):
    monkeypatch.delenv("GMAIL_MCP_CREDENTIALS", raising=False)

    result = call_tool("student@jct.ac.il", "נושא", "גוף")

    assert result == {
        "ok": True,
        "confirmation": "stub-logged:student@jct.ac.il",
        "mode": "stub",
    }


def test_call_tool_rejects_invalid_credentials_json(monkeypatch):
    monkeypatch.setenv("GMAIL_MCP_CREDENTIALS", "{not-json")

    result = call_tool("admin@jct.ac.il", "נושא", "גוף")

    assert result == {
        "ok": False,
        "confirmation": "invalid credentials JSON",
        "mode": "error",
    }


def test_call_tool_sends_through_smtp_when_credentials_exist(monkeypatch):
    delivered = []

    class RecordingSMTP:
        def __init__(self, host, port, timeout):
            delivered.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def login(self, user, password):
            delivered.append(("login", user, password))

        def send_message(self, message):
            delivered.append(("send", message["To"], message["Subject"]))

    monkeypatch.setenv("GMAIL_MCP_CREDENTIALS", "me@jct.ac.il:app-pass")
    monkeypatch.setenv("GMAIL_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("GMAIL_SMTP_PORT", "2525")
    monkeypatch.setattr("mcp_tools.gmail_alert.tool.smtplib.SMTP", RecordingSMTP)

    result = call_tool("admin@jct.ac.il", "נושא", "גוף")

    assert result == {
        "ok": True,
        "confirmation": "sent:admin@jct.ac.il",
        "mode": "smtp",
    }
    assert delivered == [
        ("connect", "smtp.test", 2525, 15),
        ("login", "me@jct.ac.il", "app-pass"),
        ("send", "admin@jct.ac.il", "נושא"),
    ]


def test_call_tool_reports_an_smtp_failure(monkeypatch):
    class FailingSMTP:
        def __init__(self, host, port, timeout):
            raise OSError("connection refused")

    monkeypatch.setenv("GMAIL_MCP_CREDENTIALS", "me@jct.ac.il:app-pass")
    monkeypatch.setattr("mcp_tools.gmail_alert.tool.smtplib.SMTP", FailingSMTP)

    result = call_tool("admin@jct.ac.il", "נושא", "גוף")

    assert result == {
        "ok": False,
        "confirmation": "connection refused",
        "mode": "error",
    }
