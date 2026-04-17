"""Bearer-token auth dependency."""
from __future__ import annotations

from fastapi import Header, HTTPException, Request


async def require_token(
    request: Request,
    authorization: str | None = Header(None),
) -> None:
    expected = request.app.state.token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid_token")
