# Repository layout

ASCII map of the tree. For patterns and flows, see [ARCHITECTURE.md](ARCHITECTURE.md).

```
campus-plus/
├── app.py                 # Flask entry (student routes + app setup)
├── admin_views.py         # Admin routes
├── catalog.py             # Reads / search (query side)
├── classify.py            # Upload preview classification
├── commands/              # Writes (command side)
│   ├── materials.py
│   ├── reports.py
│   └── users.py
├── events.py              # Append-only audit log helper
├── models.py              # SQLAlchemy models
├── courses.py             # Course name map (Drive + UI)
├── seed.py                # Course catalog bootstrap (not bulk materials)
├── schema.py              # DB schema helpers
├── extensions.py          # db, csrf, login_manager
├── db_config.py           # DATABASE_URL / SQLite fallback
├── agent/
│   ├── worker.py          # Background AI evaluation (`python -m agent.worker`)
│   └── embeddings.py      # Chroma + Gemini embeddings
├── mcp_tools/             # Two MCP Studio tools (see mcp_tools/README.md)
│   ├── gmail_alert/
│   └── tavily_search/
├── scripts/
│   ├── README.md
│   ├── list_drive.py      # Build Drive index JSON
│   ├── import_drive.py    # Seed materials into DB
│   ├── seed_embeddings.py # One-time Chroma batch
│   └── dev/               # Scratch helpers (not demo path)
├── templates/             # Jinja2 HTML
├── static/
│   ├── css/
│   └── js/
├── tests/                 # pytest suite (`pytest` from repo root)
├── docs/
│   ├── LAYOUT.md          # this file
│   ├── PRD.md             # Product requirements (course deliverable)
│   └── ARCHITECTURE.md
├── README.md
├── AGENTS.md
├── requirements.txt
├── pytest.ini
├── .env.example
├── .github/workflows/ci.yml
├── .cursor/
│   ├── plans/             # Project planning markdown
│   └── rules/             # Agent workflow rules
└── .agents/skills/        # Project Cursor skills
```

**Local / gitignored (not in git):** `.venv/`, `.env`, `instance/` (`uploads/`, `chroma/`, `*.db`, Drive index files).
