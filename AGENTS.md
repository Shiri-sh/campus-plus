# Agent and contributor guide

This repo is set up for human teammates and coding agents (Cursor, etc.). Use this file as a map; detailed architecture lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Before you change code

1. Read [README.md](README.md) for product scope and run commands.
2. Follow [.cursor/rules/git-and-agent-workflow.mdc](.cursor/rules/git-and-agent-workflow.mdc): **do not commit or push** unless someone explicitly asks.
3. After application or test changes, from repo root:

```bash
source .venv/bin/activate
pytest
```

Report pass/fail with your summary; wait for commit instructions.

## Where to put new code

| Change type | Location |
|-------------|----------|
| New read/query (search, lists) | `catalog.py` |
| New write (approve, upload side effects) | `commands/` + `events.record_event` |
| New HTTP route (student) | `app.py` |
| New HTTP route (admin) | `admin_views.py` |
| New model column / table | `models.py` + `schema.py` migration helpers |
| New MCP tool | New package under `mcp_tools/` mirroring `gmail_alert` |
| One-off ops | `scripts/` (or `scripts/dev/` if exploratory) |

Avoid repo-wide renames (`queries/` vs `catalog.py`) unless the team agreed in an issue — see project plan.

## Skills and rules (course tooling)

- **Rules:** `.cursor/rules/` (e.g. git and test workflow).
- **Project skills:** `.agents/skills/` (pytest, draft-issues, RTL, web guidelines).

## Secrets

Never commit `.env`. Use `.env.example` as the template. Gmail and API keys stay local or in deployment env only.

## Documentation

- [docs/LAYOUT.md](docs/LAYOUT.md) — repository tree
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — patterns, flows, deployment
- [mcp_tools/README.md](mcp_tools/README.md) — MCP index
- [scripts/README.md](scripts/README.md) — operational vs dev scripts
