# Campus+

A portal for JCT students to search, preview, upload, and report academic study materials. Administrators review uploads, handle reports, and manage users.

The Flask app, the AI worker, and local ChromaDB run on the **demo machine**. Users, courses, materials, reports, and the audit log live in **MSSQL on somee.com**. Local SQLite is the fallback for development.

Repository: [Shiri-sh/campus-plus](https://github.com/Shiri-sh/campus-plus)

## Architecture

Matches [PROJECT_PLAN_UPDATED.md](.cursor/plans/PROJECT_PLAN_UPDATED.md) §3. Routes parse the request, then call one side: reads in `catalog.py`, writes in command functions. `classify.py` stays on the upload request as a fast keyword preview. It is not the worker.

```
┌──────────────────────────────────────────────────────────────┐
│  Demo machine                                                │
│                                                              │
│  Flask (app.py, admin_views.py)                              │
│    routes parse the request, then call one side:             │
│                                                              │
│    reads                          writes                     │
│    catalog.py                     commands/materials.py      │
│    (search, suggest, explorer)    commands/reports.py        │
│                                   commands/users.py          │
│                                          │                   │
│                                          ▼                   │
│                                   events.py → audit row      │
│                                                              │
│  agent/worker.py          local ChromaDB                     │
│  pending uploads only     collection: campus_materials       │
│  Gemini + Tavily MCP      filled first by seed_embeddings.py │
│                           then by approved uploads           │
└──────────────┬───────────────────────────┬───────────────────┘
               │                           │
               ▼                           ▼
     MSSQL on somee.com            MCP servers (MCP Studio)
     user, course, material,       tavily_search  — worker calls this
     report, event (audit log)     gmail_alert    — report command calls this
```

```mermaid
flowchart LR
  subgraph demo [Demo machine]
    Flask[Flask app.py / admin_views.py]
    Catalog[catalog.py reads]
    Commands[command writes]
    Events[events.py audit row]
    Worker[agent/worker.py]
    Chroma[local ChromaDB campus_materials]
    Flask --> Catalog
    Flask --> Commands
    Commands --> Events
    Worker --> Chroma
    Catalog --> Chroma
  end
  MSSQL[(MSSQL on somee.com)]
  MCP[MCP Studio: tavily_search / gmail_alert]
  Flask --> MSSQL
  Worker --> MSSQL
  Worker --> MCP
  Commands --> MCP
```

**Today:** Flask auth, student catalog, upload, reports, admin review, CSRF, Hebrew/RTL UI, local SQLite, and the `gmail_alert` MCP tool (stub without credentials). Course names are seeded on startup (`seed.py`).

**Still to land:** somee.com MSSQL, remaining command modules, audit log, worker, Chroma hybrid search, Tavily MCP. The setup below already names the variables and commands those pieces will use.

## Local development setup

1. Clone the repo and create a virtual environment:

```bash
cd campus-plus
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows (cmd/PowerShell)
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the environment template and edit values. **Do not commit `.env`.**

```bash
cp .env.example .env
# Windows: copy .env.example .env
```

4. For local work you can leave `SECRET_KEY` and `DATABASE_URL` empty. Flask then uses the development secret and SQLite at `instance/campus_plus.db`.

5. Start the app (see [Running each component](#running-each-component)). Open http://127.0.0.1:5000

`instance/` (database, uploads, Drive index, Chroma folder) is gitignored.

### somee.com MSSQL

1. Create an MSSQL database on [somee.com](https://somee.com).
2. Install the MSSQL driver when that work lands (`pymssql` is planned in `requirements.txt`).
3. Set `DATABASE_URL` in `.env`:

```
DATABASE_URL=mssql+pymssql://USER:PASSWORD@SERVER.somee.com/DATABASE
```

4. Restart Flask. `db.create_all()` runs on startup against that URI. Flask and the worker must share the same `DATABASE_URL`.

Leave `DATABASE_URL` unset to keep local SQLite.

### ChromaDB

Chroma stays **local** on the demo / each developer machine (not in the cloud).

1. Set `CHROMA_PERSIST_DIR` (default `instance/chroma`).
2. One person runs `scripts/seed_embeddings.py` (when it exists) to embed 80–100 seed items into collection `campus_materials`.
3. Everyone else **copies that folder** and points `CHROMA_PERSIST_DIR` at it. Do not re-embed the seed batch.

Install `chromadb` when hybrid search / the worker land.

### API keys

| Variable | Where to get it | Used by |
|---|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | Worker summaries, `text-embedding-004` |
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) | Tavily MCP tool (worker verification) |
| `GMAIL_MCP_CREDENTIALS` | Gmail app password (`you@gmail.com:app-password`) | `gmail_alert` MCP tool — emails admins after a student upload |

Put real values only in `.env` or the machine environment. Never commit them.

## Environment variables

See [PROJECT_PLAN_UPDATED.md](.cursor/plans/PROJECT_PLAN_UPDATED.md) §10 and `.env.example`.

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes when debug is off | Flask sessions and CSRF. Default `campus-plus-dev-key` is for local debug only. |
| `DATABASE_URL` | For somee.com | Shared relational DB. Unset = local SQLite. |
| `CHROMA_PERSIST_DIR` | For search / worker | Local Chroma path. Default `instance/chroma`. |
| `GEMINI_API_KEY` | For embeddings / summaries | Google AI Studio. |
| `TAVILY_API_KEY` | For the worker | Tavily MCP. |
| `GMAIL_MCP_CREDENTIALS` | For upload (and later report) email | `gmail_alert` MCP tool. Empty = log-only stub. |
| `FLASK_DEBUG` | Optional | Unset or `true` enables the debug server. `false` / `0` disables it. |

If the default `SECRET_KEY` is used while debug is disabled, the app logs a warning and you should set a strong random value before any shared or production run.

## Running each component

From the repo root, with the virtualenv active and `.env` loaded.

### Flask app

```bash
python app.py
```

Open http://127.0.0.1:5000

### Gmail MCP tool

After a student confirms an upload, `commands/materials.py` calls `gmail_alert` for every unblocked administrator. See [`mcp_tools/gmail_alert/README.md`](mcp_tools/gmail_alert/README.md).

```bash
python -m mcp_tools.gmail_alert.server
```

Without `GMAIL_MCP_CREDENTIALS` the tool only logs the message (dev stub). The material is still saved.

### AI worker

Planned process on the demo machine. Same `DATABASE_URL` and `CHROMA_PERSIST_DIR` as Flask. Polls **pending student uploads only** (not Drive seed rows).

```bash
python -m agent.worker
```

Needs `GEMINI_API_KEY`, `TAVILY_API_KEY`, and the Tavily MCP tool. This module is not in the repo yet.

### Seed scripts

**Course names** (already automatic): `seed.py` runs when Flask starts.

**Drive catalog into the database** — needs `instance/drive_index.json` (gitignored). Uses the same `DATABASE_URL` as the app, so set that first if you are targeting somee.com:

```bash
python scripts/import_drive.py
```

Rows are inserted as **approved** with Drive preview URLs. The worker does not evaluate them.

**Rebuild the Drive index** (optional, only if the JSON is missing):

```bash
python scripts/list_drive.py
```

**Seed embeddings** (planned, once per team):

```bash
python scripts/seed_embeddings.py
```

Embeds 80–100 selected approved seed items into `CHROMA_PERSIST_DIR`. Then copy that directory to the other machines. This is not a second worker.

## Team

Campus+ is built by **Shiri Shachor**, **Naomi Tal**, and **Tammy Dinavetsky**.

Sprint split from [PROJECT_PLAN_UPDATED.md](.cursor/plans/PROJECT_PLAN_UPDATED.md) §8:

| Role | Focus |
|---|---|
| Person A | somee.com, audit log, command functions, Drive seed import |
| Person B | AI worker, Tavily MCP, hybrid search, seed embeddings |
| Person C | Gmail MCP, documentation, CSRF, upload-file cleanup |
