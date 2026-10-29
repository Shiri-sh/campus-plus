# Scripts

Operational scripts run from the **repo root** with the venv active.

## Production / team workflow

| Script | Purpose | Typical command |
|--------|---------|-----------------|
| [list_drive.py](list_drive.py) | Crawl the public Drive folder HTML and write `instance/drive_index.json` | `python scripts/list_drive.py` |
| [import_drive.py](import_drive.py) | Load materials from that JSON into the DB (idempotent); `--remote` targets MSSQL from `.env` | `python scripts/import_drive.py` or `--remote` |
| [seed_embeddings.py](seed_embeddings.py) | One-time batch: embed ~80–100 approved materials into local Chroma | `python scripts/seed_embeddings.py` |

Order for a fresh catalog: `list_drive` → `import_drive` → (on demo machine) `seed_embeddings`, then share `instance/chroma/`.

## Development only

[dev/](dev/) holds throwaway helpers used while building the Drive crawler (save HTML, inspect `flip-entry` markup). They are **not** part of CI, README quick start, or the demo path. Run from repo root, e.g. `python scripts/dev/peek_drive.py`.
