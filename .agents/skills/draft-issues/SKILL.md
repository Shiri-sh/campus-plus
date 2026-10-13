---
name: draft-issues
description: >-
  Draft GitHub issues for Shiri-sh/campus-plus following the repo's established
  conventions: atomic scope, clear acceptance criteria, proper labelling, and
  cross-references. Use when the user asks to create issues, plan work, break
  down a feature, or mentions "draft issue", "open issue", or "new issue".
---

# Draft Issues for campus-plus

## Golden rules

1. **Atomic** — one issue = one deliverable task. If a request touches multiple
   modules, routes, or concerns → split into separate issues and cross-link
   with `Depends on` / `Related`.
2. **Simple wording, clear AC** — every issue has checkboxable `Acceptance criteria`.
   Write them so a reviewer can verify pass/fail without ambiguity.
3. **Labels are mandatory** — pick from the existing label set below. You MAY
   create a new label only when no existing label fits; justify it in your
   response to the user.
4. **Ask when in doubt** — if the scope feels large, or you're unsure about
   direction, ask the user whether to split or what to prioritize before
   drafting.
5. **Check for duplicates first** — before drafting, run
   `gh issue list --repo Shiri-sh/campus-plus --state open --json number,title`
   and scan for issues covering the same or overlapping scope. If a potential
   duplicate or overlap exists, tell the user and ask whether to proceed,
   extend the existing issue, or skip.

---

## Existing labels (use these first)

| Label | Description |
|-------|-------------|
| `bug` | Something isn't working |
| `enhancement` | New feature or request |
| `documentation` | Improvements or additions to documentation |
| `question` | Further information is requested |
| `ai` | AI / RAG / embeddings |
| `search` | Search & retrieval |
| `email` | Email & MCP mail |
| `notifications` | Notifications |
| `student-ux` | Student-facing UX |
| `admin` | Admin console |
| `security` | Security hardening |
| `architecture` | Command vs Query paths |
| `auth` | Product / auth boundaries |
| `accessibility` | Barrier affecting people with disabilities |
| `good first issue` | Good for newcomers |
| `help wanted` | Extra attention is needed |

### Priority labels

Suggest a priority for every issue. Present your recommendation to the user and
let them confirm or change it before applying.

| Label | When to use |
|-------|-------------|
| `P0-critical` | Blocks other work or production is broken |
| `P1-high` | Should be done this sprint / next |
| `P2-medium` | Important but not urgent |
| `P3-low` | Nice to have, backlog |

> Priority labels may not exist on the repo yet. Create them on first use
> with `gh label create` (colors: P0 `#b60205`, P1 `#d93f0b`, P2 `#fbca04`,
> P3 `#0e8a16`).

Only create a new label when none of the above cover the topic. When you do,
propose a name, hex color, and one-line description for the user to approve.

---

## Issue template

Use this structure for every issue. Omit optional sections only when truly
irrelevant.

```markdown
## Context
One or two sentences: why this matters and what exists today.

## Scope
What this issue covers (and explicitly what it does NOT, if useful).

## Acceptance criteria
- [ ] Concrete, verifiable checklist item
- [ ] Another item

## Out of scope *(optional)*
- Items explicitly excluded to keep the issue atomic.

## Depends on *(optional)*
- #N (title) — why the dependency exists.

## References *(optional)*
- Files, routes, templates, or earlier discussion issues.
```

### Size labels

Suggest a size for every issue alongside the priority. Present your
recommendation to the user and let them confirm or change it.

| Label | Meaning |
|-------|---------|
| `size/S` | A few hours — one file/module, straightforward |
| `size/M` | ~1 day — touches 2-3 files, some design choices |
| `size/L` | 2+ days — cross-cutting, needs design or discussion first |

If your estimate is **L**, consider whether the issue should be split.

> Size labels may not exist on the repo yet. Create them on first use
> with `gh label create` (colors: S `#0e8a16`, M `#fbca04`, L `#d93f0b`).

### Title conventions

- Prefix with the **area** when relevant:
  `Query path:`, `Command path:`, `Student UX:`, `Security:`, `Ops:`,
  `Discuss:`, `Admin:`, `Docs:`.
- Keep titles short and scannable — a noun-phrase or imperative verb.
- Examples from this repo:
  - `Query path: RAG semantic search for student catalog`
  - `Command path: shared notifications module (Gmail MCP + dev stub)`
  - `Security: CSRF protection for POST forms`
  - `Discuss: public catalog vs login / registration`

### Discussion issues (`Discuss:` prefix)

For open questions or architecture decisions, use a slightly different body:

```markdown
## Context
Background and why a decision is needed.

## Goal of this issue
What decision we need to reach (not implementation).

## Options (to evaluate in comments) *(if applicable)*
- **Option A** — …
- **Option B** — …

## Decision checklist
- [ ] Question 1
- [ ] Question 2

**No implementation in this issue** — discussion and agreed direction only.

## References
- Relevant files and issues.
```

---

## Workflow

1. **Understand the request** — read the user's description. Scan relevant
   source files if needed (`app.py`, `models.py`, `catalog.py`, etc.).
2. **Duplicate check** — list open issues and look for overlap. If found, ask
   the user before continuing.
3. **Check for atomicity** — if the work naturally splits into 2+ issues, tell
   the user and propose the split before drafting.
4. **Draft the issue(s)** — use the template above. Include title, labels,
   suggested priority, and size estimate.
5. **Present for review** — show the draft to the user. Ask:
   *"Should I open this on GitHub, adjust anything, or split further?"*
6. **Create on GitHub** — only after the user approves, run:
   ```bash
   gh issue create \
     --repo Shiri-sh/campus-plus \
     --title "…" \
     --body "…" \
     --label "label1,label2"
   ```

---

## Splitting heuristic

Split when any of these apply:
- The AC list has items touching **different files/modules** that can ship independently.
- Frontend and backend work can be reviewed separately.
- A discussion/decision must happen before implementation.
- The issue mixes **Command path** and **Query path** concerns.

When splitting, each child issue should cross-reference siblings with
`## Depends on` or `## Related`.

---
