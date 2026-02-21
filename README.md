# Workdeck

A Google Docs-inspired platform for **agentic workflows**. Describe what you want to accomplish, and Workdeck decomposes it into a parallel task DAG, executes each step with a specialised AI agent, and lets you edit, inspect, and re-run any part of the workflow at any time.

---

## Key Features

- **Action workspace** — prompt → planner → editable task DAG → parallel execution
- **6 real built-in agents** — arXiv search, code execution, data retrieval, spreadsheet, report, general
- **Agent Studio** — create, edit, and AI-modify custom agents with generated Python code
- **Planner dashboard** — configure the planning model, system prompt, max tasks, and preview plans
- **Multi-model LLM support** — OpenAI (GPT-5, GPT-4.1, o3/o4), Anthropic (Claude 4.6), Google (Gemini 2.5), DeepSeek
- **Real-time updates** — Server-Sent Events stream task status, logs, and outputs live
- **Artifact system** — agents produce downloadable files (plots, .xlsx, .csv, JSON) stored as artifacts
- **Inline rendering** — Markdown, LaTeX math ($...$ / $$...$$), and inline images in task outputs

---

## Architecture

| Layer | Stack |
|---|---|
| **Frontend** | Next.js 16 (App Router), TypeScript, Tailwind CSS v4, ShadCN UI, TanStack Query |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), aiosqlite, SQLite |
| **LLM Providers** | OpenAI, Anthropic, Google Gemini, DeepSeek (OpenAI-compatible) |
| **Planning** | OpenAI structured output API (`response_format=PlannerOutput`) |
| **Real-time** | Server-Sent Events via sse-starlette |
| **Execution** | In-process async DAG executor (`asyncio.gather` for parallel tasks) |
| **Vector store** | ChromaDB (arXiv semantic search) |
| **Code sandbox** | Subprocess Python with artifact scanning |

---

## Built-in Agents

| Agent | Type | Implementation |
|---|---|---|
| 📚 ArXiv Search | `arxiv_search` | Searches arXiv API, stores embeddings in ChromaDB, synthesises literature review with citations |
| ⚙️ Code Execution | `code_execution` | LLM generates Python, runs in sandboxed subprocess, saves plots/files as artifacts |
| 🌐 Data Retrieval | `data_retrieval` | LLM plans queries → DuckDuckGo search → fetches pages, extracts HTML tables, CSV, JSON, Excel → LLM synthesis |
| 📊 Spreadsheet | `spreadsheet` | LLM generates openpyxl code → real .xlsx with formatted headers, frozen rows, summary sheet, artifact download |
| 📝 Report | `report` | Multi-step: extract findings (parallel) → outline → write sections (parallel) → assemble with images + LaTeX |
| 🤖 General | `general` | Chain-of-thought: classify → plan steps → execute steps → synthesise structured markdown answer |

All agents accept upstream task outputs as context and pass them to downstream tasks.

---

## Model Registry

| Provider | Models |
|---|---|
| **OpenAI** | `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `o3`, `o3-mini`, `o4-mini`, `gpt-4o`, `gpt-4o-mini` |
| **Anthropic** | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`, `claude-sonnet-4-5` |
| **Google** | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.0-flash` |
| **DeepSeek** | `deepseek-chat` |

Default models per agent type (auto-selected, falls back gracefully if key missing):

| Agent | Default Model |
|---|---|
| `arxiv_search`, `report` | `claude-sonnet-4-6` |
| `code_execution`, `spreadsheet`, `general` | `gpt-5` |
| `data_retrieval` | `gpt-5-mini` |

Users can override the model per task in the task editor. Configure in the Planner dashboard (`/planner`) for the planning model.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- At least one LLM API key (OpenAI recommended as baseline — required for the planner's structured output)

---

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
OPENAI_API_KEY=sk-...           # required for planner + OpenAI models
ANTHROPIC_API_KEY=sk-ant-...    # optional — unlocks Claude models
GOOGLE_API_KEY=...              # optional — unlocks Gemini models
DEEPSEEK_API_KEY=sk-...         # optional — unlocks DeepSeek models
```

### Frontend

```bash
cd frontend
npm install
```

---

## Running

```bash
# Terminal 1 — Backend (port 8001)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001

# Terminal 2 — Frontend (port 3000)
cd frontend
npm run dev
```

Open **http://localhost:3000**

The frontend connects to the backend at `http://localhost:8001` by default. Override with `NEXT_PUBLIC_API_URL`.

---

## Navigation

| URL | Description |
|---|---|
| `/` | Action list (landing page) |
| `/actions/:id` | Action workspace — task DAG, run controls, logs |
| `/agents` | Agent Studio catalog |
| `/agents/new` | Create a custom agent |
| `/agents/:id` | View/edit agent — code, description, AI-modify panel |
| `/planner` | Planner configuration dashboard |

---

## API Endpoints

### Actions

| Method | Path | Description |
|---|---|---|
| `POST` | `/actions` | Create action (triggers LLM planning) |
| `GET` | `/actions` | List actions |
| `GET` | `/actions/:id` | Get action with tasks |
| `PATCH` | `/actions/:id` | Update title/prompt |
| `POST` | `/actions/:id/run` | Execute pending tasks |
| `GET` | `/actions/:id/events` | SSE stream |
| `POST` | `/actions/:id/tasks` | Add a task |
| `PATCH` | `/actions/:id/tasks/:taskId` | Edit task (invalidates downstream) |
| `GET` | `/actions/:id/tasks/:taskId/logs` | Task logs |

### Agent Studio

| Method | Path | Description |
|---|---|---|
| `GET` | `/agent-definitions` | List all agents (builtins + custom) |
| `GET` | `/agent-definitions/tools` | Tool catalog (8 entries) |
| `GET` | `/agent-definitions/:id` | Single agent |
| `POST` | `/agent-definitions` | Create custom agent |
| `PATCH` | `/agent-definitions/:id` | Update agent |
| `DELETE` | `/agent-definitions/:id` | Delete agent (custom only) |
| `POST` | `/agent-definitions/scaffold` | AI-generate agent code (does not save) |
| `POST` | `/agent-definitions/:id/modify` | AI-modify existing agent code |

### Planner Config

| Method | Path | Description |
|---|---|---|
| `GET` | `/planner-config` | Get planner configuration |
| `PATCH` | `/planner-config` | Update model, system prompt, max tasks, retries |
| `GET` | `/planner-config/api-status` | Check which API keys are configured |
| `POST` | `/planner-config/preview` | Test-plan a prompt and preview tasks |
| `POST` | `/planner-config/modify-prompt` | AI-rewrite the system prompt |

### Other

| Method | Path | Description |
|---|---|---|
| `GET` | `/artifacts/:id/content` | Download artifact file |
| `GET` | `/models` | List available models with configured keys |
| `GET` | `/health` | Health check |

---

## SSE Events

| Event | Payload |
|---|---|
| `snapshot` | Full action + tasks state on connect |
| `task.started` | `{ task_id, action_id }` |
| `task.completed` | `{ task_id, output_summary, artifact_ids }` |
| `task.failed` | `{ task_id, error, retry_count }` |
| `log.append` | `{ task_id, level, message }` |
| `action.completed` | `{ action_id }` |
| `action.failed` | `{ action_id, reason }` |

---

## Project Structure

```
backend/
  app/
    main.py                   # FastAPI app, lifespan (DB init + seeding)
    config.py                 # Settings (env vars via pydantic-settings)
    database.py               # Async SQLAlchemy engine + session factory
    models/
      action.py               # Action model
      task.py                 # Task model
      task_output.py          # TaskOutput + Artifact models
      log.py                  # Log model
      agent_definition.py     # Custom/builtin agent definitions
      planner_config.py       # Planner config singleton
    schemas/
      task.py                 # Task create/update schemas
      planner.py              # Planner output schema (structured output)
      agent_definition.py     # Agent CRUD + scaffold/modify schemas
      planner_config.py       # Planner config schemas
    routers/
      actions.py              # Action CRUD + run + SSE
      tasks.py                # Task create/edit + logs
      artifacts.py            # Artifact download
      agent_definitions.py    # Agent Studio CRUD + scaffold
      planner_config.py       # Planner config endpoints
      models.py               # Model list endpoint
    services/
      llm_client.py           # Unified multi-provider LLM client
      planner.py              # DAG planner (OpenAI structured output)
      executor.py             # Async DAG executor
      event_bus.py            # In-process pub/sub for SSE
      code_runner.py          # Sandboxed subprocess Python runner
      arxiv_service.py        # arXiv API + ChromaDB vector store
      vector_store.py         # ChromaDB wrapper
      planner_config_seed.py  # Seed default planner config on boot
      agents/
        base.py               # Abstract BaseAgent
        mock_agent.py         # LLM-based mock (fallback for unknown types)
        arxiv_search_agent.py # arXiv RAG agent
        code_execution_agent.py  # Sandboxed code agent
        data_retrieval_agent.py  # Web search + table extraction agent
        spreadsheet_agent.py  # openpyxl .xlsx generation agent
        report_agent.py       # Multi-step report synthesis agent
        general_agent.py      # Chain-of-thought reasoning agent
        scaffolding_service.py   # LLM code generation for custom agents
        tool_catalog.py       # Static tool catalog (8 tools)
        seed_builtins.py      # Seed 6 builtin agents on boot
        registry.py           # Agent factory (DB-first, then native, then mock)

frontend/
  src/
    app/
      page.tsx                # Landing page (action list)
      actions/[id]/page.tsx   # Action workspace
      agents/
        page.tsx              # Agent Studio catalog
        new/page.tsx          # Create agent
        [id]/page.tsx         # Agent detail / edit
      planner/page.tsx        # Planner config dashboard
    components/
      workspace/              # TaskBoard, TaskCard, TaskCardEditor, LogsDrawer
      agents/                 # AgentCard, AgentBuilderForm, ToolSelector
      ui/                     # ShadCN components
    lib/api/                  # API client functions (actions, tasks, models, agents, planner)
    hooks/                    # TanStack Query hooks
    stores/                   # Zustand store (real-time SSE state overlay)
    types/index.ts            # TypeScript interfaces
```

---

## Agent Studio

### Using Built-in Agents

All 6 built-in agents are pre-seeded at startup. Pick an agent type in the task editor dropdown. The planner automatically assigns appropriate agent types when decomposing prompts.

### Creating Custom Agents

1. Go to `/agents/new`
2. Enter a name and description
3. Select tools from the catalog (python-docx, openpyxl, httpx, playwright, etc.)
4. Click **Generate Code** — the scaffolding service uses an LLM to write a complete `BaseAgent` subclass
5. Review and edit the code in the textarea
6. Click **Save** — the agent becomes available in the task editor dropdown immediately

### Modifying Agents (AI Assist)

On any agent detail page (`/agents/:id`), the **AI Modify** panel lets you describe a change in plain English (e.g. "add retry logic", "also save a CSV"). The modify endpoint sends the current code + your instruction to an LLM and returns updated code for review before saving.

### Dynamic Loading

Custom agent code is stored in the `agent_definitions` table and loaded at runtime via `exec()` into a controlled namespace (`{BaseAgent, chat_completion, asyncio, logging, Any}`). Built-in agents can also be overridden by saving code to their DB record.

---

## Planner Dashboard (`/planner`)

- **API key status** — shows which providers are configured
- **Planning model** — select which OpenAI model runs the structured-output planner
- **System prompt editor** — full control over how the planner decomposes tasks; AI-modify button to rewrite it with plain-English instructions
- **Max tasks / retries** — tune planner behaviour
- **Custom agent context** — automatically injected into the planner prompt so it can route tasks to user-defined agent types
- **Test sandbox** — enter any prompt and preview the planned tasks without creating an action
