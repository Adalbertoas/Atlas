from __future__ import annotations


def test_chat_requires_authentication(client):
    response = client.post("/api/v1/chat", json={"message": "hola"})
    assert response.status_code == 401


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/api/v1/auth/login", json={"password": "incorrecta"})
    assert response.status_code == 401


def test_login_with_correct_password_returns_token(client):
    response = client.post("/api/v1/auth/login", json={"password": "test-password"})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_read_only_command_executes_directly(client, auth_headers):
    response = client.post("/api/v1/chat", json={"message": "¿qué hora es?"}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is False
    assert body["reply"]


def test_medium_risk_command_requires_confirmation(client, auth_headers):
    response = client.post("/api/v1/chat", json={"message": "abre notepad"}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is True
    assert body["confirmation_id"]
    assert "notepad" in body["confirmation_description"].lower()


def test_cancelling_a_confirmation_does_not_execute(client, auth_headers):
    chat_response = client.post("/api/v1/chat", json={"message": "abre notepad"}, headers=auth_headers)
    confirmation_id = chat_response.json()["confirmation_id"]

    confirm_response = client.post(
        "/api/v1/chat/confirm",
        json={"confirmation_id": confirmation_id, "approve": False},
        headers=auth_headers,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["reply"] == "Acción cancelada."


def test_create_memory_via_chat_is_low_risk_and_auto_executes(client, auth_headers):
    response = client.post(
        "/api/v1/chat", json={"message": "anota que prefiero reuniones por la mañana"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is False
    assert body["reply"]

    memory_response = client.get("/api/v1/memory", headers=auth_headers)
    assert memory_response.status_code == 200
    assert len(memory_response.json()) == 1


def test_chat_generates_conversation_id_when_not_provided(client, auth_headers):
    response = client.post("/api/v1/chat", json={"message": "hola"}, headers=auth_headers)
    body = response.json()
    assert body["conversation_id"]


def test_chat_reuses_conversation_id_and_persists_history(client, auth_headers):
    first = client.post("/api/v1/chat", json={"message": "hola"}, headers=auth_headers)
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        "/api/v1/chat",
        json={"message": "¿qué hora es?", "conversation_id": conversation_id},
        headers=auth_headers,
    )
    assert second.json()["conversation_id"] == conversation_id


def test_personality_settings_can_be_read_and_updated(client, auth_headers):
    get_response = client.get("/api/v1/settings/personality", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["verbosity"] == "breve"

    put_response = client.put(
        "/api/v1/settings/personality", json={"verbosity": "detallado"}, headers=auth_headers
    )
    assert put_response.status_code == 200
    assert put_response.json()["verbosity"] == "detallado"

    # El cambio persiste.
    get_again = client.get("/api/v1/settings/personality", headers=auth_headers)
    assert get_again.json()["verbosity"] == "detallado"


def test_tools_endpoint_lists_all_base_tools(client, auth_headers):
    response = client.get("/api/v1/tools", headers=auth_headers)
    assert response.status_code == 200
    names = {t["name"] for t in response.json()}
    assert names == {
        "get_system_info",
        "open_application",
        "close_application",
        "list_processes",
        "open_file",
        "control_media",
        "list_files",
        "search_files",
        "get_current_time",
        "create_memory",
        "search_memory",
        "list_devices",
        "set_device_state",
        "control_room",
        "run_routine",
        "analyze_screenshot",
    }


def test_system_status_endpoint_returns_metrics_without_ai_call(client, auth_headers):
    response = client.get("/api/v1/system/status", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert "cpu_percent" in body
    assert "ram_percent" in body


def test_system_health_endpoint_is_public(client):
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
