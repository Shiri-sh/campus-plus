# Product Requirements Document (PRD) — Campus+

**Version:** 1.0  
**Date:** October 2026  
**Team:** 3 students — course capstone project  
**Repository:** [Shiri-sh/campus-plus](https://github.com/Shiri-sh/campus-plus)

> This document describes **what** the system should provide to users and **why**. Implementation detail, architecture, and development tasks live in [`.cursor/plans/PROJECT_PLAN_UPDATED.md`](../.cursor/plans/PROJECT_PLAN_UPDATED.md) and [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Vision and goals

**Campus+** is a platform for JCT students to discover, share, and validate study materials (exams, summaries, slides, etc.). It aggregates a community catalog, enables smart search, supports uploads with pre-classification, and gives admins approval and monitoring tools — with a standalone AI agent that helps assess relevance before an admin decides.

**Problem:** Materials are scattered (Drive, groups, manual sharing), relevant content is hard to find, and there is no consistent quality gate before publication.

**Solution:** Central catalog + hybrid search (keywords and semantic) + admin approval queue + content reports + a background agent for new uploads.

---

## 2. Audience and roles

| Role | Primary need | Success looks like… |
|------|--------------|---------------------|
| **Student** | Find material by course/year/type; upload; report issues | Relevant search results; easy upload; feedback on reports |
| **Admin** | Maintain catalog quality; handle reports; manage users | Clear KPIs; approval queue with AI recommendation; fast actions |

---

## 3. Functional requirements (mapped to instructor requirements)

| # | Requirement | Product description | Acceptance criteria |
|---|-------------|---------------------|---------------------|
| 1 | Choose a topic | Academic study materials platform for JCT | Topic reflected in UI, data model, and catalog content |
| 2 | User management + authentication | Register/login (email + password), secure session | Unauthenticated users cannot access protected content; passwords not stored in plain text |
| 3 | At least two user types | Student and Admin | Different routing after login; admin capabilities not available to students |
| 4.1 | Data search | Text search + semantic (RAG) search on approved catalog | Results filterable by course/year/type; fallback to keyword search if vector DB unavailable |
| 4.2 | Show record details | Details modal: metadata, preview, download | Selecting an item from the table/list opens full details |
| 4.3 | Display in a table | Admin pending-approvals table | Columns: file name, date, estimated course, AI confidence, actions |
| 4.4 | KPI dashboard | Metric cards: pending, open reports, course distribution | Data loaded from DB when dashboard opens |
| 4.5 | Data entry | Student upload + classification (editable before submit) | After submit — status “pending approval”; not visible to everyone until approved |
| 5 | Standalone AI agent process | Background worker: text extraction, embeddings, Tavily, summary and recommendation | Processes only student uploads with **pending** status; does not re-evaluate Drive seed data |

---

## 4. Non-functional requirements

| # | Requirement | Direction in Campus+ |
|---|-------------|----------------------|
| 1 | Organized MD documents | README, PRD (this file), ARCHITECTURE, project plan |
| 2 | Use ≥1 Skill from skills.sh | Project skills (e.g. draft-issues, pytest) |
| 3 | Custom Skill + Rule | `.agents/skills/`, `.cursor/rules/` |
| 4 | Flask application server | `app.py` + `admin_views.py` |
| 5 | Cloud database (somee.com) | MSSQL for production; SQLite for local dev |
| 6 | Vector DB + semantic search | Local Chroma + embeddings (Gemini) |
| 7 | MVC / CQRS | Models + templates; reads in `catalog.py`, writes in `commands/` |
| 8 | Event sourcing (log) | Append-only event table — no replay |
| 9–11 | MCP, MCP tools, Deep Agent + RAG + Tavily | `mcp_tools/` + `agent/worker.py` |
| 12 | GitHub repository | Shiri-sh/campus-plus |

---

## 5. User experience — main screens

### 5.1 Authentication (login / register)

- Campus+ logo, login and registration forms, basic validation.
- After login — route to student or admin dashboard by role.

### 5.2 Student dashboard

- Bar: search, upload button, profile.
- Search with suggestions (suggest), filter by material type (`material_type`).
- Hierarchical navigation: course → year → type (breadcrumb).
- Results table/list: name, type, date; details, download, report.
- AI relevance and confidence — in summary/details modal, not duplicate columns in the results table.

### 5.3 Item details modal

- Preview (PDF / iframe for Drive seed items).
- Metadata: course, year (0 = “unknown”), type, AI summary when present.
- Download; “Report to admin” button.

### 5.4 Upload

- File selection; classification preview (course/year/type) — editable.
- Read-only AI fields before submit: relevance, confidence, summary (when available).
- After submit — “pending approval” message.

### 5.5 Admin console

- KPI cards (4.4).
- Pending table (4.3) with confidence score, summary (eye icon), approve/reject.
- Reports inbox + replies; Gmail alerts on relevant events.
- User management: block/delete.

### 5.6 Reports — student

- `/student/reports` — report status and admin replies.

---

## 6. End-to-end flow (primary user story)

1. A student uploads a summary for “Algorithms 1”.
2. Pre-classification is shown; the student confirms or edits and submits — record is `pending`.
3. Background worker runs Gemini (summary), embeddings to Chroma, Tavily (verification), and writes confidence + recommendation.
4. Admin sees confidence and summary on the row, checks preview, approves or rejects.
5. Approved item enters the catalog and hybrid search.
6. Another student reports an error — admin gets an alert (Gmail MCP) and replies; the student sees an update on the reports page.

---

## 7. Out of scope

- Live Google Drive integration (one-time seed only + preview links).
- Event-sourcing replay to rebuild state.
- Automatic approval without an admin (AI recommends only).
- Full AI re-evaluation of the entire seed catalog (~14K) — only a batch of embeddings for search (80–100 items) + worker on pending uploads.

---

## 8. Seed data and trust model

- **Seed:** One-time import from `drive_index.json` — `approved` rows, `file_path` as Drive URL.
- **New uploads:** Files in `instance/uploads/`; only these enter the worker queue.
- **Search:** Approved catalog only; filters apply to both SQL and Chroma.

---

## 9. External integrations

| Service | Product use |
|---------|-------------|
| **Gemini** | Summaries, embeddings |
| **Tavily (MCP)** | Background academic content verification |
| **Gmail (MCP)** | Alerts to admin/reporter/uploader on upload/report/approve events |
| **somee.com MSSQL** | Users, materials, reports, event log |
| **Chroma (local)** | Vector storage for semantic search |

---

## 10. Success metrics (demo checklist)

- Student finds material via hybrid search within ≤3 clicks from the home dashboard.
- Upload appears in the admin queue with confidence and summary (after worker).
- Admin sees KPIs and performs approve/reject with audit log entries.
- Two MCP tools run via MCP Studio and are invoked from the system.
- Worker runs as a process separate from Flask.

---

## 11. Related documents

| Document | Purpose |
|----------|---------|
| **`docs/PRD.md` (this file)** | Product requirements — course deliverable |
| **`.cursor/plans/INITIAL_PLANNING.md`** | Screen specification — initial version |
| **`.cursor/plans/PROJECT_PLAN_UPDATED.md`** | Implementation plan, compliance matrix, tasks T1–T16 |
| **`docs/ARCHITECTURE.md`** | Patterns, flows, deployment |
| **`README.md`** | Setup and run instructions for developers/reviewers |

---

## 12. History

- An initial PRD was written in Hebrew (outside the repo) — basis for team planning.
- Cursor produced `INITIAL_PLANNING.md` and `PROJECT_PLAN_UPDATED.md` from that spec.
- This PRD consolidates requirements into one clear document for reviewers without replacing the implementation plan.
