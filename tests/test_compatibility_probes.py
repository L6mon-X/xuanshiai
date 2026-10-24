from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_models_available_on_versioned_and_legacy_paths() -> None:
    for path in ("/api/v1/models", "/api/models"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["object"] == "list"
        assert payload["data"]
        assert {"id", "object", "created", "owned_by"} <= payload["data"][0].keys()


def test_status_and_config_are_sanitized_compatibility_metadata() -> None:
    for path in ("/api/v1/status", "/api/status", "/api/v1/config", "/api/config"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["service"]
        assert "api_key" not in payload
        assert "secret" not in payload
