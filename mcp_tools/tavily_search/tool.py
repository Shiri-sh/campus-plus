import json
import logging
import os
from pathlib import Path

from tavily import TavilyClient

logger = logging.getLogger(__name__)

TOOL_NAME = "tavily_search"
INPUT_SCHEMA = json.loads((Path(__file__).with_name("tool.json")).read_text(encoding="utf-8"))[
    "inputSchema"
]
OUTPUT_SCHEMA = json.loads((Path(__file__).with_name("tool.json")).read_text(encoding="utf-8"))[
    "outputSchema"
]


def _normalize_results(raw):
    if not isinstance(raw, dict):
        return []
    rows = raw.get("results")
    if not isinstance(rows, list):
        return []
    results = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or item.get("snippet") or "",
            }
        )
    return results


def call_tool(query):
    """MCP tool entry: Tavily search or stub. Never raises to the caller."""
    text = (query or "").strip()
    if not text:
        return {
            "ok": False,
            "confirmation": "query is required",
            "mode": "error",
            "results": [],
        }

    api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not api_key:
        logger.info("tavily_search stub query=%s", text)
        return {
            "ok": True,
            "confirmation": f"stub-logged:{text}",
            "mode": "stub",
            "results": [],
        }

    try:
        payload = TavilyClient(api_key=api_key).search(text, max_results=5)
        results = _normalize_results(payload)
    except Exception as error:
        logger.warning("tavily_search failed: %s", error)
        return {
            "ok": False,
            "confirmation": str(error),
            "mode": "error",
            "results": [],
        }

    return {
        "ok": True,
        "confirmation": f"hits:{len(results)}",
        "mode": "tavily",
        "results": results,
    }
