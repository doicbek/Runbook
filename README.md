# runbook

runbook turns a natural-language prompt into a live, editable DAG of AI agent tasks. Describe what you need, watch agents work in parallel, and intervene at any point — edit a task, pause an agent, or restart from any node.

## Quick Start

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add at least OPENAI_API_KEY

# 2. Frontend
cd frontend && npm install

# 3. Run
./dev.sh start                # or manually: uvicorn + npm run dev
```

Open **http://localhost:3000**. Create an action, type a prompt, and watch it go.

## How It Works

```
Prompt  ──>  Planner (LLM)  ──>  Task DAG  ──>  Parallel Agent Execution
                                     ^                    |
                                     |                    v
                                  Edit / Restart     Artifacts + Logs
```

1. You submit a prompt (an "Action").
2. An LLM planner decomposes it into concrete tasks with typed agents and dependency edges.
3. The DAG executor runs independent tasks in parallel via `asyncio.gather`.
4. Each task streams logs and produces artifacts (files, plots, spreadsheets).
5. Edit any task mid-flight — runbook invalidates downstream nodes and re-runs from that point.

## Agents

| Type | What it does |
|---|---|
| `code_execution` | Generates and runs Python in a sandbox. Auto-installs missing packages. Produces plots, CSVs, computed results. |
| `coding` | Agentic coding loop in a git worktree. Reads, writes, edits files, runs tests, debugs — up to 50 tool-use iterations. |
| `data_retrieval` | Web search via DuckDuckGo, fetches pages, extracts tables and structured data. |
| `spreadsheet` | Generates real `.xlsx` files with openpyxl — formatted headers, frozen panes, summary sheets. |
| `report` | Multi-pass report writer: extracts findings in parallel, outlines, writes sections in parallel, assembles with images and LaTeX. |
| `arxiv_search` | Searches arXiv, indexes with ChromaDB, synthesises a literature review with citations. |
| `general` | Chain-of-thought reasoning: classifies the task, plans steps, executes them sequentially, synthesises a structured answer. |
| `sub_action` | Spawns a child Action with its own DAG. Artifacts propagate back to the parent. Max depth 3. |

Custom agents can be created in the Agent Studio (`/agents/new`) — describe what you want, select tools, and an LLM scaffolds the Python code.

## Self-Improving Skills

Agents learn continuously from both successes and failures via a structured skills system:

| Category | Trigger | What it captures |
|---|---|---|
| `learning` | Task succeeds | Reusable workflow knowledge (libraries, APIs, techniques) |
| `error_pattern` | Task fails | Recurring failure patterns with avoidance strategies |
| `correction` | Retry succeeds after failure | What fixed the problem — "When X happens, do Y instead" |
| `best_practice` | Auto-promoted | Learnings seen 3+ times, always injected into prompts |

Skills use a stable `pattern_key` for deduplication — the same type of workflow or error produces the same key, so repeated encounters refine the existing skill instead of creating duplicates. Priority auto-escalates for recurring errors. Promoted skills are highlighted in both the planner system prompt and the agent's task prompt.

Manage skills at `/skills` — filter by agent type and category, toggle active/inactive, edit priority and status, or create manual skills.

### Skill Ontology (Knowledge Graph)

Skills are linked to domain concepts (libraries, APIs, data formats, techniques, anti-patterns) via typed directed edges. When a skill is created, an LLM auto-extracts concepts and creates relations (`uses_tool`, `produces`, `avoids`). The `/skills` page has an **Ontology** tab with:

- Interactive SVG graph visualization (hover to highlight connections)
- Concept management (create, delete, filter by type)
- Relation CRUD with validation (no duplicates, no self-loops)
- Graph API: `GET /skills/ontology/graph` returns `{ nodes, edges }` for visualization

## Error Recovery

When a task fails, a fast LLM triage call classifies the failure:

- **Retry** — transient error (timeout, rate limit). Same agent re-runs with failure context in the prompt.
- **Recovery** — deterministic failure (wrong approach, missing capability). A recovery sub-action is spawned with its own re-planned DAG.

Up to 3 attempts, each independently triaged. Every attempt is recorded as an `AgentIteration` with strategy, duration, and outcome.

## LLM Support

Works with OpenAI, Anthropic, Google, and DeepSeek models. Configure API keys in `backend/.env`:

```env
OPENAI_API_KEY=sk-...           # required (planner uses structured output)
ANTHROPIC_API_KEY=sk-ant-...    # optional
GOOGLE_API_KEY=...              # optional
DEEPSEEK_API_KEY=sk-...         # optional
```

Per-task model overrides in the task editor. Per-agent-type defaults with graceful fallback when a key is missing.

## Stack

| | |
|---|---|
| **Frontend** | Next.js 16, TypeScript, Tailwind v4, ShadCN, TanStack Query, Zustand |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), SQLite |
| **Real-time** | Server-Sent Events (per-action streams, snapshot on connect) |
| **Execution** | Single-process async DAG executor |

## Project Layout

```
backend/
  app/
    main.py                        # FastAPI app + lifespan
    models/                        # SQLAlchemy models (Action, Task, Artifact, Log, AgentIteration, ...)
    routers/                       # REST endpoints (actions, tasks, artifacts, agents, planner config)
    services/
      planner.py                   # LLM DAG planner (OpenAI structured output)
      executor.py                  # DAG executor with LLM-triaged recovery
      llm_client.py                # Multi-provider LLM client
      event_bus.py                 # In-process pub/sub for SSE
      code_runner.py               # Sandboxed Python subprocess
      worktree_manager.py          # Git worktree lifecycle (coding agent)
      pause_manager.py             # Task pause/resume
      agents/
        base.py                    # Abstract BaseAgent
        code_execution_agent.py    # Sandbox code agent
        coding_agent.py            # Agentic coding loop
        data_retrieval_agent.py    # Web data agent
        spreadsheet_agent.py       # Excel generation
        report_agent.py            # Report writer
        arxiv_search_agent.py      # arXiv RAG
        general_agent.py           # Chain-of-thought
        sub_action_agent.py        # Child workflow
        agent_memory.py            # Persistent failure lessons
        agent_skills.py            # Self-improving skills (learning/error/correction/promotion)
        registry.py                # Agent factory

frontend/
  src/
    app/                           # Next.js pages (actions, agents, skills, planner)
    components/workspace/          # TaskBoard, TaskCard, TaskCardEditor
    hooks/                         # TanStack Query + SSE event handler
    stores/                        # Zustand (real-time state overlay)
    lib/api/                       # API client
```

## Key URLs

| Path | What |
|---|---|
| `/` | Action list |
| `/actions/:id` | Workspace — live DAG, logs, artifacts |
| `/agents` | Agent Studio |
| `/skills` | Self-improving skills manager |
| `/planner` | Planner config + test sandbox |
