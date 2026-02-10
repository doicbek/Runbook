# claude.md

**Project name: Workdeck**

## Project Overview

Build a modern web application inspired by Google Docs, but designed for **agentic workflows** rather than traditional documents.

The core abstraction is an **Action**:

- The landing page displays existing Actions and allows creation of new ones.
- Opening an Action reveals a workspace with:
  - A prompt input at the top.
  - Dynamically generated task cards below the prompt.
  - Each card represents a decomposed sub-task handled by an autonomous agent.
- Users can edit any task card. Editing a task triggers a restart of the workflow from that point onward.

The system must prioritize **transparency**, **editability**, and **parallel execution**.

---

## High-Level Architecture

Use a clean, production-grade architecture from the start.

### Frontend
Recommended stack:
- **Next.js (App Router)**
- **TypeScript**
- **React**
- **Tailwind**
- **ShadCN UI or similar component library**
- **React Query / TanStack Query**
- **Zustand or lightweight state store**

### Backend
Recommended stack:

- **Python + FastAPI** OR **TypeScript + NestJS**
- Strong preference for async execution
- PostgreSQL for persistence (MVP: SQLite acceptable for Steps 1–3)
- Redis for queues / pub-sub (introduce in Step 4; see MVP Scope)
- Worker system for agents

### Agent Orchestration Layer
Design this as a first-class subsystem — not an afterthought.

Prefer a DAG-style execution model where:

- Tasks are nodes
- Dependencies are edges
- Independent nodes execute in parallel

Avoid monolithic “agent loops.”

---

## Key API Endpoints

Minimal surface for backend–frontend handoff:

- `POST /actions` — Create action (body: `root_prompt`, optional `title`); returns action + initial tasks after planning.
- `GET /actions` — List actions (optional filters: status, limit).
- `GET /actions/:id` — Get action with tasks (and optionally task outputs/artifacts).
- `PATCH /actions/:id` — Update action (e.g. title, root_prompt; may trigger re-plan).
- `PATCH /actions/:id/tasks/:taskId` — Edit task (prompt, dependencies); invalidates that task and downstream; triggers restart.
- `POST /actions/:id/run` — Start or resume execution (idempotent; only runs runnable tasks).
- `GET /actions/:id/events` — SSE or WebSocket stream for real-time updates (scope: this action only).
- `GET /artifacts/:id` — Get artifact by ID (e.g. redirect or signed URL).
- `GET /actions/:id/tasks/:taskId/logs` — Stream or fetch logs for a task.

---

## Core Entities

### Action
Represents a full workflow initiated by a user prompt.

Fields:

- `id`
- `title`
- `root_prompt`
- `status` (draft, running, completed, failed)
- `created_at`
- `updated_at`

---

### Task
Represents a decomposed step within an Action.

Fields:

- `id`
- `action_id`
- `prompt`
- `status` (pending, running, completed, failed)
- `agent_type`
- `dependencies` (array of task IDs)
- `output_summary` (optional short text; full output via TaskOutput/Artifacts)
- `restart_from_here` flag

Task output is stored in **TaskOutput** and **Artifact** tables; tasks reference outputs by ID, not by embedding blobs.

---

### TaskOutput
Links a task to its structured result (one per task when completed).

Fields:

- `id`
- `task_id`
- `artifact_ids` (array of artifact IDs — a task may produce multiple artifacts, e.g. plot + table)
- `text` (optional short summary or stdout snippet)
- `created_at`

---

### Artifact
A stored artifact produced by a task (file, image, report).

Fields:

- `id`
- `task_id`
- `action_id`
- `type` (e.g. file, image, markdown)
- `mime_type`
- `url` or `storage_path` (retrievable via URL; see Key API Endpoints)
- `size_bytes` (optional)
- `created_at`

Artifacts are stored outside primary tables (object store or file system); tables hold metadata and references only.

---

### Log
Per-task execution log (for transparency and debugging).

Fields:

- `id`
- `task_id`
- `level` (info, warn, error)
- `message` (text)
- `timestamp`
- Optional: `structured` (JSON for tool calls, etc.)

Retention: define policy (e.g. keep last N per task or 30 days). Avoid unbounded growth.

---

### Agent
Logical executor attached to a task.

Agents should be tool-specialized, for example:

- Data retrieval agent
- Spreadsheet agent
- Code execution agent
- Markdown/report agent

Agents must be:

- Stateless where possible
- Idempotent
- Retryable

---

## User Experience Flow

### Landing Page

Display:

Your Actions
[ Action Card ]
[ Action Card ]
[ + Create New Action ]


Action cards should show:

- Title
- Status
- Last updated
- Progress indicator

---

### Creating an Action

User enters a prompt:

> "Create a Google spreadsheet with weather data in San Francisco for 2025 and fit a sinusoidal function to the temperature data."

Backend immediately:

1. Persists the Action.
2. Sends the prompt to a **Task Planner** service.
3. Planner decomposes it into tasks.
4. Tasks are returned and rendered as editable cards.

---

### Workspace Layout

Top → Prompt input  
Below → Horizontal or grid layout of task cards.

Example cards:

[ Fetch weather data from the internet ]

[ Put the data into a Google spreadsheet ]

[ Write Python code to fit a sine function and plot ]

[ Create an editable markdown page with plots and explanation ]


Each card must support:

- Inline editing
- Status indicator
- Logs / output drawer
- Restart button

---

## Critical Behavior Requirements

### Editable Workflow

If a user edits a task:

- Invalidate that task and all downstream tasks.
- Preserve upstream outputs.
- Rebuild the DAG.
- Resume execution automatically.

This is a **hard requirement**.

---

### Restart from edited task

When a user edits a task (prompt or dependencies), apply the following semantics:

**Data flow**

- **Outputs:** Downstream tasks receive inputs by **reference** (artifact IDs or task output IDs), not by value. When a task is invalidated, its outputs remain readable until overwritten by a re-run. Downstream tasks that are re-run read the latest outputs of their dependency tasks from the store.
- **Upstream:** Preserve upstream outputs; do not re-run upstream tasks unless the user explicitly edits them or triggers a full re-plan.

**DAG rebuild**

- Recompute which tasks are invalid (edited task + all tasks that depend on it, transitively). Mark those tasks as pending and clear their outputs (or mark outputs as stale). Optionally allow the planner to be re-invoked if the user changed the root prompt or requested re-plan; otherwise keep the existing DAG and only reset state for invalidated nodes.
- **Edge case — user edits a completed task:** Invalidate that task and all downstream; set the edited task to pending; on resume, re-run it then downstream. Upstream outputs are unchanged.
- **Edge case — concurrent edit:** If the user edits a second task while a run is in progress, define a policy (e.g. cancel in-flight run and apply both edits, or queue the second edit until the current run completes). Prefer a single source of truth: one "pending edit" or "last saved" state per task.

**Versioning (optional for MVP):** Keep the previous plan or task set for "undo" or diff; otherwise at least persist the current DAG and task versions so restart is deterministic.

---

### Parallel Execution

Tasks with no dependencies MUST execute concurrently.

Use a worker queue such as:

- Celery
- Temporal
- BullMQ
- or equivalent

Avoid sequential orchestration unless necessary.

---

### Transparency

Users should never wonder:

> “What is the system doing right now?”

Expose:

- Task status
- Streaming logs
- Outputs
- Failures
- Retries

Think **observable agents**, not black boxes.

**Error and retry policy**

- **Retries:** Configurable per task (e.g. max 3 attempts, exponential backoff). Only retry on transient errors (network, rate limit); do not retry on validation or auth failures.
- **Visibility:** Expose "Retrying (2/3)" in the UI (via events). On final failure, mark task as failed and surface the error; optionally mark the whole action as failed or pause and let the user fix and restart.
- **Partial success:** If one of several parallel tasks fails, do not auto-fail the entire action; mark that task failed and optionally pause downstream. User can edit and restart from the failed task.

---

## Task Planning Service

Implement a planner that converts a root prompt into structured tasks.

### Planner contract

**Inputs**

- `root_prompt` (string, required)
- Optional: `existing_tasks` or `action_id` for re-plan / refinement (e.g. user changed the prompt and we want to preserve or diff)

**Output schema** (LLM structured output)

```json
{
  "tasks": [
    {
      "prompt": "...",
      "agent_type": "data_retrieval",
      "dependencies": []
    }
  ]
}
```

- `dependencies`: array of task indices (0-based) or task IDs; must refer only to earlier tasks in the same list (no cycles, no forward refs).

**Validation rules**

- DAG validity: no cycles; every dependency index < task index (or resolve IDs to a valid topological order).
- Reject empty `tasks` or missing required fields (`prompt`, `agent_type`).
- If invalid: log, optionally retry with a fix prompt (e.g. "Output a valid DAG"), or return a safe fallback (e.g. single task with the root prompt).

**Retry / fallback**

- On LLM failure or timeout: retry once with same prompt; then return a single-task fallback (root prompt, generic agent_type) so the user can still proceed.
- Idempotency: same `root_prompt` may be sent multiple times (e.g. user clicks "Create" twice); backend should dedupe or return existing plan when appropriate.

The planner should:

- Minimize dependencies
- Maximize parallelism
- Prefer tool-specialized tasks over giant multi-step ones

Do NOT allow the planner to produce vague tasks.

**Bad:** "Analyze the data"

**Good:** "Fit a sinusoidal regression using Python and output coefficients"

---

### Execution Engine

The orchestrator should:

- Build a DAG from tasks.
- Dispatch runnable tasks.
- Listen for completion events.
- Trigger downstream nodes.

Strongly consider an event-driven design.

---

### Suggested Agent Tooling

Design agents around capabilities. Prefer **MCP** to expose these as tools (see [Agent tooling via MCP](#agent-tooling-via-mcp-model-context-protocol)):

**Data Agent**

- Web access
- APIs
- Scraping if needed

**Spreadsheet Agent**

- Google Sheets API
- Table formatting

**Code Agent**

- Sandboxed Python execution
- Plot generation
- Artifact storage

**Report Agent**

- Markdown generation
- Editable documents
- Versioning

Artifacts should be stored and retrievable via URLs.

---

### Persistence Model

Minimum tables:

- `actions`
- `tasks`
- `task_outputs`
- `artifacts`
- `logs`

Avoid embedding large blobs in primary tables.

---

### Events / real-time

Use **Server-Sent Events (SSE)** or **WebSocket** to push updates. Prefer SSE for simplicity (one-way, action-scoped stream).

**Subscription:** Client subscribes per action: `GET /actions/:id/events` (SSE) or `WS /actions/:id/events`. One stream per action; no global stream. Reconnect with `Last-Event-ID` or accept full-state snapshot on connect.

**Event types and payloads (example)**

| Event type       | Payload (example) |
|------------------|-------------------|
| `task.started`   | `{ "task_id": "...", "action_id": "..." }` |
| `task.completed` | `{ "task_id": "...", "output_summary": "...", "artifact_ids": ["..."] }` |
| `task.failed`    | `{ "task_id": "...", "error": "...", "retry_count": 1 }` |
| `task.retrying`  | `{ "task_id": "...", "attempt": 2, "max_attempts": 3 }` |
| `log.append`     | `{ "task_id": "...", "level": "info", "message": "..." }` |
| `action.completed` | `{ "action_id": "..." }` |
| `action.failed`  | `{ "action_id": "...", "reason": "..." }` |

Client should handle reconnection (exponential backoff) and, on connect, optionally fetch current state via `GET /actions/:id` to avoid gaps.

The UI should feel alive.

---

## MVP Scope (IMPORTANT)

Do NOT overbuild.

**Phased infra:** Use a **single process** and **SQLite** (or in-memory store) for **Steps 1–3**. Avoid Redis and a separate worker process until the core loop (create → plan → run → edit → restart) is stable. Introduce **Redis + worker queue** in **Step 4** when adding streaming/real-time and scaling execution.

Phase 1 must achieve:

- ✅ Create Action
- ✅ Decompose prompt into tasks
- ✅ Render editable task cards
- ✅ Execute tasks in parallel (mock agents acceptable)
- ✅ Restart workflow from edited task

Skip authentication initially if needed. Skip billing. Skip multi-user. Ship the core loop fast.

---

## Non-Goals (for now)

- Perfect agents
- Fully autonomous planning
- Complex permissions
- Enterprise features

Focus on the orchestration UX.

---

## Design Philosophy

Optimize for:

- Visibility
- Control
- Determinism
- Modularity

Avoid:

- Hidden agent reasoning
- Giant prompt chains
- Fragile orchestration

The product should feel like: **"Google Docs for computation and agent workflows."**

---

## Implementation Strategy

Recommended order:

**Step 1:** Backend skeleton — Action + Task models, Planner stub

**Step 2:** Frontend workspace — Task cards, Editing

**Step 3:** DAG executor — Worker queue

**Step 4:** Streaming updates

**Step 5:** Real agents (and MCP integration; see below)

---

## Agent tooling via MCP (Model Context Protocol)

Use **MCP** as the standard way for agents to access tools and context. MCP gives a uniform way to expose capabilities (browsers, data, spreadsheets, code execution, files) to the orchestration layer without hard-coding one-off integrations.

**Principles**

- **Agents talk to MCP servers:** Each agent type (data, spreadsheet, code, report) uses one or more MCP servers for its tools. The backend (or worker) runs an MCP client that discovers tools and resources from configured servers and passes them to the agent runtime (e.g. LLM with tool use).
- **Configure servers per environment:** E.g. a "Data" MCP server for web/API access, a "Spreadsheet" server for Google Sheets, a "Code" server for sandboxed execution. Keep credentials and server URLs in config; do not bake them into the app.
- **Stateless, per-task:** For each task, the orchestrator invokes the appropriate agent with the task prompt and the tools/resources provided by the relevant MCP server(s). No long-lived agent state; session scope is the task.
- **Observability:** Log MCP tool calls and results (e.g. in the existing `logs` table or structured log events) so "Transparency" applies to MCP usage as well.

**MVP:** In Phase 1, mock agents can simulate MCP tool calls (e.g. return stub responses). As you move to real agents (Step 5), integrate one or two MCP servers (e.g. filesystem or a simple data API) and expand from there.

**References:** [Model Context Protocol](https://modelcontextprotocol.io) — use the standard for tools, resources, and prompts where it fits.

---

## Final Guiding Principle

The user is always in the loop.

Agents propose. The system executes. The user can intervene at any moment.