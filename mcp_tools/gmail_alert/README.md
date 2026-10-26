# gmail_alert — MCP Tool #2

Sends a plain-text email. Campus+ calls this after a student upload is saved as `pending`, and after a student files a content report.

## Schemas

Import [`tool.json`](tool.json) into MCP Studio.

| Direction | Fields |
|---|---|
| Input | `recipient` (email), `subject` (string), `body` (string) |
| Output | `ok` (boolean), `confirmation` (string), `mode` (`smtp` / `stub` / `error`) |

## MCP Studio

1. Create a tool named `gmail_alert`.
2. Paste the input and output schemas from `tool.json`.
3. Point the runtime at this server from the repo root:

```bash
python -m mcp_tools.gmail_alert.server
```

The server speaks newline-delimited JSON-RPC (`initialize`, `tools/list`, `tools/call`). Flask uses the same `call_tool()` implementation the server exposes.

## Credentials

Set `GMAIL_MCP_CREDENTIALS` in `.env` (never commit the real value):

```
GMAIL_MCP_CREDENTIALS=you@gmail.com:your-app-password
```

JSON is also accepted: `{"user":"you@gmail.com","password":"your-app-password"}`.

Use a [Gmail app password](https://support.google.com/accounts/answer/185833), not the account password. Optional: `GMAIL_SMTP_HOST` (default `smtp.gmail.com`), `GMAIL_SMTP_PORT` (default `587`).

If `GMAIL_MCP_CREDENTIALS` is empty, the tool **logs the message and returns a stub confirmation**. The upload is still saved.

## Who is emailed

Every unblocked administrator. The body includes uploader email, course, year, material type, filename, and a link to `/admin?tab=approvals`.
