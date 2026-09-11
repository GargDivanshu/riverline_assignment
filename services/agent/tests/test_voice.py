import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.voice.sessions import VoiceSessions


def settings():
    return Settings(
        internal_api_secret="a" * 32,
        daily_api_key="test",
        elevenlabs_api_key="test",
        openrouter_api_key="test",
        voice_max_sessions=1,
    )


async def waiting(session, config):
    session.status = "active"
    await asyncio.Event().wait()


def make_manager(pipeline=waiting, fail_tokens=False):
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("meeting-tokens"):
            return httpx.Response(503 if fail_tokens else 200, json={"token": "test-token"})
        return httpx.Response(200, json={"url": "https://test.daily.co/test"})

    client = httpx.AsyncClient(
        base_url="https://api.daily.co/v1/", transport=httpx.MockTransport(respond)
    )
    return VoiceSessions(settings(), pipeline, client), calls


def test_repeated_concurrent_start_creates_one_room_and_enforces_ownership():
    async def scenario():
        manager, calls = make_manager()
        request_id = uuid4()
        first, second = await asyncio.gather(
            manager.start("a", request_id), manager.start("a", request_id)
        )
        assert first.session_id == second.session_id
        assert calls.count(("POST", "/v1/rooms")) == 1
        with pytest.raises(HTTPException) as error:
            manager.get("b", first.session_id)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            await manager.end("b", first.session_id)
        assert error.value.status_code == 404
        await manager.close()

    asyncio.run(scenario())


def test_capacity_and_end_release_resources_without_replaying_old_call():
    async def scenario():
        manager, calls = make_manager()
        request_id = uuid4()
        call = await manager.start("a", request_id)
        with pytest.raises(HTTPException) as error:
            await manager.start("b", uuid4())
        assert error.value.status_code == 429
        result = await manager.end("a", call.session_id)
        assert result.status == "ended"
        assert any(method == "DELETE" for method, _ in calls)
        with pytest.raises(HTTPException) as error:
            await manager.start("a", request_id)
        assert error.value.status_code == 409
        await manager.start("b", uuid4())
        await manager.close()

    asyncio.run(scenario())


def test_partial_room_setup_failure_deletes_room_and_returns_no_token():
    async def scenario():
        manager, calls = make_manager(fail_tokens=True)
        with pytest.raises(HTTPException) as error:
            await manager.start("a", uuid4())
        assert error.value.status_code == 502
        assert not manager.sessions
        assert calls[-1][0] == "DELETE"
        await manager.close()

    asyncio.run(scenario())


def test_pipeline_failure_is_visible_and_does_not_leak_provider_error():
    async def broken(session, config):
        raise RuntimeError("provider-private-debug-detail")

    async def scenario():
        manager, calls = make_manager(pipeline=broken)
        connection = await manager.start("a", uuid4())
        session = manager.get("a", connection.session_id)
        await session.worker
        assert session.status == "failed"
        assert "provider-private" not in session.error
        assert calls[-1][0] == "DELETE"
        await manager.close()

    asyncio.run(scenario())
