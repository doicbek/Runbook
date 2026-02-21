# Actions

A web application for agentic workflows. Create actions from natural language prompts, decompose them into parallel task DAGs via an LLM planner, execute with mock agents, and edit any task to trigger re-execution from that point.

## Architecture

- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS v4, ShadCN UI, TanStack Query, Zustand
- **Backend**: Python, FastAPI, SQLAlchemy (async), aiosqlite, SQLite
- **LLM Providers**: OpenAI, Anthropic, DeepSeek, Google Gemini (auto-selects best model per agent type)
- **Planner**: OpenAI GPT-4o with structured output
- **Real-time**: Server-Sent Events (SSE) via sse-starlette
- **Execution**: In-process async DAG executor (asyncio), specialized agents (arXiv RAG, code execution, mock)

## Prerequisites

- Python 3.11+
- Node.js 18+
- At least one LLM API key (OpenAI recommended as baseline)

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in `backend/`:

```
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here    # optional
DEEPSEEK_API_KEY=sk-your-key-here         # optional
GOOGLE_API_KEY=your-key-here              # optional
```

Without any API key, the planner falls back to a single task per action. Each configured key unlocks its provider's models. If only `OPENAI_API_KEY` is set, all tasks gracefully fall back to GPT-4o.

### Frontend

```bash
cd frontend
npm install
```

## Running

Start both servers:

```bash
# Terminal 1 - Backend (default port 8001)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001

# Terminal 2 - Frontend
cd frontend
npm run dev
```

Open http://localhost:3000

The frontend connects to the backend at `http://localhost:8001` by default. Override with the `NEXT_PUBLIC_API_URL` environment variable.

## Usage

### Create an Action

1. Click **New Action** on the landing page
2. Enter a prompt describing what you want to accomplish
3. The LLM planner decomposes your prompt into a DAG of tasks

### Run Tasks

1. Click **Run** in the workspace header
2. Tasks execute in parallel where dependencies allow
3. Watch real-time status updates via SSE (pulse animation on running tasks)
4. View logs by clicking **Logs** on any task card

### Edit and Restart

1. Click **Edit** on any task card to modify its prompt or dependencies
2. Saving resets that task and all downstream tasks to pending
3. Click **Run** again to re-execute from the edited point
4. Upstream outputs are preserved

### Add Tasks

1. Click **Add Task** in the workspace
2. Enter a prompt and select which existing tasks it depends on
3. The new task's agent will have access to the outputs of its dependencies

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/actions` | Create action (triggers LLM planning) |
| `GET` | `/actions` | List actions |
| `GET` | `/actions/:id` | Get action with tasks |
| `PATCH` | `/actions/:id` | Update action title/prompt |
| `POST` | `/actions/:id/run` | Execute pending tasks |
| `GET` | `/actions/:id/events` | SSE stream for real-time updates |
| `POST` | `/actions/:id/tasks` | Add a task to an action |
| `PATCH` | `/actions/:id/tasks/:taskId` | Edit task (invalidates downstream) |
| `GET` | `/actions/:id/tasks/:taskId/logs` | Get task execution logs |
| `GET` | `/artifacts/:id` | Get artifact metadata |
| `GET` | `/models` | List available LLM models and defaults |
| `GET` | `/health` | Health check |

## SSE Event Types

| Event | Description |
|-------|-------------|
| `snapshot` | Full action + tasks state on connect |
| `task.started` | Task began execution |
| `task.completed` | Task finished with output |
| `task.failed` | Task failed with error |
| `log.append` | New log line from agent |
| `action.completed` | All tasks completed |
| `action.failed` | Action failed |

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app, CORS, router mounting
    config.py            # Settings (env vars)
    database.py          # Async SQLAlchemy engine + session
    models/              # SQLAlchemy models (Action, Task, TaskOutput, Artifact, Log)
    schemas/             # Pydantic request/response schemas
    routers/
      actions.py         # Action CRUD + run + SSE
      tasks.py           # Task create/edit + logs
      artifacts.py       # Artifact retrieval
    services/
      llm_client.py      # Unified multi-provider LLM client
      planner.py         # OpenAI GPT-4o structured output planner
      executor.py        # Async DAG executor
      event_bus.py       # In-process pub/sub for SSE
      agents/
        base.py          # Abstract base agent
        mock_agent.py    # Mock agent with LLM output generation
        arxiv_search_agent.py  # arXiv RAG agent (search + ChromaDB + synthesis)
        code_execution_agent.py # Sandboxed Python code agent

frontend/
  src/
    app/
      page.tsx           # Landing page
      actions/[id]/
        page.tsx         # Action workspace
    components/
      workspace/         # Task board, cards, editor, logs drawer, add task
      ui/                # ShadCN components
    lib/
      api/               # API client functions
      sse.ts             # EventSource wrapper
    hooks/               # TanStack Query hooks
    stores/              # Zustand store for real-time state
    types/               # TypeScript interfaces
```

## Multi-Model LLM Support

The system supports 4 LLM providers and auto-selects the best model per agent type:

| Agent Type | Default Model | Rationale |
|---|---|---|
| `arxiv_search` | Claude Sonnet 4.5 | Excellent at research synthesis |
| `code_execution` | DeepSeek Chat | Best at code generation |
| `report` | Claude Sonnet 4.5 | Great at long-form writing |
| `data_retrieval` | GPT-4o Mini | Simple task, fast/cheap |
| `spreadsheet` | GPT-4o Mini | Structured data, fast |
| `general` | GPT-4o | Good all-rounder |

The planner assigns models automatically when creating tasks. Users can override the model per task via the editor dropdown in the UI. If a provider's API key isn't configured, tasks fall back gracefully to the next available model.

The unified LLM client (`backend/app/services/llm_client.py`) routes:
- **OpenAI / DeepSeek / Google Gemini** through `AsyncOpenAI` with appropriate `base_url`
- **Anthropic** through `AsyncAnthropic` with automatic message format conversion

## Features

- Multi-provider LLM support (OpenAI, Anthropic, DeepSeek, Google Gemini)
- Per-task model selection with smart defaults
- Dark mode (system-aware with manual toggle)
- Markdown rendering with LaTeX math support
- Topological sort for task display order
- Parallel task execution
- DAG invalidation on edit (BFS downstream reset)
- Real-time SSE updates with Zustand overlay
- arXiv RAG agent (search + vector store + LLM synthesis)
- Sandboxed Python code execution with artifact generation
