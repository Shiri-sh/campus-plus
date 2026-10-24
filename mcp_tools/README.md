# MCP tools

Campus+ talks to MCP Studio tools from command functions, not from route handlers.

| Tool | Status | Called from |
|---|---|---|
| `gmail_alert` | Implemented — [gmail_alert/](gmail_alert/) | `commands/materials.py` after a pending upload |
| `tavily_search` | Planned (issue #6) | AI worker |
