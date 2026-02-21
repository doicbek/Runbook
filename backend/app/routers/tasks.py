from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Action, Artifact, Log, Task, TaskOutput
from app.schemas.task import ArtifactResponse, LogResponse, TaskCreate, TaskResponse, TaskUpdate
from app.services.event_bus import event_bus

router = APIRouter(tags=["tasks"])


class RunCodeRequest(BaseModel):
    code: str | None = None


class CodeExecutionResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    artifacts: list[ArtifactResponse]


@router.post(
    "/actions/{action_id}/tasks",
    response_model=TaskResponse,
    status_code=201,
)
async def create_task(
    action_id: str,
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Validate that all dependency IDs exist within this action
    if body.dependencies:
        result = await db.execute(
            select(Task).where(Task.action_id == action_id, Task.id.in_(body.dependencies))
        )
        found = {t.id for t in result.scalars().all()}
        missing = set(body.dependencies) - found
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown dependency task IDs: {missing}")

    task = Task(
        action_id=action_id,
        prompt=body.prompt,
        agent_type=body.agent_type,
        model=body.model,
        dependencies=body.dependencies,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch(
    "/actions/{action_id}/tasks/{task_id}",
    response_model=TaskResponse,
)
async def update_task(
    action_id: str,
    task_id: str,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    from app.services.executor import invalidate_downstream

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.action_id == action_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.prompt is not None:
        task.prompt = body.prompt
    if body.model is not None:
        task.model = body.model
    if body.agent_type is not None:
        task.agent_type = body.agent_type
    if body.dependencies is not None:
        task.dependencies = body.dependencies

    # Reset this task to pending
    task.status = "pending"
    task.output_summary = None

    # Invalidate downstream tasks
    await invalidate_downstream(task_id, action_id, db)

    await db.commit()
    await db.refresh(task)
    return task


@router.get(
    "/actions/{action_id}/tasks/{task_id}/logs",
    response_model=list[LogResponse],
)
async def get_task_logs(
    action_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.action_id == action_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(Log).where(Log.task_id == task_id).order_by(Log.timestamp)
    )
    return result.scalars().all()


@router.post(
    "/actions/{action_id}/tasks/{task_id}/run-code",
    response_model=CodeExecutionResponse,
)
async def run_task_code(
    action_id: str,
    task_id: str,
    body: RunCodeRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Execute Python code from a task's output or from the request body."""
    from app.services.code_runner import extract_code_blocks, run_code

    # Verify task exists and belongs to action
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.action_id == action_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get code to execute
    if body and body.code:
        code = body.code
    else:
        # Extract from task output
        if not task.output_summary:
            raise HTTPException(status_code=400, detail="Task has no output to extract code from")
        blocks = extract_code_blocks(task.output_summary)
        if not blocks:
            raise HTTPException(status_code=400, detail="No Python code blocks found in task output")
        # Concatenate all Python blocks
        code = "\n\n".join(b["code"] for b in blocks)

    # Publish start event
    await event_bus.publish(action_id, "code.started", {
        "task_id": task_id,
        "action_id": action_id,
    })

    # Log callback that persists and publishes
    async def log_callback(level: str, message: str):
        async with db.begin_nested():
            log = Log(
                task_id=task_id,
                level=level,
                message=message,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(log)
        await db.commit()
        await event_bus.publish(action_id, "code.log", {
            "task_id": task_id,
            "level": level,
            "message": message,
        })

    # Execute the code
    result = await run_code(
        task_id=task_id,
        action_id=action_id,
        code=code,
        log_callback=log_callback,
    )

    # Delete old artifacts for this task (from previous runs)
    old_artifacts = await db.execute(
        select(Artifact).where(Artifact.task_id == task_id)
    )
    for old in old_artifacts.scalars().all():
        await db.delete(old)
    await db.commit()

    # Create artifact records for generated files
    artifacts = []
    for f in result["files"]:
        artifact = Artifact(
            task_id=task_id,
            action_id=action_id,
            type=f["type"],
            mime_type=f["mime_type"],
            storage_path=f["path"],
            size_bytes=f["size"],
        )
        db.add(artifact)
        artifacts.append(artifact)

    await db.commit()
    for a in artifacts:
        await db.refresh(a)

    # Update task output with artifact IDs
    artifact_ids = [a.id for a in artifacts]
    task_output_result = await db.execute(
        select(TaskOutput).where(TaskOutput.task_id == task_id)
    )
    task_output = task_output_result.scalar_one_or_none()
    if task_output:
        task_output.artifact_ids = artifact_ids
        await db.commit()

    # Store stdout/stderr as log entries
    if result["stdout"].strip():
        log = Log(
            task_id=task_id,
            level="info",
            message=f"[code stdout] {result['stdout'][:2000]}",
            timestamp=datetime.now(timezone.utc),
        )
        db.add(log)
    if result["stderr"].strip():
        log = Log(
            task_id=task_id,
            level="error",
            message=f"[code stderr] {result['stderr'][:2000]}",
            timestamp=datetime.now(timezone.utc),
        )
        db.add(log)
    await db.commit()

    # Publish completion event
    if result["exit_code"] == 0:
        await event_bus.publish(action_id, "code.completed", {
            "task_id": task_id,
            "exit_code": result["exit_code"],
            "artifact_ids": artifact_ids,
            "stdout_preview": result["stdout"][:500],
        })
    else:
        await event_bus.publish(action_id, "code.failed", {
            "task_id": task_id,
            "error": result["stderr"][:500],
            "stderr": result["stderr"][:500],
        })

    return CodeExecutionResponse(
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        artifacts=artifacts,
    )
