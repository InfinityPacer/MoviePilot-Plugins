"""形象编辑只保存活动参数，并保留其他配置与管理员边界。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.plugins.agentpets import AgentPets, SaveSettingsRequest, require_admin


def editor(config=None):
    plugin = AgentPets()
    config = config or {"enabled": True, "scale": 1, "speed": 1, "roam": "floor", "future_option": {"keep": 1}}
    stored = deepcopy(config)
    plugin.init_plugin(config)
    plugin.get_config = lambda: deepcopy(stored)
    plugin.get_data = lambda key=None: None

    def persist(values):
        stored.clear()
        stored.update(deepcopy(values))
        return True

    plugin.update_config = persist
    return plugin, stored


def test_editor_returns_only_public_state_and_both_builtin_modes():
    plugin, _ = editor()
    result = plugin.api_editor()
    assert result.success
    assert set(result.data) == {"enabled", "settings", "pets"}
    assert [(pet["key"], pet["mode"], pet["builtin"]) for pet in result.data["pets"]] == [
        ("ying", "stage", True), ("projector-cat", "renderer", True),
    ]
    assert "future_option" not in result.data


def test_save_merges_latest_config_and_leaves_enable_and_unknown_options_untouched():
    plugin, stored = editor()
    stored["future_option"]["keep"] = 2
    result = plugin.api_save_settings(SaveSettingsRequest(scale=1.25, speed=0.8, roam="free"))
    assert result.success
    assert plugin.settings() == result.data == {"scale": 1.25, "speed": 0.8, "roam": "free"}
    assert stored == {"enabled": True, **result.data, "future_option": {"keep": 2}}


def test_save_does_not_enable_a_disabled_plugin():
    plugin, stored = editor({"enabled": False, "scale": 1, "speed": 1, "roam": "floor"})
    assert plugin.api_save_settings(SaveSettingsRequest(scale=1.2, speed=1, roam="free")).success
    assert not stored["enabled"] and not plugin.get_state()


@pytest.mark.parametrize("failure", ["write", "readback"])
def test_failed_persistence_keeps_runtime_parameters(failure):
    plugin, _ = editor()
    before = plugin.settings()
    plugin.update_config = lambda value: failure != "write"
    response = plugin.api_save_settings(SaveSettingsRequest(scale=1.3, speed=1.5, roam="free"))
    assert not response.success
    assert plugin.settings() == before


@pytest.mark.parametrize("change", [
    {"scale": 0.1}, {"scale": float("inf")}, {"speed": 3}, {"speed": float("nan")},
    {"roam": "outside"}, {"enabled": False}, {"AI_AGENT_PET": "another:pet"},
])
def test_edit_request_rejects_invalid_values_and_unrelated_fields(change):
    with pytest.raises(ValidationError):
        SaveSettingsRequest(**{"scale": 1, "speed": 1, "roam": "floor", **change})


def test_edit_route_requires_admin_and_read_route_only_requires_login():
    plugin, _ = editor()
    routes = {(item["path"], item["methods"][0]): item for item in plugin.get_api()}
    assert routes[("/settings", "POST")]["dependencies"][0].dependency is require_admin
    assert routes[("/editor", "GET")]["auth"] == "bear"
    assert "dependencies" not in routes[("/editor", "GET")]
    with pytest.raises(HTTPException) as denied:
        require_admin(SimpleNamespace(super_user=False))
    assert denied.value.status_code == 403


def test_built_preview_does_not_export_raw_vue_sources():
    """动态素材路径不能被 Vite 展开成源码 glob。"""
    from pathlib import Path

    dist = Path(__file__).parents[3] / "plugins.v3" / "agentpets" / "frontend" / "dist" / "assets"
    assert not list(dist.glob("*.vue"))
