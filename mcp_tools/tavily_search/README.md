# tavily_search — MCP Tool #1

Web search via Tavily. The AI worker (#21) will call this to check that a pending upload matches academic topics.

## Schemas

Import [`tool.json`](tool.json) into MCP Studio.

| Direction | Fields |
|---|---|
| Input | `query` (string) |
| Output | `ok` (boolean), `confirmation` (string), `mode` (`tavily` / `stub` / `error`), `results` (title, url, snippet) |

## MCP Studio

1. Create a tool named `tavily_search`.
2. Paste the input and output schemas from `tool.json`.
3. Point the runtime at this server from the repo root:

```bash
python -m mcp_tools.tavily_search.server
```

The server speaks newline-delimited JSON-RPC (`initialize`, `tools/list`, `tools/call`). The worker uses the same `call_tool()` implementation.

## Credentials

Set `TAVILY_API_KEY` in `.env`. If it is empty, the tool logs a stub and returns no hits so evaluation can continue at lower confidence.
