"""Concrete payload validation without changing the established JSON wire shape."""

from typing import get_args

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import schemas
from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.responses import SettingsData


def test_all_json_routes_have_concrete_payload_models():
    """Every route validates its business payload and preserves error envelopes."""
    for route in AgentPets().get_api():
        model = route["response_model"]
        payload = model.__pydantic_generic_metadata__["args"][0]
        assert payload not in (dict, list)
        assert not (get_args(payload) and get_args(payload)[0] is dict)
        response = model(success=False, message="test failure")
        assert response.model_dump() == {"success": False, "message": "test failure", "data": None}


@pytest.mark.parametrize("change", [
    {"scale": "not-a-number"}, {"roam": "unknown"}, {"unexpected": "field"},
    {"dialogue": {"mode": "invalid", "voice": "neutral"}},
    {"peek_angles": {"bottom": 0, "left": 35}},
])
def test_invalid_settings_payload_is_not_accepted_as_an_arbitrary_dict(change):
    """Wrong field shapes and unknown fields fail before transmission."""
    value = {"scale": 1, "speed": 1, "roam": "floor", "movement": "auto", **change}
    with pytest.raises(ValidationError):
        schemas.Response[SettingsData](success=True, data=value)


def test_optional_settings_stay_absent_and_dictionary_callers_still_work():
    """Validation does not invent optional preferences for old configurations."""
    plugin = AgentPets()
    plugin.init_plugin({"enabled": True})
    result = plugin.api_settings()
    assert isinstance(result.data, dict)
    assert set(result.data) == {"scale", "speed", "roam", "movement"}
    assert "peek_angles" not in result.model_dump()["data"]
    assert "dialogue" not in result.model_dump()["data"]


def test_read_routes_validate_real_http_payloads_and_publish_named_schemas():
    """Actual endpoints round-trip through FastAPI and publish concrete schemas."""
    plugin = AgentPets()
    plugin.init_plugin({"enabled": True})
    plugin.get_config = lambda: {}
    plugin.get_data = lambda *_args, **_kwargs: []
    app = FastAPI()
    wanted = {"/settings", "/editor", "/packs", "/pack", "/markets"}
    for route in plugin.get_api():
        if route["path"] in wanted and route["methods"] == ["GET"]:
            app.add_api_route(route["path"], route["endpoint"], methods=["GET"],
                              response_model=route["response_model"])
    with TestClient(app) as client:
        for path in wanted:
            response = client.get(path)
            assert response.status_code == 200
            assert response.json()["success"] is True
            assert set(response.json()) == {"success", "message", "data"}
        schema = client.get("/openapi.json").json()
    definitions = schema["components"]["schemas"]
    for name in ("SettingsData", "EditorData", "PackSummaryData", "PackPayload", "MarketInfoData"):
        assert name in definitions


def test_http_rejects_malformed_backend_payload_instead_of_sending_success():
    """A broken backend cannot silently send a nominally successful payload."""
    app = FastAPI()
    app.add_api_route("/broken", lambda: {
        "success": True, "message": "", "data": {"scale": "invalid"},
    }, response_model=schemas.Response[SettingsData])
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/broken").status_code == 500
