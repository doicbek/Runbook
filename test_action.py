"""
Test loop: create action → run → stream events → report results.
Run with: python test_action.py
"""
import asyncio
import json
import httpx
import sys

BASE = "http://localhost:8001"
PROMPT = "Plot the daily temperature in San Jose in the year 2023"


async def create_action() -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/actions", json={"root_prompt": PROMPT, "title": "Temp Test"})
        r.raise_for_status()
        return r.json()


async def run_action(action_id: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/actions/{action_id}/run")
        r.raise_for_status()


async def get_action(action_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/actions/{action_id}")
        r.raise_for_status()
        return r.json()


async def get_logs(action_id: str, task_id: str) -> list:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/actions/{action_id}/tasks/{task_id}/logs")
        r.raise_for_status()
        return r.json()


async def poll_until_done(action_id: str, timeout_s: int = 300, interval: float = 3.0):
    """Poll action status until all tasks complete or timeout. More resilient than SSE."""
    print(f"\n{'='*60}")
    print(f"Polling action {action_id[:8]}... (every {interval}s, timeout {timeout_s}s)")
    print(f"{'='*60}\n")

    seen_statuses: dict[str, str] = {}
    seen_logs: dict[str, int] = {}
    start = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > timeout_s:
            print(f"\n⏱  Timed out after {timeout_s}s")
            break

        action = await get_action(action_id)
        tasks = action.get("tasks", [])

        # Print new log lines for each task
        for t in tasks:
            tid = t["id"]
            try:
                logs = await get_logs(action_id, tid)
            except Exception:
                logs = []
            prev = seen_logs.get(tid, 0)
            for log in logs[prev:]:
                lvl = log.get("level", "info").upper()
                msg = log.get("message", "")
                sym = "❌" if lvl == "ERROR" else "⚠️ " if lvl == "WARN" else "  "
                atype = t.get("agent_type", "?")
                print(f"  {sym}[{tid[:8]}|{atype}] {msg}")
            seen_logs[tid] = len(logs)

            # Print status change
            new_status = t.get("status", "?")
            if seen_statuses.get(tid) != new_status:
                sym = "▶" if new_status == "running" else "✅" if new_status == "completed" else "❌" if new_status == "failed" else "·"
                print(f"\n{sym} [{tid[:8]}] {t.get('agent_type'):20s} → {new_status}\n")
                seen_statuses[tid] = new_status

        # Done?
        action_status = action.get("status")
        terminal_task_statuses = {"completed", "failed"}
        all_done = all(t.get("status") in terminal_task_statuses for t in tasks)

        if action_status in ("completed", "failed") or (tasks and all_done):
            sym = "🎉" if action_status == "completed" else "💥"
            print(f"\n{sym} Action {action_status or '(all tasks done)'}")
            break

        await asyncio.sleep(interval)

    action = await get_action(action_id)
    return action


async def print_full_logs(action_id: str, tasks: list):
    """Print full logs for any failed tasks."""
    for t in tasks:
        if t.get("status") == "failed":
            print(f"\n{'─'*60}")
            print(f"Full logs for FAILED task [{t['id'][:8]}] ({t.get('agent_type')}):")
            print(f"{'─'*60}")
            logs = await get_logs(action_id, t["id"])
            for log in logs:
                lvl = log.get("level", "info").upper()
                msg = log.get("message", "")
                print(f"  [{lvl}] {msg}")


async def main():
    # 1. Create action
    print(f"Creating action: {PROMPT!r}")
    action = await create_action()
    action_id = action["id"]
    tasks = action.get("tasks", [])
    print(f"Action ID: {action_id}")
    print(f"Planned {len(tasks)} task(s):")
    for t in tasks:
        print(f"  [{t['id'][:8]}] agent={t.get('agent_type'):20s}  deps={t.get('dependencies', [])}")
    print()

    # 2. Run
    print("Starting execution...")
    await run_action(action_id)

    # 3. Poll until done
    final = await poll_until_done(action_id, timeout_s=300)
    final_tasks = final.get("tasks", [])

    # 4. Summary
    print(f"\n{'='*60}")
    print("Final state:")
    for t in final_tasks:
        tid = t["id"][:8]
        status = t.get("status", "?")
        atype = t.get("agent_type", "?")
        summary = (t.get("output_summary") or "")[:150]
        print(f"  [{tid}] {atype:20s}  {status:10s}  {summary!r}")

    all_ok = all(t.get("status") == "completed" for t in final_tasks)
    print(f"\n{'='*60}")
    print(f"Result: {'✅ ALL PASSED' if all_ok else '❌ SOME TASKS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
