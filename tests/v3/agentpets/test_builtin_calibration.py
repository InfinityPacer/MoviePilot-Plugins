"""Exercise built-in calibration persistence without touching the live host."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.packs.constants import BUILTIN_PACK_IDS
from app.plugins.agentpets.packs.schema import parse_calibration
from app.plugins.agentpets.requests import CalibrationData, SaveCalibrationRequest

KEYS = ("ying", *BUILTIN_PACK_IDS)


@pytest.fixture(name="editor")
def editor_fixture(tmp_path):
    """Create isolated config and data callbacks without touching the live host."""
    config = {
        "enabled": True, "scale": 1.5, "speed": 1.2, "roam": "surfaces",
        "pet_settings": {"ying": {"scale": 0.8, "speed": 1.1}},
        "future": {"keep": 1},
    }
    data = {}
    plugin = AgentPets()
    plugin.get_config = lambda: deepcopy(config)
    plugin.get_data = lambda key: deepcopy(data.get(key))
    plugin.get_data_path = lambda: tmp_path

    def persist(value):
        """Simulate durable plugin config storage and return its success flag."""
        config.clear()
        config.update(deepcopy(value))
        return True

    plugin.update_config = persist
    plugin.init_plugin(deepcopy(config))
    return plugin, config, data


def change(plugin, key, offset=0.01):
    """Build a small edit against the currently persisted calibration."""
    current = plugin.api_builtin_calibration(key).data.calibration
    return SaveCalibrationRequest(
        id=key, expected_calibration=current,
        calibration={**current, "offset_x": current["offset_x"] + offset},
    )


@pytest.mark.parametrize("key", KEYS)
def test_builtin_save_reopen_reset_is_instance_scoped_and_preserves_assets(editor, key):
    """All built-ins retain their art, settings and mode through calibration."""
    plugin, config, data = editor
    before = deepcopy(config)
    defaults = plugin.api_builtin_calibration(key)
    assert defaults.success
    assert config == before
    original = deepcopy(plugin.builtin_pack(key)) if key != "ying" else None
    request = change(plugin, key)
    result = plugin.api_save_calibration(request)
    assert result.success and result.data.calibration == request.calibration
    assert config == {**before, "builtin_calibrations": {key: request.calibration}}
    assert data == {}
    plugin.init_plugin(deepcopy(config))
    assert plugin.api_builtin_calibration(key).data == result.data
    if original:
        assert plugin.builtin_pack(key) == original
        assert plugin.api_pack(key).data["pack"]["calibration"] == request.calibration
    pet = next(pet for pet in plugin.api_editor().data["pets"] if pet["key"] == key)
    assert pet["mode"] == ("renderer" if key == "projector-cat" else "stage")
    assert pet["builtin"]
    reset = plugin.api_save_calibration(SaveCalibrationRequest(
        id=key, expected_calibration=request.calibration,
        calibration=defaults.data.calibration,
    ))
    assert reset.success
    assert config["builtin_calibrations"] == {}
    assert plugin.api_builtin_calibration(key).data == defaults.data
    assert data == {}


def test_defaults_do_not_write_config_and_instances_do_not_share_calibration(editor, monkeypatch):
    """Default reads are side-effect free and overrides cannot cross instances."""
    plugin, config, _ = editor
    old = deepcopy(config)
    monkeypatch.setattr(
        plugin, "update_config", lambda _: pytest.fail("read/defaults must not persist"))
    for key in KEYS:
        value = plugin.api_builtin_calibration(key).data.calibration
        assert plugin.api_save_calibration(SaveCalibrationRequest(
            id=key, expected_calibration=value, calibration=value,
        )).success
    assert config == old
    config["builtin_calibrations"] = {"ying": parse_calibration({"eye_x": 0.45, "eye_y": 0.35})}
    other = AgentPets()
    other.get_config = dict
    assert other.api_builtin_calibration("ying").data.calibration["eye_x"] == 0.5
    assert plugin.api_builtin_calibration("ying").data.calibration["eye_x"] == 0.45


def test_concurrent_saves_merge_distinct_pets_and_reject_stale_same_pet(editor):
    """Serialize writes while preserving unrelated Pets and stale-write guards."""
    plugin, config, _ = editor
    requests = [change(plugin, key) for key in KEYS]
    with ThreadPoolExecutor(max_workers=5) as pool:
        assert all(result.success for result in pool.map(plugin.api_save_calibration, requests))
    assert set(config["builtin_calibrations"]) == set(KEYS)
    before = deepcopy(config)
    stale = plugin.api_save_calibration(requests[0])
    assert not stale.success and "其他页面" in stale.message
    assert config == before


@pytest.mark.parametrize("phase", ["read", "write", "readback", "mismatch", "false"])
def test_builtin_failures_are_not_reported_as_success(editor, phase, monkeypatch):
    """Read, write and readback failures must not become successful saves."""
    plugin, config, _ = editor
    request = change(plugin, "ying")
    before = deepcopy(config)
    calls = 0

    def read():
        """Inject a failure at the selected config read stage."""
        nonlocal calls
        calls += 1
        if phase == "read" or (phase == "readback" and calls == 2):
            raise OSError("simulated read failure")
        return deepcopy(config)

    def persist(_value):
        """Simulate rejected, failed and non-durable storage writes."""
        if phase == "write":
            raise RuntimeError("simulated write failure")
        return phase != "false"

    monkeypatch.setattr(plugin, "get_config", read)
    monkeypatch.setattr(plugin, "update_config", persist)
    assert not plugin.api_save_calibration(request).success
    assert config == before


@pytest.mark.parametrize("value", [{"left": 0.95}, {"eye_x": 0.5}, {"offset_x": 0.3}, {"extra": 1}])
def test_invalid_calibration_is_rejected_before_any_write(editor, value):
    """Keep invalid geometry and unsupported fields out of persisted overrides."""
    plugin, config, _ = editor
    before = deepcopy(config)
    request = change(plugin, "ying")
    request.calibration = value
    assert not plugin.api_save_calibration(request).success
    assert config == before


def test_read_contract_and_admin_only_write_are_registered(editor):
    """Keep the lightweight GET authenticated and the mutation admin-only."""
    plugin, _, _ = editor
    routes = [route for route in plugin.get_api() if route["path"] == "/packs/calibration"]
    assert {tuple(route["methods"]) for route in routes} == {("GET",), ("POST",)}
    for route in routes:
        assert route["auth"] == "bear" and route["response_model"]
        assert bool(route.get("dependencies")) == (route["methods"] == ["POST"])
        response = (plugin.api_builtin_calibration("ying") if route["methods"] == ["GET"]
                    else plugin.api_save_calibration(change(plugin, "ying")))
        payload = response.model_dump(mode="json")
        assert set(payload) == {"success", "message", "data"}
        assert route["response_model"].model_validate(payload).model_dump(mode="json") == payload
        assert isinstance(response.data, CalibrationData)
        assert set(payload["data"]) == {"id", "calibration"}
    assert not plugin.api_builtin_calibration("missing").success
    assert not plugin.api_builtin_calibration("../ying").success
