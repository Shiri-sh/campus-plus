# Campus+

An intelligent academic materials platform for JCT students — upload, discover, and share study resources with AI-powered search and automated content moderation.

## What it does

- **Smart catalog** — browse, search, and preview thousands of academic materials organized by course, year, and type
- **Hybrid search** — combines SQL keyword matching with Gemini-powered semantic search (ChromaDB) for results that understand what you mean, not just what you typed
- **AI content agent** — a background worker evaluates every new upload: extracts text, verifies relevance via Tavily, generates a summary, and recommends approve/reject to admins
- **Upload with live classification** — students upload files and get instant course/type predictions before submitting
- **Admin dashboard** — KPI cards, pending approval queue, content reports, and user management in one view
- **MCP tool integration** — Tavily web search and Gmail notifications built as MCP Studio tools

## Architecture

```mermaid
flowchart TB
    Student([Student]) -->|search / browse| Flask
    Student -->|upload / report| Flask
    Admin([Admin]) -->|approve / reject / manage| Flask

    subgraph Server ["Demo Machine"]
        Flask["Flask App"]
        Reads["catalog.py\n(hybrid search)"]
        Commands["commands/\n(materials, reports, users)"]
        Events["events.py\n(audit log)"]
        Worker["agent/worker.py\nGemini + Tavily"]
        Chroma[("ChromaDB\ncampus_materials")]

        Flask -->|reads| Reads
        Flask -->|writes| Commands
        Commands --> Events
        Reads <--> Chroma
        Worker <--> Chroma
    end

    Worker -->|polls pending| DB
    Commands -->|insert / update| DB
    Reads -->|query| DB
    Worker -->|verify content| Tavily["Tavily MCP"]
    Commands -->|notify admin| Gmail["Gmail MCP"]

    DB[("MSSQL\nsomee.com")]
```

**Pattern:** Logical CQRS — reads stay in `catalog.py`, writes go through command functions that append audit events. Event sourcing via an append-only log (no replay).

## Tech stack

| Layer | Technology |
|-------|-----------|
| Server | Flask 3.1 · Flask-Login · Flask-SQLAlchemy |
| Database | MSSQL on somee.com (SQLite for local dev) |
| Vector DB | ChromaDB (local, Gemini `text-embedding-004`) |
| AI | Google Gemini (summaries + embeddings) · Tavily (web verification) |
| MCP Tools | Tavily search · Gmail alerts (built in MCP Studio) |
| Frontend | Jinja2 templates · vanilla JS · CSS |

## Quick start

```bash
git clone https://github.com/Shiri-sh/campus-plus.git
cd campus-plus
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```
SECRET_KEY=<random-secret>
DATABASE_URL=mssql+pymssql://user:pass@server.somee.com/campus_plus
GEMINI_API_KEY=<google-ai-studio-key>
TAVILY_API_KEY=<tavily-key>
CHROMA_PERSIST_DIR=instance/chroma
GMAIL_MCP_CREDENTIALS=<gmail-oauth-or-app-password>
```

Run the app:

```bash
python app.py                    # Flask on http://127.0.0.1:5000
python -m agent.worker           # AI worker (separate terminal)
```

One-time data setup:

```bash
python scripts/import_drive.py --remote   # seed catalog into somee.com
python scripts/seed_embeddings.py         # embed 80-100 items into ChromaDB
```
