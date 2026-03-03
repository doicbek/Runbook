import difflib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Artifact, ArtifactVersion
from app.schemas.task import ArtifactResponse, ArtifactVersionResponse

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.get("/{artifact_id}/content")
async def get_artifact_content(artifact_id: str, db: AsyncSession = Depends(get_db)):
    """Serve the actual artifact file content with proper Content-Type."""
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if not artifact.storage_path:
        raise HTTPException(status_code=404, detail="Artifact has no stored file")

    file_path = Path(artifact.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type=artifact.mime_type or "application/octet-stream",
        filename=file_path.name,
    )


@router.get("/{artifact_id}/versions", response_model=list[ArtifactVersionResponse])
async def list_artifact_versions(artifact_id: str, db: AsyncSession = Depends(get_db)):
    """List all versions of an artifact."""
    # Verify artifact exists
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version.asc())
    )
    versions = result.scalars().all()
    return versions


@router.get("/{artifact_id}/versions/{version}/content")
async def get_artifact_version_content(
    artifact_id: str, version: int, db: AsyncSession = Depends(get_db)
):
    """Serve a specific version's file content."""
    result = await db.execute(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == version,
        )
    )
    ver = result.scalar_one_or_none()
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    file_path = Path(ver.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Version file not found on disk")

    # Get parent artifact for mime_type
    art_result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = art_result.scalar_one_or_none()
    mime = artifact.mime_type if artifact else None

    return FileResponse(
        path=str(file_path),
        media_type=mime or "application/octet-stream",
        filename=file_path.name,
    )


_TEXT_MIME_PREFIXES = ("text/", "application/json")


@router.get("/{artifact_id}/diff")
async def get_artifact_diff(
    artifact_id: str,
    v1: int = Query(..., description="First version number"),
    v2: int = Query(..., description="Second version number"),
    db: AsyncSession = Depends(get_db),
):
    """Return a unified diff between two versions of a text artifact."""
    # Verify artifact exists and is a text type
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    mime = artifact.mime_type or ""
    if not any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"Diff is only supported for text artifacts (mime_type: {mime})",
        )

    # Helper to resolve a version — could be a stored version or the current artifact
    async def _read_version(ver_num: int) -> tuple[str, list[str]]:
        """Return (label, lines) for a version number."""
        # Check if this is the current version on the artifact itself
        if ver_num == artifact.current_version:
            path = Path(artifact.storage_path) if artifact.storage_path else None
            if not path or not path.exists():
                raise HTTPException(
                    status_code=404, detail=f"File for current version {ver_num} not found"
                )
            text = path.read_text(errors="replace")
            return f"v{ver_num}", text.splitlines(keepends=True)

        # Otherwise look in ArtifactVersion table
        res = await db.execute(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == artifact_id,
                ArtifactVersion.version == ver_num,
            )
        )
        version_row = res.scalar_one_or_none()
        if not version_row:
            raise HTTPException(status_code=404, detail=f"Version {ver_num} not found")

        path = Path(version_row.storage_path)
        if not path.exists():
            raise HTTPException(
                status_code=404, detail=f"File for version {ver_num} not found on disk"
            )
        text = path.read_text(errors="replace")
        return f"v{ver_num}", text.splitlines(keepends=True)

    label1, lines1 = await _read_version(v1)
    label2, lines2 = await _read_version(v2)

    diff = difflib.unified_diff(lines1, lines2, fromfile=label1, tofile=label2)
    return {"diff": "".join(diff)}
