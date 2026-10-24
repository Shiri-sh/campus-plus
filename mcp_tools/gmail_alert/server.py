"""Stdio JSON-RPC MCP server for the gmail_alert tool (MCP Studio)."""

import json
import sys

from mcp_tools.gmail_alert.tool import INPUT_SCHEMA, OUTPUT_SCHEMA, TOOL_NAME, call_tool

PROTOCOL_VERSION = "2024-11-05"


def _write(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id, result):
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id, code, message):
    _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def handle(payload):
    method = payload.get("method")
    request_id = payload.get("id")
    params = payload.get("params") or {}

    if method == "initialize":
        _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": TOOL_NAME, "version": "1.0.0"},
            },
        )
        return
    if method == "notifications/initialized":
        return
    if method == "tools/list":
        _result(
            request_id,
            {
                "tools": [
                    {
                        "name": TOOL_NAME,
                        "description": "Send an email via Gmail SMTP (recipient, subject, body).",
                        "inputSchema": INPUT_SCHEMA,
                        "outputSchema": OUTPUT_SCHEMA,
                    }
                ]
            },
        )
        return
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name != TOOL_NAME:
            _error(request_id, -32601, f"Unknown tool: {name}")
            return
        result = call_tool(
            arguments.get("recipient"),
            arguments.get("subject"),
            arguments.get("body"),
        )
        _result(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result,
                "isError": not result.get("ok"),
            },
        )
        return
    if request_id is not None:
        _error(request_id, -32601, f"Unknown method: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except Exception as error:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(error)}})


if __name__ == "__main__":
    main()
