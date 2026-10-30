# MCP tools

Campus+ talks to MCP Studio tools from command functions, not from route handlers.

| Tool | Status | Called from |
|---|---|---|
| `gmail_alert` | Implemented — [gmail_alert/](gmail_alert/) | `commands/materials.py` after a pending upload; `commands/reports.py` after a student report |
| `tavily_search` | Implemented — [tavily_search/](tavily_search/) | AI worker (`agent.worker`) |
