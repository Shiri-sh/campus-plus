# Campus+ architecture

This document goes deeper than [README.md](../README.md): deployment boundaries, request flows, and pattern choices. The README stays the front door; read this when you need to explain *why* the tree looks the way it does.

## Design goals (course alignment)

| Course theme | How Campus+ implements it |
|--------------|---------------------------|
| MVC | `models.py` + Jinja templates + routes in `app.py` / `admin_views.py` |
| CQRS (logical) | Reads in `catalog.py`; writes in `commands/*` — no mandatory `queries/` folder name |
| Event sourcing (subset) | Append-only `Event` rows via `events.record_event` — **audit log only**, no replay |
| Separate AI agent | `python -m agent.worker` — not in the HTTP request path |
| Vector DB + semantic search | Local Chroma (`agent/embeddings.py`), hybrid merge in `catalog.py` |
| MCP external services | `mcp_tools/*` — two Studio tools; app/worker call the same `call_tool()` as the servers |
| Cloud RDBMS | MSSQL on somee.com (`DATABASE_URL`); SQLite when unset for local dev/tests |

## Where things run

```
┌─────────────────────────────────────────────────────────────┐
│  Demo machine (laptop / presentation host)                   │
│  • Flask (app.py)                                            │
│  • agent.worker                                              │
│  • instance/chroma/  (Chroma persist — copy between teammates)│
│  • instance/uploads/ (student file uploads)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ SQL
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  somee.com MSSQL — users, materials, reports, events         │
└─────────────────────────────────────────────────────────────┘

Optional at demo time:
  • MCP Studio processes: python -m mcp_tools.tavily_search.server
                          python -m mcp_tools.gmail_alert.server
  • Or in-process call_tool() with same env vars (tests, dev)
```

Drive seed data is **not** live integration: `scripts/list_drive.py` → `instance/drive_index.json` → `scripts/import_drive.py` inserts approved rows once.

## Layer map

| Layer | Modules | Responsibility |
|-------|---------|----------------|
| HTTP | `app.py`, `admin_views.py` | Auth, student UI, upload, JSON classify API; admin tabs delegate to commands + catalog |
| Query | `catalog.py` | Approved/pending lists, hybrid keyword + Chroma search, explorer filters |
| Command | `commands/materials.py`, `commands/reports.py`, `commands/users.py` | Mutations, side effects (Gmail MCP, embedding upsert on approve) |
| Audit | `events.py` | `record_event()` after successful writes (and worker completion) |
| Domain data | `models.py`, `courses.py`, `classify.py` | ORM, course name map, upload preview heuristics |
| Infra | `extensions.py`, `db_config.py`, `schema.py`, `seed.py` | Flask extensions, DB URL, lightweight migrations, course catalog bootstrap |
| Async AI | `agent/worker.py`, `agent/embeddings.py` | Poll pending uploads; Gemini summary; Tavily MCP; Chroma upsert |
| MCP | `mcp_tools/gmail_alert`, `mcp_tools/tavily_search` | Schemas + JSON-RPC servers + shared tool logic |

## Request flows

### Student search (read path)

1. Route in `app.py` calls `catalog.approved_materials` or `catalog.suggestion_items`.
2. Catalog runs SQL keyword scoring and (when Chroma/Gemini available) semantic query in parallel.
3. Results merge by material id; filters apply to both legs.
4. No writes; no events.

### Student upload (write path)

1. Route validates file, may call `classify.classify_source` for live preview (rule-based, no LLM).
2. `commands.materials.confirm_pending_upload` saves `Material` as `pending`, stores file under `instance/uploads/`.
3. Command calls `mcp_tools.gmail_alert.call_tool` to notify admins (stub if no credentials).
4. Command calls `record_event(MATERIAL_UPLOADED, ...)`.
5. Worker later picks up the row (see below); admin approve/reject is a separate command.

### Admin approve (write path)

1. `admin_views` → `commands.materials.approve_material` (or reject/delete/update variants).
2. Row updated; on approve, embedding upsert via `agent.embeddings.upsert_material`.
3. Matching `record_event` for the action.
4. Gmail notifies the uploader that the file was approved or rejected (stub if no credentials). Mail failure does not roll back the decision.

### AI worker (background)

1. Poll `Material` where `status=pending` and AI fields empty.
2. Classify metadata, optional Tavily verification, Gemini summary, confidence + recommendation.
3. Upsert vector; `record_event(AI_EVALUATION_COMPLETED, ...)`.
4. Does **not** change `status` — admins remain authoritative.

## Why `events.py` is not inside `commands/`

`record_event` is **shared infrastructure**, not a business command:

- All three command modules import it after their own commits.
- `agent/worker.py` also records `AIEvaluationCompleted` without going through `commands/`.

Putting `events.py` under `commands/` would suggest only HTTP-triggered writes emit events, which is wrong. Keeping it at repo root next to `commands/` matches “commands *call* the event log,” similar to keeping `extensions.py` outside commands.

Alternative (not used): `audit/events.py` — clearer name, same idea; moving is cosmetic only.

## `seed.py` vs `scripts/seed_embeddings.py`

Two different “seed” jobs:

| | `seed.py` | `scripts/seed_embeddings.py` |
|---|-----------|------------------------------|
| **What** | Ensures every JCT course in `courses.COURSE_MAP` exists as a `Course` row; migrates old English course names to Hebrew | Picks ~80–100 **approved** materials and writes vectors into Chroma |
| **When** | Every app startup (`app.py` app context) and start of `import_drive.py` | Once per environment (or when refreshing semantic index) |
| **DB** | Inserts missing courses only (idempotent) | Read-only on materials |
| **Chroma** | No | Yes |
| **Who calls** | `app.py`, `scripts/import_drive.py`, tests | Operators manually; documented in README |

Do not confuse with `scripts/import_drive.py`, which bulk-loads **materials** from the Drive JSON index into the database.

## MCP tools layout

Each tool is a Python package runnable as a module:

- `tool.json` — import into MCP Studio
- `tool.py` — `call_tool()` used by Flask, worker, and server
- `server.py` — newline JSON-RPC for Studio
- `__init__.py` — re-exports `call_tool` for clean imports
- `__main__.py` — `python -m mcp_tools.<name>.server`

See [mcp_tools/README.md](../mcp_tools/README.md), [gmail_alert/README.md](../mcp_tools/gmail_alert/README.md), [tavily_search/README.md](../mcp_tools/tavily_search/README.md).

## Testing vs production

- `pytest` uses in-memory SQLite and stubs external APIs — see `tests/conftest.py`.
- CI runs the same suite on push/PR (`.github/workflows/ci.yml`).

## Further reading

- [LAYOUT.md](LAYOUT.md) — ASCII repository tree
- [.cursor/plans/PROJECT_PLAN_UPDATED.md](../.cursor/plans/PROJECT_PLAN_UPDATED.md) — task history and locked layout decisions
