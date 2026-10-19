"""形象编辑只保存活动参数，并保留其他配置与管理员边界。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.plugins.agentpets import AgentPets, require_admin
from app.plugins.agentpets.packs.constants import BUILTIN_STAGE_PACKS
from app.plugins.agentpets.requests import SaveSettingsRequest


def editor(config=None):
    """建立配置保存在内存且素材为空的实例，模拟未知配置字段的并存"""
    plugin = AgentPets()
    config = config or {"enabled": True, "scale": 1, "speed": 1, "roam": "floor", "future_option": {"keep": 1}}
    stored = deepcopy(config)
    plugin.init_plugin(config)
    plugin.get_config = lambda: deepcopy(stored)
    plugin.get_data = lambda key=None: None

    def persist(values):
        """以深拷贝替换内存配置，模拟一次成功持久化"""
        stored.clear()
        stored.update(deepcopy(values))
        return True

    plugin.update_config = persist
    return plugin, stored


def test_editor_returns_only_public_state_and_both_builtin_modes():
    """编辑接口只暴露必要设置和两类内置形象，不泄露未知配置"""
    plugin, _ = editor()
    result = plugin.api_editor()
    assert result.success
    assert set(result.data) == {"enabled", "settings", "pets", "pet_settings"}
    assert [(pet["key"], pet["mode"], pet["builtin"]) for pet in result.data["pets"]] == [
        ("ying", "stage", True), ("projector-cat", "renderer", True),
        *((key, "stage", True) for key in BUILTIN_STAGE_PACKS),
    ]
    assert "future_option" not in result.data


def test_save_merges_latest_config_and_leaves_enable_and_unknown_options_untouched():
    """保存时合并最新配置，保留开关及其他页面更新的未知字段"""
    plugin, stored = editor()
    stored["future_option"]["keep"] = 2
    result = plugin.api_save_settings(SaveSettingsRequest(scale=1.25, speed=0.8, roam="free"))
    assert result.success
    assert plugin.settings() == result.data == {"scale": 1.25, "speed": 0.8, "roam": "free", "movement": "auto"}
    assert stored == {"enabled": True, **result.data, "future_option": {"keep": 2}}


def test_save_does_not_enable_a_disabled_plugin():
    """调整活动参数不得意外启用已停用的插件"""
    plugin, stored = editor({"enabled": False, "scale": 1, "speed": 1, "roam": "floor"})
    assert plugin.api_save_settings(SaveSettingsRequest(scale=1.2, speed=1, roam="free")).success
    assert not stored["enabled"] and not plugin.get_state()


@pytest.mark.parametrize("failure", ["write", "readback"])
def test_failed_persistence_keeps_runtime_parameters(failure):
    """写入失败或回读不一致时，运行中的活动参数不得提前改变"""
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
    """请求拒绝越界、非有限值、未知枚举和无权更改的配置字段"""
    with pytest.raises(ValidationError):
        SaveSettingsRequest(**{"scale": 1, "speed": 1, "roam": "floor", **change})


def test_edit_route_requires_admin_and_read_route_only_requires_login():
    """活动保存需要管理员，编辑读取只要求登录且不改变配置"""
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


@pytest.mark.parametrize("phase", ["read", "write", "readback"])
def test_settings_io_errors_return_failure_without_changing_runtime(phase):
    """读取、写入和回读异常均返回失败，不改变运行参数或已有配置"""
    plugin, stored = editor()
    before = plugin.settings()
    original = deepcopy(stored)
    calls = 0

    def read():
        """根据测试阶段在首读或回读注入故障，其他读取返回独立快照"""
        nonlocal calls
        calls += 1
        if phase == "read" or (phase == "readback" and calls == 2):
            raise OSError("settings unavailable")
        return deepcopy(stored)

    def write(_values):
        """仅在写入阶段注入运行时错误，不实际覆盖原始配置"""
        if phase == "write":
            raise RuntimeError("settings unavailable")
        return True

    plugin.get_config = read
    plugin.update_config = write
    response = plugin.api_save_settings(SaveSettingsRequest(scale=1.3, speed=1.5, roam="free"))
    assert not response.success
    assert plugin.settings() == before
    assert stored == original
