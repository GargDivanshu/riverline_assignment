"""Bounded, owner-scoped live sessions for a single-process local backend."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import httpx
from loguru import logger
from pydantic import BaseModel

from app.config import Settings
from app.errors import (
    VOICE_ALREADY_ACTIVE,
    VOICE_CAPACITY,
    VOICE_ENDED,
    VOICE_NOT_CONFIGURED,
    VOICE_SESSION_NOT_FOUND,
    PublicError,
    classify_voice_error,
    log_voice_error,
)


class StartVoice(BaseModel):
    request_id: UUID


class VoiceState(BaseModel):
    session_id: str
    status: Literal["starting", "active", "ended", "failed"]
    error: str | None = None
    error_code: str | None = None
    retryable: bool = False


class VoiceConnection(VoiceState):
    room_url: str
    token: str
    expires_at: int


@dataclass
class Session:
    id: str
    owner: str
    room_url: str
    room_name: str
    token: str = field(repr=False)
    bot_token: str = field(repr=False)
    expires_at: int
    status: str = "starting"
    error: str | None = None
    error_code: str | None = None
    retryable: bool = False
    pipeline: Any = field(default=None, repr=False)
    worker: asyncio.Task | None = field(default=None, repr=False)
    created_monotonic: float = field(default_factory=time.monotonic, repr=False)

    def state(self) -> VoiceState:
        return VoiceState(
            session_id=self.id,
            status=self.status,
            error=self.error,
            error_code=self.error_code,
            retryable=self.retryable,
        )

    def fail(self, public: PublicError) -> None:
        self.status = "failed"
        self.error = public.message
        self.error_code = public.code
        self.retryable = public.retryable

    def connection(self) -> VoiceConnection:
        return VoiceConnection(
            **self.state().model_dump(),
            room_url=self.room_url,
            token=self.token,
            expires_at=self.expires_at,
        )


class VoiceSessions:
    def __init__(self, settings: Settings, run_pipeline=None, client=None):
        self.settings = settings
        self.sessions: dict[str, Session] = {}
        self.lock = asyncio.Lock()
        self.client = client or httpx.AsyncClient(
            base_url="https://api.daily.co/v1/",
            timeout=10,
            headers={"Authorization": f"Bearer {settings.daily_api_key}"},
        )
        self.run_pipeline = run_pipeline

    async def start(self, owner: str, request_id: UUID) -> VoiceConnection:
        if not self.settings.voice_ready:
            raise VOICE_NOT_CONFIGURED.as_http_exception()
        async with self.lock:
            sid = str(request_id)
            existing = self.sessions.get(sid)
            if existing:
                if existing.owner != owner:
                    raise VOICE_SESSION_NOT_FOUND.as_http_exception()
                if existing.status in ("starting", "active"):
                    return existing.connection()
                raise VOICE_ENDED.as_http_exception()
            active = [s for s in self.sessions.values() if s.status in ("starting", "active")]
            if any(s.owner == owner for s in active):
                raise VOICE_ALREADY_ACTIVE.as_http_exception()
            if len(active) >= self.settings.voice_max_sessions:
                raise VOICE_CAPACITY.as_http_exception()
            now = int(time.time())
            started = time.monotonic()
            self.sessions = {k: s for k, s in self.sessions.items() if s.expires_at > now}
            expires = now + self.settings.voice_max_seconds
            room_name = "riverline-" + sid
            try:
                response = await self.client.post(
                    "rooms",
                    json={
                        "name": room_name,
                        "privacy": "private",
                        "properties": {
                            "exp": expires,
                            "eject_at_room_exp": True,
                            "max_participants": 2,
                            "start_video_off": True,
                            "enable_screenshare": False,
                        },
                    },
                )
                response.raise_for_status()
                room_url = response.json()["url"]
                tokens = []
                for identity in ("user", "riverline-bot"):
                    token_response = await self.client.post(
                        "meeting-tokens",
                        json={
                            "properties": {
                                "room_name": room_name,
                                "exp": expires,
                                "eject_at_token_exp": True,
                                "is_owner": False,
                                "user_id": identity,
                                "start_video_off": True,
                            }
                        },
                    )
                    token_response.raise_for_status()
                    tokens.append(token_response.json()["token"])
            except (httpx.HTTPError, ValueError, KeyError) as error:
                await self.delete_room(room_name)
                public = classify_voice_error(error, source="daily")
                log_voice_error(public, error)
                raise public.as_http_exception() from None
            session = Session(
                sid, owner, room_url, room_name, tokens[0], tokens[1], expires, created_monotonic=started
            )
            self.sessions[sid] = session
            session.worker = asyncio.create_task(self.run(session))
            logger.info("voice_session_created session_id={} room_setup_ms={}", sid, int((time.monotonic() - session.created_monotonic) * 1000))
            return session.connection()

    def get(self, owner: str, sid: str) -> Session:
        session = self.sessions.get(sid)
        if not session or session.owner != owner:
            raise VOICE_SESSION_NOT_FOUND.as_http_exception()
        return session

    async def run(self, session: Session):
        logger.info("voice_pipeline_starting session_id={}", session.id)
        try:
            if self.run_pipeline is None:
                from app.voice.pipeline import run_cascade

                self.run_pipeline = run_cascade
            async with asyncio.timeout(self.settings.voice_max_seconds):
                await self.run_pipeline(session, self.settings)
        except asyncio.CancelledError:
            pass
        except Exception as error:  # noqa: BLE001 - isolate provider failures without logging secrets/audio
            public = classify_voice_error(error)
            log_voice_error(public, error, session_id=session.id)
            session.fail(public)
        finally:
            if session.status != "failed":
                session.status = "ended"
            await self.delete_room(session.room_name)
            logger.info(
                "voice_pipeline_finished session_id={} status={} elapsed_ms={}",
                session.id,
                session.status,
                int((time.monotonic() - session.created_monotonic) * 1000),
            )

    async def delete_room(self, room_name: str):
        # Daily expiry remains the backstop if cleanup cannot reach the provider.
        try:
            await self.client.delete("rooms/" + room_name)
        except httpx.HTTPError as error:
            public = classify_voice_error(error, source="daily")
            log_voice_error(public, error)

    async def end(self, owner: str, sid: str) -> VoiceState:
        session = self.get(owner, sid)
        logger.info("voice_session_end_requested session_id={}", sid)
        if session.worker and not session.worker.done():
            if session.pipeline:
                await session.pipeline.cancel()
            session.worker.cancel()
            await asyncio.gather(session.worker, return_exceptions=True)
        if session.status != "failed":
            session.status = "ended"
        await self.delete_room(session.room_name)
        return session.state()

    async def close(self):
        await asyncio.gather(*(self.end(s.owner, s.id) for s in list(self.sessions.values())))
        await self.client.aclose()
