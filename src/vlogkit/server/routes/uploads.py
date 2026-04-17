"""POST /upload — streaming upload with SHA-256 verification."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import JSONResponse

from vlogkit.project import Project
from vlogkit.server.auth import require_token

CHUNK_SIZE = 1024 * 1024  # 1 MB


def create_router(project: Project) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_token)])
    tmp_dir = project.cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    @router.post("/upload")
    async def upload(
        file: UploadFile = File(...),
        x_sha256: str | None = Header(None),
    ):
        filename = file.filename or "upload.mp4"
        h = hashlib.sha256()
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir)
        total = 0
        try:
            with open(fd, "wb") as tmp_f:
                while chunk := await file.read(CHUNK_SIZE):
                    tmp_f.write(chunk)
                    h.update(chunk)
                    total += len(chunk)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        computed = h.hexdigest()
        if x_sha256 and x_sha256.lower() != computed:
            Path(tmp_path).unlink(missing_ok=True)
            return JSONResponse(
                status_code=400,
                content={
                    "error": "hash_mismatch",
                    "expected": x_sha256.lower(),
                    "computed": computed,
                },
            )

        dest = project.root / filename
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                dest = project.root / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.move(tmp_path, dest)
        return {
            "status": "ok",
            "filename": dest.name,
            "size": total,
            "sha256": computed,
        }

    return router
