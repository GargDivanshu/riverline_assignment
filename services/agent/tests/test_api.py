import os
from datetime import date

from fastapi.testclient import TestClient

os.environ["INTERNAL_API_SECRET"] = "test-secret-that-is-at-least-32-characters"

from app.main import app

client = TestClient(app)
headers = {
    "Authorization": f"Bearer {os.environ['INTERNAL_API_SECRET']}",
    "X-User-Id": "test-user-a",
}


def test_workspace_rejects_missing_or_wrong_service_credentials():
    assert client.get("/v1/workspace").status_code == 401
    assert client.get("/v1/workspace", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_workspace_requires_authenticated_user_context():
    assert (
        client.get("/v1/workspace", headers={"Authorization": headers["Authorization"]}).status_code
        == 400
    )


def test_new_workspace_preserves_unknown_cash_and_exact_horizon():
    response = client.get("/v1/workspace", headers=headers)
    assert response.status_code == 200
    state = response.json()
    assert state["opening_cash_paise"] is None
    assert state["income"] == state["commitments"] == state["expenses"] == []
    assert (
        date.fromisoformat(state["window_end_exclusive"])
        - date.fromisoformat(state["window_start"])
    ).days == 30
    assert state["voice_available"] is False


def test_voice_requires_configuration_and_valid_request():
    with TestClient(app) as live_client:
        response = live_client.post(
            "/v1/voice/start",
            headers=headers,
            json={"request_id": "7f974566-a1be-4c66-b451-53844c42d98e"},
        )
        assert response.status_code == 503
        assert (
            live_client.post(
                "/v1/voice/start", headers=headers, json={"request_id": "bad"}
            ).status_code
            == 422
        )
    assert client.post("/v1/voice/start").status_code == 401
