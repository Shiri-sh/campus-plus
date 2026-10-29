# PROJECT PLAN — Campus+ (Updated)

> **Team size:** 3 · **Deadline:** Friday (1 week from project start)
> **Last updated:** October 11, 2026 (T4: seed embeddings are a one-time batch, search is hybrid)

---

## 0. How to read this document

Implementation progress is tracked in [GitHub issues and pull requests](https://github.com/Shiri-sh/campus-plus). This document describes design and where requirements are implemented.

Each section maps back to the teacher's requirement number in parentheses.

---

## 1. What changed from the initial plan

| Topic | Initial plan (INITIAL_PLANNING.md) | Updated direction |
|---|---|---|
| **Database** | Not specified (local SQLite assumed) | **MSSQL on somee.com** (teacher's requirement). SQLite stays for local dev only. |
| **Google Drive** | Drive folder was the primary data source; spec assumed Drive integration | **No Drive integration.** Drive data was a POC. It will serve **only as seed data** imported once into the cloud DB via a migration script. |
| **AI classification** | LLM-based agent with embeddings + Tavily verification | Upload preview stays **rule-based** (`classify.py`) so the student is not waiting on an LLM. Gemini runs later, in the worker, for summary, embeddings, and the admin recommendation. |
| **Search** | RAG semantic search | Keyword scoring in `catalog.py` stays. Add **hybrid search**: Chroma semantic matches and SQL keyword matches run at the same time, then merge. Chroma is local. A one-time script embeds 80–100 seed items so semantic search covers the initial catalog. |
| **Architecture** | CQRS + Event Sourcing mentioned conceptually | Keep today's layout. **Logical CQRS:** routes stay in `app.py` / `admin_views.py`, reads stay in `catalog.py`, writes become command functions grouped by entity. **Event sourcing = an append-only audit log** on somee.com. No event replay. No required `commands/` or `queries/` directory names. |
| **MCP Tools** | Tavily + Gmail MCP mentioned | Not implemented. Must build **2 MCP Tools via MCP Studio** (Tavily search + Gmail alerts). |
| **AI Agent** | Independent background process | Not implemented. Standalone worker on the **demo machine**. It polls **pending student uploads only**. It does not read the Drive seed catalog. |
| **Seed data** | Drive index with 14K+ entries used to populate catalog | One run of `import_drive.py` inserts **already-approved** rows into somee.com. Drive preview URLs stay. The worker does not evaluate these rows. A separate one-time script embeds **80–100 selected** seed items into local Chroma for search. |

### Locked decisions (October 10, 2026)

1. **Layout.** Keep `app.py`, `admin_views.py`, `catalog.py`, `classify.py`, and `models.py`. Add command functions grouped by entity, plus `events.py` and `agent/`. Do not rename the tree into `commands/` vs `queries/` as a repo-wide move. The course asks for the CQRS pattern (see its diagram: query model reads, command model writes, one database). It does not name directories.
2. **Where things run.** Users, materials, reports, and the audit log live in **MSSQL on somee.com**. Flask, the worker, and ChromaDB run on the demo machine. Chroma stays local (the course PDF requires a vector DB, not a cloud one). One person generates it; the team shares that directory by copying it.
3. **Event sourcing.** An append-only audit-log table is enough. Do not rebuild rows by replaying events.
4. **Drive links stay.** Seeded `file_path` values remain Google Drive preview URLs. Task T15 is cancelled.
5. **Two different jobs for seed data.** The worker selects `status = pending` only. It does not score, summarize, or poll seed rows. Search is separate: `scripts/seed_embeddings.py` runs once, embeds 80–100 chosen seed items into Chroma, and then stops. That script is not a second worker.

---

## 2. Teacher's requirements — full compliance matrix

### Functional Requirements

| # | Requirement | Where / Notes |
|---|---|---|
| 1 | Choose a topic | Academic study materials for JCT students |
| 2 | User management with authentication | `app.py` — login/register with email + password, `flask-login` session |
| 3 | At least two user types | Student and Admin roles (models.py) |
| 4.1 | Data search | Text search works (`catalog.py`) across the full catalog. **Missing:** hybrid search — Chroma semantic hits for the embedded seed batch (and later approved uploads) merged with SQL keyword hits. |
| 4.2 | Show details for a result | Item Details Modal with metadata, preview, download (`student_dashboard.html`) |
| 4.3 | Display data in a table | Admin Pending Approvals table (`admin.html`) |
| 4.4 | Dashboard with KPIs | Admin KPI cards — pending count, open reports, course distribution (`admin.html`) |
| 4.5 | Data entry | Student upload workflow with classification (`upload.html`, `app.py`) |
| 5 | Independent AI agent process | **Must build:** background worker on the demo machine. It reads **pending student uploads** from somee.com, embeds them in local Chroma, verifies via Tavily, and writes confidence + recommendation. Seed rows are already approved and are out of this queue. |

### Non-Functional Requirements

| # | Requirement | Where / Notes |
|---|---|---|
| 1 | Organized MD documents | `README.md` exists but minimal. **Must add:** `INITIAL_PLANNING.md` (done), this file, architecture doc |
| 2 | Use ≥1 Skill from Skills.sh | **Must install and use** a Skill from [skills.sh](https://skills.sh) |
| 3 | Define ≥1 custom Skill + ≥1 Rule | Skill exists at `.cursor/skills/draft-issues/SKILL.md`. **Must add:** at least one `.cursor/rules/` Rule file |
| 4 | Flask application server | `app.py` — Flask 3.1.2 |
| 5 | Cloud database (somee.com) | Currently SQLite. **Must migrate to MSSQL on somee.com** |
| 6 | Vector DB + semantic search | **Must add:** local ChromaDB on the demo machine + Gemini `text-embedding-004`. Checked against the course PDF (9 Sep 2026): a vector DB and semantic search are required; cloud hosting is required for the relational database only. |
| 7 | MVC/CQRS architecture | MVC is already there (models, templates, routes). CQRS is the course diagram: the UI sends reads to a query model and writes to a command model, both on one database. **No prescribed folder names.** Reads stay in `catalog.py`. Writes become command functions. Routes stay in `app.py` and `admin_views.py`. |
| 8 | Event Sourcing pattern | **Append-only `Event` audit log** on somee.com, written on every state change. The `Material` row stays the source of truth. No replay, no projections rebuilt from events. |
| 9 | External services via MCP | **Must integrate:** Tavily MCP + Gmail MCP |
| 10 | ≥2 MCP Tools via MCP Studio | **Must develop:** two tools (see §5 below) |
| 11 | AI agent with Deep Agent + RAG + Tavily | **Must build:** agent script using Gemini + ChromaDB + Tavily |
| 12 | GitHub Repo | [Shiri-sh/campus-plus](https://github.com/Shiri-sh/campus-plus) |

---

## 3. Architecture overview (updated)

Demo machine (Flask + worker + Chroma together). Relational data is remote.

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

`classify.py` stays on the upload request. It is the fast keyword preview. It is not the worker.

---

## 4. Database: migration to somee.com MSSQL

### Current state
- SQLite database at `instance/campus_plus.db`
- SQLAlchemy ORM with models: `User`, `Course`, `Material`, `Report`

### Migration steps

1. **Create somee.com account** and provision an MSSQL database.
2. **Add `pymssql`** (or `pyodbc`) to `requirements.txt`.
3. **Update `SQLALCHEMY_DATABASE_URI`** in `app.py`:
   ```python
   # Production (somee.com)
   app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
       "DATABASE_URL",
       "mssql+pymssql://user:password@server.somee.com/dbname"
   )
   ```
4. **Run `db.create_all()`** against the remote DB to create tables.
5. **Add `Event` model** (see §6 below) before creating tables.
6. **Seed data:** run `import_drive.py` once pointing at the remote DB to insert
   the initial catalog from the Drive POC index.
7. **Keep SQLite fallback** for local development via environment variable toggle.

### New model: Event (append-only audit log)

This is the event-sourcing deliverable for the course. Each state change appends one row. Current tables (`User`, `Material`, `Report`) remain the source of truth. Nothing is rebuilt by replaying the log.

```python
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(60), nullable=False)   # e.g. "MaterialUploaded"
    entity_type = db.Column(db.String(40), nullable=False)   # e.g. "Material"
    entity_id = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    payload = db.Column(db.Text)       # JSON with event-specific data
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
```

**Event types to log:** `UserRegistered`, `UserBlocked`, `UserUnblocked`,
`MaterialUploaded`, `MaterialApproved`, `MaterialRejected`, `MaterialDeleted`,
`MaterialUpdated`, `ReportCreated`, `ReportReplied`, `AIEvaluationCompleted`.

A helper `record_event(event_type, entity_type, entity_id, payload=None)` in `events.py` is called from the command functions, after the row change succeeds. Routes do not write events themselves.

---

## 5. MCP Tools (Requirement 9 + 10)

### Tool 1: Tavily Web Search

**Purpose:** The AI agent calls this tool to verify that an uploaded file's content
matches real course syllabi and academic topics.

**Implementation:**
- Register a Tavily API key.
- Build an MCP Tool in MCP Studio that wraps the Tavily search API.
- Input: search query (e.g., "JCT Data Structures course syllabus 2024").
- Output: top search results with snippets.
- The AI agent uses results as context for its confidence scoring.

### Tool 2: Gmail Alert

**Purpose:** Send email notifications to administrators when a student submits an
urgent content report.

**Implementation:**
- Build an MCP Tool in MCP Studio that sends email via Gmail API/SMTP.
- Input: recipient email, subject, body.
- Output: send confirmation.
- Called from the report-creation command when the report message contains urgency
  keywords or when any report is created (configurable).

---

## 6. AI Agent — background worker (Requirements 5 + 11)

### Current state
- `classify.py` predicts course, year, and material type with keywords, inside the upload request. That stays. The student is waiting on that response.
- Gemini, embeddings, and Tavily do not exist yet. They belong to the worker, which runs after the upload is saved.

### Target implementation

**File: `agent/worker.py`** — a separate process on the demo machine. Same `DATABASE_URL` as Flask. Same local Chroma directory.

```
Loop:
  1. Query somee.com for materials with status="pending" and no AI evaluation.
     Seed rows are status="approved", so they never match.
  2. For each pending upload:
     a. Extract text (PyPDF2 / python-docx) from the local file
     b. Embed that text via Gemini text-embedding-004
     c. Similarity-search local Chroma. The collection already holds the
        80–100 seed embeddings, plus any uploads approved since.
        If the directory has not been copied yet, skip the similarity term.
     d. Call the Tavily MCP tool to verify academic content
     e. Generate a summary via Gemini
     f. Confidence = similarity (if any) + Tavily match + the keyword classification
        already stored on the row
     g. Write material.confidence, material.ai_recommendation, material.ai_summary
     h. Append Event "AIEvaluationCompleted"
  3. Sleep and repeat
```

The worker does not update `status`. Approval stays an admin action.

### Embeddings pipeline (Requirement 6)

- Collection name: `campus_materials`. Path from `CHROMA_PERSIST_DIR`, default `instance/chroma`.
- Embedding model: Gemini `text-embedding-004` (free tier, 768 dimensions).
- **Seed batch, once.** `scripts/seed_embeddings.py` picks 80–100 approved seed materials (spread across courses and material types), builds a document from the text stored on the row — file name, course, academic year, material type — and upserts one vector per material id. Seed rows point at Drive preview URLs, so there is no local file body to extract. The script does not change `status`, `confidence`, or `ai_summary`, and it does not call Tavily.
- **Share the directory.** One person runs the script. Everyone else copies `instance/chroma` and points `CHROMA_PERSIST_DIR` at it. They do not re-embed those 80–100 items.
- **New uploads.** The worker embeds a pending file in memory to score it. The vector joins `campus_materials` only when an admin approves, through `agent/embeddings.py`. The same directory then holds the seed batch plus approved uploads.

### Hybrid search in `catalog.py` (Requirement 6)

When the student submits a text query, `catalog.py` runs the two lookups **at the same time**, then merges:

1. **SQL keyword side** — today's token overlap over the full approved catalog, with the course / year / type filters.
2. **Chroma side** — embed the query with Gemini, take top-K from `campus_materials`, drop any id that fails those same filters.
3. **Merge by material id.** A row in both lists keeps a combined score. A keyword-only row still appears (most of the catalog has no vector). A semantic-only row still appears (a paraphrase can hit one of the 80–100 embedded seed items, or a later approved upload, without sharing tokens). Sort by the combined score.

Course, year, and type filters apply to both sides. A Chroma hit outside the active filter is discarded.

---

## 7. Code layout (Requirement 7)

### What we are not doing

No repo-wide move into `commands/` and `queries/`. The course diagram is a query model and a command model sharing one database. It does not name folders. A big rename collides with the agent work for the whole week.

### What "clean and decoupled" means here

Routes parse HTTP and call one function. They do not both change rows and build the read model.

| Module | Owns | Does not own |
|---|---|---|
| `app.py`, `admin_views.py` | Routes, templates, auth checks | Row changes, event rows, Chroma |
| `catalog.py` | Student reads. Hybrid search: Chroma and SQL at the same time, then merge. Also suggestions and explorer. | Writes |
| `scripts/seed_embeddings.py` | One-time embedding of 80–100 selected seed rows into `instance/chroma` | The worker loop, row status, Tavily |
| `classify.py` | Keyword prediction on the upload request | Gemini, Chroma, Tavily |
| `commands/materials.py` | Upload confirm, approve, reject, update, delete | HTTP, templates |
| `commands/reports.py` | Create report, reply. Reply path calls the Gmail MCP tool. | HTTP |
| `commands/users.py` | Register, block, unblock, delete | Login/session (that stays in the auth routes) |
| `events.py` | `record_event()` | Deciding when a business action happens |
| `agent/worker.py` | Poll pending uploads, score them, write the AI columns + one audit event | Approving or rejecting |
| `agent/embeddings.py` | Gemini embed + Chroma read/write. Shared by the worker, the approve command, and `catalog.py`. | Flask |
| `mcp_tools/` | Tavily and Gmail as MCP servers the worker and the report command call | Being imported as plain functions that skip MCP |

`models.py`, `extensions.py`, `templates/`, and `static/` stay where they are.

Command functions take ids and fields, not `request`. That is what lets Person A change approve/reject while Person B changes the worker, without editing the same route body.

---

## 8. Remaining tasks — ordered by priority

Historical task breakdown; completion tracked in [GitHub issues and pull requests](https://github.com/Shiri-sh/campus-plus).

> **Legend:** 🔴 Blocks submission · 🟡 Important · 🟢 Nice to have

| # | Task | Priority | Est. effort | Assignable to |
|---|---|---|---|---|
| **T1** | **Set up somee.com MSSQL** — create DB, configure connection string, verify `db.create_all()` works remotely | 🔴 | Small | Any one person |
| **T2** | **Append-only `Event` audit log** + `record_event()`. Call it from command functions for approve, reject, upload, report, block, and delete. No replay. | 🔴 | Medium | Person A |
| **T3** | **AI Agent worker** — `agent/worker.py` on the demo machine. Gemini + local Chroma + Tavily. Polls **pending student uploads only**. Does not touch seed rows. | 🔴 | Large | Person B |
| **T4** | **Hybrid search + seed vectors.** (1) `scripts/seed_embeddings.py` embeds 80–100 selected approved seed items into local Chroma, once. Share that directory with the team. (2) `catalog.py` runs the Chroma query and the SQL keyword query concurrently and merges by material id. Does not wait on the worker. Seed rows are searchable semantically; the worker still does not poll them. | 🔴 | Medium | Person B (after T8, parallel with T3) |
| **T5** | **MCP Tool #1: Tavily search** — register API key, build the tool in MCP Studio, call it from the worker. | 🔴 | Medium | Person B |
| **T6** | **MCP Tool #2: Gmail alert** — build the tool in MCP Studio, call it from the report command. | 🔴 | Medium | Person C |
| **T7** | **Extract command functions in place** — `commands/materials.py`, `commands/reports.py`, `commands/users.py`. Routes stay in `app.py` and `admin_views.py`. `catalog.py` stays the query module. No folder rename of existing files. | 🔴 | Medium | Person A |
| **T8** | **Seed data migration** — run `import_drive.py` against somee.com. Rows stay `approved`, Drive preview URLs stay, and the worker queue stays empty of these rows. | 🔴 | Small | Person A (after T1) |
| **T9** | **Install + use a Skill from Skills.sh** | 🔴 | Small | Any |
| **T10** | **Add a `.cursor/rules/` Rule file** (coding conventions, commit style, or similar) | 🔴 | Tiny | Any |
| **T11** | **Update `requirements.txt`** — add `pymssql`, `chromadb`, `google-generativeai`, `PyPDF2`, `python-docx`, `tavily-python` | 🔴 | Tiny | Whoever does T1 |
| **T12** | **Documentation** — update `README.md` with setup instructions, architecture diagram, environment variables | 🟡 | Small | Person C |
| **T13** | **CSRF protection** for POST forms (`flask-wtf` or manual tokens) | 🟡 | Small | Person C |
| **T14** | **AI summary display** — show the worker's summary in the Item Details Modal for materials it has evaluated. Seed rows have no summary; the modal should say so plainly. | 🟡 | Small | Person B (after T3) |
| **T15** | **Cancelled.** Drive preview URLs stay. They are how seeded catalog items open. Do not strip them. | — | — | — |
| **T16** | **Delete stored files on material deletion** — clean up `instance/uploads/` for student uploads. Do not delete anything for a Drive URL. | 🟢 | Tiny | Person C |

---

## 9. Seed data strategy

### What we have

The file `instance/drive_index.json` contains ~14,000 entries scraped from the JCT
shared Google Drive. The existing `scripts/import_drive.py` reads this index and
creates `Material` rows with Google Drive preview URLs as `file_path`.

### What changes

1. **Drive is NOT a runtime integration.** No Drive API calls, no Drive MCP, no
   live syncing.
2. The Drive index is a **one-time seed** to populate the cloud MSSQL database with
   a realistic initial catalog.
3. Existing Drive preview URLs (`https://drive.google.com/file/d/.../preview`) will
   remain as `file_path` values in seeded records — students can still preview
   these files via iframe.
4. **New uploads** (from students) are stored as files in `instance/uploads/` on the demo machine. `file_path` holds that filename. Only these rows enter the worker queue, and only while `status` is `pending`.
5. **The worker does not evaluate seed data.** No Tavily call, no summary, no confidence score, no `AIEvaluationCompleted` event, and no polling. Those rows stay pre-approved catalog entries.
6. **Search embeddings are a separate one-time batch.** After the import, `scripts/seed_embeddings.py` embeds 80–100 selected seed rows into `instance/chroma` for hybrid search. One run, then the team copies the directory. This is not the worker, and it does not grow to the full catalog.

### Migration script modification

Update `import_drive.py` to:
- Accept a `--remote` flag to target somee.com instead of local SQLite.
- Insert only clean, study-relevant files (existing filtering logic is already good).
- Keep `status = approved` (this is already what the script does).
- Leave `ai_summary` and `confidence` null. Null means "not evaluated", not "please enqueue". The worker's filter is `status = pending`, so these rows stay out.

---

## 10. Environment variables

The following environment variables will be needed for production:

```
SECRET_KEY=<random-secret-for-flask-sessions>
DATABASE_URL=mssql+pymssql://user:pass@server.somee.com/campus_plus
CHROMA_PERSIST_DIR=instance/chroma
GEMINI_API_KEY=<google-ai-studio-api-key>
TAVILY_API_KEY=<tavily-api-key>
GMAIL_MCP_CREDENTIALS=<gmail-oauth-or-app-password>
```

`DATABASE_URL` is the shared somee.com database. `CHROMA_PERSIST_DIR` is a local directory. One person fills it with `scripts/seed_embeddings.py`; the others copy that folder. Flask, the worker, and the demo all read the same copy.

---

## 11. Risk notes

| Risk | Mitigation |
|---|---|
| somee.com free tier may have row or size limits | Seed only the most relevant ~2,000 materials instead of all 14K. They are still inserted as approved and still skipped by the worker. |
| Gemini free tier has rate limits (60 RPM) | Seed embeddings are capped at 80–100 and run once. The worker embeds new uploads only. Teammates copy `instance/chroma` instead of re-running the script. |
| Chroma is a local directory | It is not in the cloud. The shared artifact is the generated folder: copy it to each dev machine and to the demo machine. Flask and the worker on that machine use the same path. |
| MCP Studio may require specific setup | Start the two tools early. If Studio is blocked, wrap the same calls in an MCP server the worker and the report command still speak to. |
| One week, three people, merge collisions | Person A: somee.com, audit log, command functions, seed import (T8). Person B: seed embedding script and hybrid search (T4, after T8) in parallel with the worker and Tavily (T3, T5). Person C: Gmail MCP, docs, CSRF, upload-file cleanup. Nobody moves `app.py` routes into a new tree while the others are editing them. |
