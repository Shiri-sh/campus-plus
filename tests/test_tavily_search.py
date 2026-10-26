from mcp_tools.tavily_search.tool import call_tool


class _FakeClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.queries = []
        self.payload = {
            "results": [
                {
                    "title": "Syllabus",
                    "url": "https://example.com/s",
                    "content": "physics exam",
                }
            ]
        }
        self.error = None

    def search(self, query, max_results=5):
        self.queries.append((query, max_results))
        if self.error:
            raise self.error
        return self.payload


def test_call_tool_rejects_a_blank_query(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = call_tool("   ")

    assert result == {
        "ok": False,
        "confirmation": "query is required",
        "mode": "error",
        "results": [],
    }


def test_call_tool_stubs_when_the_api_key_is_missing(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = call_tool("פיזיקה מבחן")

    assert result == {
        "ok": True,
        "confirmation": "stub-logged:פיזיקה מבחן",
        "mode": "stub",
        "results": [],
    }


def test_call_tool_returns_normalized_hits(monkeypatch):
    client = _FakeClient("key")
    monkeypatch.setenv("TAVILY_API_KEY", "key")
    monkeypatch.setattr("mcp_tools.tavily_search.tool.TavilyClient", lambda api_key: client)

    result = call_tool("פיזיקה מבחן")

    assert result["ok"] is True
    assert result["mode"] == "tavily"
    assert result["results"] == [
        {"title": "Syllabus", "url": "https://example.com/s", "snippet": "physics exam"}
    ]
    assert client.queries == [("פיזיקה מבחן", 5)]


def test_call_tool_returns_error_mode_when_tavily_raises(monkeypatch):
    client = _FakeClient("key")
    client.error = RuntimeError("timeout")
    monkeypatch.setenv("TAVILY_API_KEY", "key")
    monkeypatch.setattr("mcp_tools.tavily_search.tool.TavilyClient", lambda api_key: client)

    result = call_tool("פיזיקה")

    assert result == {
        "ok": False,
        "confirmation": "timeout",
        "mode": "error",
        "results": [],
    }


def test_call_tool_ignores_a_malformed_payload(monkeypatch):
    client = _FakeClient("key")
    client.payload = "not-a-dict"
    monkeypatch.setenv("TAVILY_API_KEY", "key")
    monkeypatch.setattr("mcp_tools.tavily_search.tool.TavilyClient", lambda api_key: client)

    result = call_tool("פיזיקה")

    assert result["ok"] is True
    assert result["results"] == []
    assert result["confirmation"] == "hits:0"
