"""Range-aware file streaming for /media."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse an HTTP Range header (only `bytes=X-Y` / `bytes=X-`)."""
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="invalid_range")
    spec = range_header.removeprefix("bytes=")
    start_s, _, end_s = spec.partition("-")
    try:
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
    except ValueError:
        raise HTTPException(status_code=416, detail="invalid_range")
    if start > end or end >= file_size:
        raise HTTPException(status_code=416, detail="range_out_of_bounds")
    return start, end


def stream_file(request: Request, path: Path):
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media_not_found")
    size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    if range_header is None:
        return FileResponse(
            path,
            media_type=mime,
            headers={"Accept-Ranges": "bytes"},
        )

    start, end = _parse_range(range_header, size)
    length = end - start + 1

    def iter_bytes():
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_bytes(),
        status_code=206,
        media_type=mime,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
        },
    )
