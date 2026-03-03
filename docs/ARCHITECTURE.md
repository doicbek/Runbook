# Runbook Architecture

## System Overview

Runbook is a web application for agentic workflows — "Google Docs for computation and agent workflows." Users create **Actions** from natural language prompts, which are decomposed into a DAG of **Tasks** executed by specialized AI agents.

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   Backend    │────▶│  LLM APIs    │
│  Next.js     │◀────│  FastAPI     │◀────│  OpenAI /    │
│  Port 3000   │ SSE │  Port 8001   │     │  Anthropic / │
└─────────────┘     └──────┬───────┘     │  Google /    │
                           │              │  DeepSeek    │
                    ┌──────▼───────┐     └──────────────┘
                    │   SQLite     │
                    │  actions.db  │
                    └──────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router), TypeScript, React 19, Tailwind CSS v4, ShadCN UI |
| State | Zustand (client), React Query / TanStack Query (server) |
| Backend | Python 3.12+, FastAPI, uvicorn, async/await throughout |
| Database | SQLite via aiosqlite + SQLAlchemy 2.0 (async) |
| LLM | Multi-provider: OpenAI, Anthropic, Google, DeepSeek via unified `chat_completion()` |
| Real-time | Server-Sent Events (SSE) per action |
| Package mgmt | uv (backend), npm (frontend) |

## Directory Structure

```
/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan, router mounting
│   │   ├── config.py            # Pydantic settings (env vars)
│   │   ├── database.py          # SQLAlchemy async engine, session factory, init_db()
│   │   ├── models/              # SQLAlchemy ORM models (18 files)
│   │   │   ├── action.py        # Action (workflow)
│   │   │   ├── task.py          # Task (DAG node)
│   │   │   ├── artifact.py      # Artifact (file output)
│   │   │   ├── artifact_version.py
│   │   │   ├── task_output.py   # TaskOutput (structured result)
│   │   │   ├── log.py           # Per-task execution logs
│   │   │   ├── agent_iteration.py # Per-attempt execution records
│   │   │   ├── agent_definition.py # Custom agent definitions
│   │   │   ├── agent_skill.py   # Self-improving skills
│   │   │   ├── skill_relation.py / skill_concept.py  # Skill ontology graph
│   │   │   ├── agent_memory_model.py  # Per-agent-type memory
│   │   │   ├── action_template.py / action_schedule.py
│   │   │   ├── llm_usage.py / tool_usage.py  # Cost & analytics tracking
│   │   │   └── planner_config.py
│   │   ├── routers/             # FastAPI route handlers (14 files)
│   │   │   ├── actions.py       # CRUD + run + fork + breadcrumbs
│   │   │   ├── tasks.py         # Task CRUD + run-code + iterations
│   │   │   ├── artifacts.py     # Artifact serving + versioning
│   │   │   ├── agent_definitions.py  # Agent studio CRUD + scaffold + modify
│   │   │   ├── agent_skills.py  # Skills CRUD + ontology
│   │   │   ├── agent_memory.py  # Per-agent memory CRUD
│   │   │   ├── templates.py     # Action template CRUD
│   │   │   ├── schedules.py     # Scheduled actions CRUD
│   │   │   ├── planner_config.py # Planner settings
│   │   │   ├── cost.py          # Cost tracking endpoints
│   │   │   └── analytics.py     # Tool usage analytics
│   │   ├── schemas/             # Pydantic request/response models
│   │   └── services/            # Business logic
│   │       ├── executor.py      # Main execution orchestrator
│   │       ├── dag_scheduler.py # DAG traversal + parallel dispatch
│   │       ├── planner.py       # LLM-based task decomposition
│   │       ├── llm_client.py    # Multi-provider LLM interface
│   │       ├── recovery_manager.py  # LLM-triaged error recovery
│   │       ├── recovery_planner.py  # Recovery plan generation
│   │       ├── event_bus.py     # In-memory pub/sub for SSE
│   │       ├── event_publisher.py   # Typed event publishing helpers
│   │       ├── artifact_versioning.py  # Artifact version management
│   │       ├── scheduler.py     # Background schedule execution
│   │       ├── skill_capture.py # Auto-capture skills from execution
│   │       ├── mcp_client.py    # MCP server connection management
│   │       ├── code_runner.py   # Sandboxed Python execution
│   │       └── agents/          # Agent implementations (20 files)
│   │           ├── base.py      # BaseAgent abstract class
│   │           ├── registry.py  # Agent lookup + dynamic loading
│   │           ├── coding_agent.py      # Agentic coding with tools
│   │           ├── coding_tools.py      # File/bash tools for coding agent
│   │           ├── code_execution_agent.py  # Python code gen + run
│   │           ├── data_retrieval_agent.py  # Web search + fetch
│   │           ├── spreadsheet_agent.py     # Excel generation
│   │           ├── report_agent.py          # Parallel report writing
│   │           ├── general_agent.py         # General-purpose agent
│   │           ├── arxiv_search_agent.py    # ArXiv + ChromaDB search
│   │           ├── sub_action_agent.py      # Hierarchical child actions
│   │           ├── mcp_agent.py             # MCP-tool-only agent
│   │           ├── agent_memory.py          # Memory load/save
│   │           └── agent_skills.py          # Skill injection + capture
│   ├── artifacts/               # Stored artifact files
│   ├── data/                    # Agent memory files
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/                 # Next.js pages
│       │   ├── page.tsx         # Landing page (action list + create)
│       │   ├── actions/[id]/page.tsx  # Workspace page
│       │   ├── agents/          # Agent studio pages
│       │   ├── skills/          # Skills management
│       │   ├── planner/         # Planner config
│       │   ├── templates/       # Action templates
│       │   └── schedules/       # Scheduled actions
│       ├── components/
│       │   ├── app-sidebar.tsx  # Navigation sidebar
│       │   ├── create-action-dialog.tsx
│       │   └── workspace/       # Workspace components
│       │       ├── task-card.tsx          # Task card with outputs
│       │       ├── task-card-editor.tsx   # Inline task editing
│       │       ├── task-board.tsx         # DAG tier layout
│       │       ├── task-logs-drawer.tsx   # Log viewer
│       │       ├── workspace-header.tsx   # Action header + controls
│       │       ├── diff-viewer.tsx        # Git diff viewer
│       │       └── pause-guidance-panel.tsx
│       ├── hooks/               # React Query hooks
│       │   ├── use-actions.ts   # Action CRUD mutations
│       │   ├── use-tasks.ts     # Task mutations
│       │   ├── use-action-events.ts  # SSE event handling
│       │   └── ...
│       ├── lib/
│       │   ├── api.ts           # Base fetch wrapper
│       │   ├── api/             # API client functions
│       │   └── sse.ts           # SSE connection with reconnect
│       ├── stores/
│       │   └── action-store.ts  # Zustand store for real-time state
│       └── types/
│           └── index.ts         # TypeScript type definitions
├── docs/                        # Documentation
├── dev.sh                       # Development startup script
├── CLAUDE.md                    # AI assistant instructions
└── .env                         # Environment variables (not tracked)
```

## Core Data Model

```
Action (1) ──────── (*) Task
  │                    │
  │                    ├── (*) TaskOutput
  │                    ├── (*) Artifact ──── (*) ArtifactVersion
  │                    ├── (*) Log
  │                    └── (*) AgentIteration
  │
  ├── parent_action_id (self-ref for sub-actions)
  └── forked_from_id (self-ref for forks)

AgentDefinition ──── AgentSkill ──── SkillRelation / SkillConcept
AgentMemory ──── AgentMemoryVersion
ActionTemplate
ActionSchedule
LLMUsage
ToolUsage
PlannerConfig (singleton)
```

### Key Entities

**Action** — A workflow initiated by a user prompt. Status: `draft` → `running` → `completed`/`failed`.

**Task** — A DAG node within an action. Has `dependencies` (array of task IDs), `agent_type`, `prompt`, `status`. Tasks with no unmet dependencies run in parallel.

**Artifact** — A file produced by a task (images, spreadsheets, code, reports). Stored on disk at `backend/artifacts/{action_id}/{task_id}/`. Versioned via `ArtifactVersion`.

**AgentIteration** — Tracks every execution attempt per task with timing, tool calls, reasoning, and outcome. Enables the iteration timeline UI.

## Execution Flow

### 1. Action Creation

```
User prompt → POST /actions
  → persist Action (status=draft)
  → call Planner (LLM structured output)
  → persist Tasks with dependencies
  → auto-trigger execute_action()
  → SSE: action.planned, task list
```

### 2. DAG Execution

```
execute_action(action_id)
  → load all tasks
  → dag_scheduler.run_dag()
    → find runnable tasks (all deps completed)
    → asyncio.gather(*runnable_tasks)
    → for each task:
        → load agent (builtin or dynamic from DB)
        → inject: memory, skills, dependency outputs, MCP tools
        → agent.run(prompt, context)
        → save outputs, artifacts
        → SSE: task.started, task.completed/failed, log.append
    → repeat until all tasks done or failed
  → recovery (if failures):
    → LLM triage: retry or recovery sub-action
    → up to 3 attempts per task
  → SSE: action.completed / action.failed
```

### 3. Task Editing & Restart

```
User edits task prompt → PATCH /actions/:id/tasks/:taskId
  → BFS invalidation: edited task + all downstream
  → reset invalidated tasks to "pending"
  → preserve upstream completed outputs
  → POST /actions/:id/run
  → re-execute only invalidated tasks
```

### 4. Sub-Actions

The `sub_action` agent creates child actions with their own DAGs (max depth 3). Artifacts propagate from child to parent. Events forwarded via SSE.

## Agent System

### Built-in Agents (9)

| Agent | Purpose | Key Tools |
|-------|---------|-----------|
| `general` | Chain-of-thought reasoning | LLM only |
| `code_execution` | Generate + run Python code | Subprocess, pip auto-install |
| `coding` | Multi-file code changes in git worktree | read_file, write_file, edit_file, glob, grep, bash |
| `data_retrieval` | Web search + page fetching | DuckDuckGo, httpx |
| `spreadsheet` | Excel generation via openpyxl | Code runner |
| `report` | Parallel section writing + assembly | LLM + image injection |
| `arxiv_search` | Academic paper search | ArXiv API, ChromaDB |
| `sub_action` | Hierarchical child workflows | Spawns child Action |
| `mcp` | MCP-server-only agent | Derives all tools from MCP |

### Custom Agents (Agent Studio)

Users create custom agents via the UI:
1. Define name, description, tool selection
2. AI scaffolds agent code
3. Review and save to DB
4. Dynamic loading at runtime via `exec()`
5. AI-modify: describe change → LLM rewrites code

### Agent Memory & Skills

- **Memory**: Per-agent-type lessons from failures stored as markdown files
- **Skills**: Auto-captured from execution (success → learning, failure → error_pattern, recovery → correction)
- **Ontology**: Knowledge graph linking skills to concepts (tools, libraries, anti-patterns)
- Skills injected into agent prompts with `[AVOID]`/`[PROVEN]` labels

## Real-Time Updates (SSE)

Client subscribes via `GET /actions/:id/events`. On connect, receives full state snapshot, then live events:

| Event | Trigger |
|-------|---------|
| `action.planned` | Tasks created by planner |
| `task.started` | Agent begins execution |
| `task.completed` | Agent finished successfully |
| `task.failed` | Agent failed (with error) |
| `task.recovering` | Recovery attempt starting |
| `task.paused` / `task.resumed` | User pause/resume |
| `log.append` | New log entry |
| `action.completed` / `action.failed` | Terminal states |
| `cost.update` | LLM cost tracking |

Frontend state management:
- **Zustand store** holds real-time overrides (task status, logs, cost)
- **React Query** handles persistent data (action details, task list)
- SSE events update Zustand → components re-render

## LLM Integration

### Multi-Provider Registry

```python
chat_completion(model, messages, tools=None, **kwargs)
```

Unified interface supporting:
- **OpenAI**: gpt-5, gpt-5-mini, gpt-4.1, o3, o4-mini, etc.
- **Anthropic**: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5
- **Google**: gemini-2.5-pro, gemini-2.5-flash
- **DeepSeek**: deepseek-chat

Graceful fallback when API key missing. Per-agent-type model defaults.

### Planner

Uses OpenAI structured output (`response_format=PlannerOutput`) to decompose prompts into task DAGs. Validates: no cycles, no forward references, non-empty tasks. Falls back to single-task on failure.

## MCP Integration

Agents can connect to MCP (Model Context Protocol) servers for external tools:
- Configured via `mcp_config` on agent definitions
- Tool names prefixed: `mcp__{server}__{tool}` to avoid collisions
- `mcp` agent type derives ALL tools from MCP servers
- Any agent with `mcp_config` gets MCP tools alongside hardcoded tools

## Key API Endpoints

### Actions
- `POST /actions` — Create action (auto-plans + auto-runs)
- `GET /actions` — List with pagination, search, status filter
- `GET /actions/:id` — Get with tasks, outputs, artifacts
- `PATCH /actions/:id` — Update title/prompt
- `DELETE /actions/:id` — Delete with cascade cleanup
- `POST /actions/:id/run` — Resume execution
- `POST /actions/:id/fork` — Fork action
- `GET /actions/:id/events` — SSE stream
- `GET /actions/:id/breadcrumbs` — Parent chain for sub-actions

### Tasks
- `PATCH /actions/:id/tasks/:taskId` — Edit task (triggers invalidation)
- `POST /actions/:id/tasks/:taskId/pause` / `resume`
- `GET /actions/:id/tasks/:taskId/iterations` — Execution history
- `GET /actions/:id/tasks/:taskId/logs` — Task logs

### Other
- `/agent-definitions/` — Agent studio CRUD
- `/skills/` — Self-improving skills + ontology
- `/agent-memory/` — Per-agent memory
- `/templates/` — Action templates
- `/schedules/` — Scheduled actions
- `/planner/config` — Planner settings
- `/cost/` — Cost tracking
- `/analytics/` — Tool usage analytics

## Development

### Setup

```bash
# Backend
cd backend
uv pip install -r requirements.txt
cp ../.env.example .env  # Add API keys

# Frontend
cd frontend
npm install
```

### Running

```bash
./dev.sh  # Starts both backend (8001) and frontend (3000)
```

Or manually:
```bash
# Backend
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend && npm run dev
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key |
| `GOOGLE_API_KEY` | No | — | Google AI API key |
| `DEEPSEEK_API_KEY` | No | — | DeepSeek API key |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./actions.db` | Database URL |
| `CORS_ORIGINS` | No | `["http://localhost:3000"]` | Allowed CORS origins |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8001` | Backend URL for frontend |
