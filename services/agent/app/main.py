from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from secrets import compare_digest
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from loguru import logger

from app.config import get_settings
from app.models import Workspace
from app.voice.sessions import StartVoice, VoiceConnection, VoiceSessions, VoiceState

# Provider debug logs can include conversation content. Keep them out of app logs.
logger.disable("pipecat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.voice = VoiceSessions(get_settings())
    yield
    await app.state.voice.close()


app = FastAPI(title="Riverline Agent API", version="0.1.0", lifespan=lifespan)


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
    return Workspace(
        window_start=start,
        window_end_exclusive=start + timedelta(days=30),
        voice_available=get_settings().voice_ready,
    )


@app.post("/v1/voice/start", response_model=VoiceConnection, operation_id="start_voice")
async def start_voice(
    body: StartVoice,
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_service)],
) -> VoiceConnection:
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.voice.start(user_id, body.request_id)


@app.get("/v1/voice/{session_id}", response_model=VoiceState, operation_id="get_voice")
async def get_voice(
    session_id: str, request: Request, user_id: Annotated[str, Depends(require_service)]
) -> VoiceState:
    return request.app.state.voice.get(user_id, session_id).state()


@app.post("/v1/voice/{session_id}/end", response_model=VoiceState, operation_id="end_voice")
async def end_voice(
    session_id: str, request: Request, user_id: Annotated[str, Depends(require_service)]
) -> VoiceState:
    return await request.app.state.voice.end(user_id, session_id)
