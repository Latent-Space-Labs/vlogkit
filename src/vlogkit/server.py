"""Upload server for vlogkit companion app."""

from __future__ import annotations

import hashlib
import shutil
import socket
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .project import Project, file_hash

CHUNK_SIZE = 1024 * 1024  # 1MB


def create_app(project: Project) -> FastAPI:
    app = FastAPI(title="vlogkit upload server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    tmp_dir = project.cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/health")
    def health():
        clips = project.scan_clips()
        return {
            "status": "ok",
            "project": str(project.root),
            "clips": len(clips),
        }

    @app.get("/clips")
    def list_clips():
        clips = project.scan_clips()
        return [
            {"name": c.name, "size": c.stat().st_size}
            for c in clips
        ]

    @app.post("/upload")
    async def upload(
        file: UploadFile = File(...),
        x_sha256: str | None = Header(None),
    ):
        filename = file.filename or "upload.mp4"

        # Stream to temp file, computing hash as we go
        h = hashlib.sha256()
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir)
        total_bytes = 0
        try:
            with open(fd, "wb") as tmp_f:
                while chunk := await file.read(CHUNK_SIZE):
                    tmp_f.write(chunk)
                    h.update(chunk)
                    total_bytes += len(chunk)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        computed_hash = h.hexdigest()

        # Verify hash if provided
        if x_sha256 and x_sha256.lower() != computed_hash:
            Path(tmp_path).unlink(missing_ok=True)
            return JSONResponse(
                status_code=400,
                content={
                    "error": "hash_mismatch",
                    "expected": x_sha256.lower(),
                    "computed": computed_hash,
                },
            )

        # Resolve destination, handling duplicates
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
            "size": total_bytes,
            "sha256": computed_hash,
        }

    return app


def get_lan_ip() -> str:
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_server(project: Project, host: str = "0.0.0.0", port: int = 8420):
    """Start the upload server with QR code display."""
    import uvicorn
    from rich.console import Console

    console = Console()
    lan_ip = get_lan_ip()
    url = f"http://{lan_ip}:{port}"

    console.print(f"\n[bold green]vlogkit upload server[/]")
    console.print(f"Project: {project.root}")
    console.print(f"Listening on: {url}\n")

    # Show QR code if qrcode is available
    try:
        import qrcode  # type: ignore
        qr = qrcode.QRCode(box_size=1, border=1)
        qr.add_data(url)
        qr.make()
        qr.print_ascii(invert=True)
        console.print()
    except ImportError:
        console.print(f"[dim](install qrcode for QR display: pip install qrcode)[/]\n")

    app = create_app(project)
    uvicorn.run(app, host=host, port=port, log_level="info")
