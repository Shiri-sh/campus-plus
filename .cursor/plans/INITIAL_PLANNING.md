# System Specification Document and Visual Description: "Campus+" (+Campus)

## System Summary

A collaborative platform for aggregating, validating, classifying, and making
accessible academic knowledge accumulated over the years. The system integrates
autonomous AI agents for sorting and academic verification of study materials, a
semantic search engine (RAG), and a full administrative management and monitoring
interface.

---

## 1. User Types and Permissions in the System

| User Type | Role Description | Key Permissions |
|---|---|---|
| **Student** | An end-user who consumes academic knowledge and contributes new materials to the community repository. | • Semantic and hierarchical search within study materials. • Viewing material details and downloading them to the local device. • Uploading files and content to the system (forwarded for review and approval). • Sending a report/feedback/note to the administrator regarding defective or missing material. |
| **Administrator (Admin)** | A monitoring authority responsible for repository reliability, maintenance, and content quality. | • Approving or rejecting new files (assisted by AI agent recommendations). • Editing, reclassifying, and deleting existing materials. • Handling student reports and inquiries (receiving email notifications via MCP). • User management, blocking harmful users, and activity tracking. |

---

## 2. Screen Specifications and Visual Structure (UI / UX)

### 2.1 Authentication Screen

**Structure:** A clean, modern page that includes the "Campus+" logo, input fields
for institutional email and password, and an option for new registration.

**Visual Elements:**

- Login / Register form with input validation.
- Automatic identification of the user's role (Student vs. Admin) upon successful
  authentication, routing to the designated screen.

### 2.2 Student Main Dashboard

**Top Navigation Bar:** Campus+ logo, a central smart search bar, a "Upload New
Material" button (prominent CTA), and a personal profile area.

**Smart Search Bar:**

- AI-powered search (RAG) and textual search. Support for natural language queries
  (e.g., "differential equations exam 2023").
- Autocomplete (Typeahead) component and quick filters (by file type: exam,
  summary, presentation, exercise).

**Interactive Folder Tree (Hierarchy & Category Explorer):**

- Displayed beneath the search bar as a clear tree/card layout: Course (e.g., Data
  Structures) → Academic Year (2024, 2023...) → Material Type (Exams, Quizzes,
  Summaries, Presentations, Recordings).
- Breadcrumb navigation allowing quick return to the desired course or year.

**Results and Files View (File Grid / List View):**

- Displays file cards including: file name, file type (PDF icon, video, slides),
  upload date, relevance score, and quick action buttons (view, download, report).

### 2.3 Item Details Modal

Compliance with requirement 4.2 of the guidelines document: displaying extended
details for a selected record.

**Structure:**

- File preview (PDF Viewer / embedded player).
- Comprehensive metadata: course name, lecturer, academic year, automated content
  summary extracted by AI.
- Direct download button to the computer/local device.
- "Report Content / Suggest Update" button opening a message dialog to the
  administrator.

### 2.4 Student Upload Workflow

**Drag & Drop Zone:** Uploading PDF files, presentations, documents, or video links.

**AI Auto-Classification Preview:**

- Upon file selection, the system displays a loading indicator and AI predictions:
  which course the file belongs to, which year, the material type, and the measured
  probability/confidence.
- The student can confirm the suggested classification or edit manually if needed.

**Status Message:** Upon upload completion, the file receives a "Pending Approval"
status and appears unavailable to general users until approved.

### 2.5 Admin Management Console

**Top KPI Cards (KPIs / Metrics Dashboard — Requirement 4.4):**

- Total materials awaiting review and approval.
- Total open reports and inquiries from students.
- Distribution of materials by active courses.

**Pending Approvals Table (Requirement 4.3):**

- Columns: file name, upload date, estimated course, confidence score, and AI agent
  recommendation (approve/reject), preview button, Approve and Reject buttons.

**Reports & Feedback Inbox:**

- Aggregation of student remarks regarding incorrect, outdated, or broken material.
- Integration of a service to send direct updates/responses to the user's email or
  to the administrator.

**User Directory Tab:** List of system users, options to Block and delete malicious
users.

---

## 3. System Architecture and AI Mechanism (Alignment with Project Guidelines)

| Project Requirement | Implementation in "Campus+" |
|---|---|
| **Independent Process AI Agent (Requirement 5)** | A Background Worker that reads newly uploaded file records: • Performs text extraction and Embedding into a vector database. • Executes semantic search against existing course materials and a RAG model to assess relevance and reliability. • Runs web queries via Tavily MCP to verify syllabus, topics of study, and academic content validation. • Updates the record with a Confidence Score and a reasoned recommendation for the administrator. |
| **Semantic Search and RAG** | Students receive accurate search results even for conceptual queries, not just exact keywords. |
| **MCP Protocol and External Services** | • Tavily MCP: Verification and web queries for the AI agent. • Gmail MCP: Sending immediate alerts to the administrator when a student submits an urgent report regarding a defective file. |
| **Architecture Patterns (CQRS & Event Sourcing)** | A clear separation between the Command path (uploading a file, admin approval, reporting) and the Query path (fetching the folder tree, fast semantic search). |

---

## 4. End-to-End User Flow

1. **Upload:** A student uploads a lecture summary for the course "Algorithms 1".
2. **Background Processing:** The independent AI agent detects the record in the
   database, inspects the text against the course vectors, verifies concepts
   against the syllabus (via Tavily), and determines a 94% match to the "Academic
   Year 2024 / Lecture Summaries" folder.
3. **Admin Review:** The administrator sees the file in the pending approvals table
   with a green AI indication, reviews it in the preview, and clicks "Approve".
4. **Publishing and Consumption:** The file becomes active, is added to the folder
   repository, and is available for RAG search to all students.
5. **Feedback:** Another student noticing a formula error clicks "Report to Admin";
   the system administrator receives an email alert via Gmail MCP and updates the
   status.

---

## 5. Initial Roadmap Steps

1. Convert specification to structured Markdown.
2. Cursor — Code planning and project structure.
3. Basic structure.
4. Task breakdown.
