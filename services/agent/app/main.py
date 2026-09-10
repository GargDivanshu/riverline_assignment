from datetime import datetime, timedelta
from secrets import compare_digest
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException

from app.config import get_settings
from app.models import Workspace

app = FastAPI(title="Riverline Agent API", version="0.1.0")


def require_service(
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    expected = f"Bearer {get_settings().internal_api_secret}"
    if not authorization or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized service")
    if not x_user_id or not 1 <= len(x_user_id) <= 128:
        raise HTTPException(status_code=400, detail="Authenticated user context required")
    return x_user_id


@app.get("/health", operation_id="health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "riverline-agent"}


@app.get("/v1/workspace", response_model=Workspace, operation_id="get_workspace")
def workspace(user_id: Annotated[str, Depends(require_service)]) -> Workspace:
    # Auth is real; financial capture is deliberately not simulated in this foundation.
    # Persistent, user-owned financial sessions replace this empty state next.
    start = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return Workspace(window_start=start, window_end_exclusive=start + timedelta(days=30))


@app.post("/v1/voice/start", operation_id="start_voice")
def start_voice(user_id: Annotated[str, Depends(require_service)]) -> None:
    raise HTTPException(status_code=501, detail="Live voice is not implemented in this foundation")
