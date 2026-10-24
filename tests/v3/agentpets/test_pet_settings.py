from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.plugins.agentpets import AgentPets, require_admin
from app.plugins.agentpets.requests import (
    PeekAngles, SavePetSettingsRequest, SaveSettingsRequest, SaveSharedSettingsRequest,
)
from app.plugins.agentpets.settings import default_dialogue


def setup_editor(config=None):
    """建立内存配置和两只舞台素材，隔离真实插件运行环境"""
    stored = deepcopy(config if config is not None else {
        "enabled": True, "scale": 1.5, "speed": 1.0,
        "roam": "surfaces", "movement": "auto", "future": {"keep": 1},
    })
    records = {key: {"id": key, "name": key, "codex_version": "v2", "grid": {"cols": 8, "rows": 11}}
               for key in ("alpha", "beta")}
    plugin = AgentPets()
    plugin.init_plugin(deepcopy(stored))
    plugin.get_config = lambda: deepcopy(stored)
    plugin._store = lambda: SimpleNamespace(get=records.get, list=lambda: list(records.values()))

    def persist(config):
        """模拟配置持久化结果，供保存成功与失败回读路径验证"""
        stored.clear()
        stored.update(deepcopy(config))
        return True

    plugin.update_config = persist
    return plugin, stored, records


def request(key="alpha", scale=0.8, speed=1.2, expected=None):
    """构造含旧值的单只 Pet 设置请求"""
    return SavePetSettingsRequest(key=key, scale=scale, speed=speed,
                                  expected=expected or {"scale": 1.5, "speed": 1.0})


def test_inheritance_is_read_only_and_each_pet_survives_reload_and_rename():
    """默认值继承不写配置，独立设置按 ID 跨重载和改名保留"""
    plugin, stored, records = setup_editor()
    original = deepcopy(stored)
    assert plugin.api_settings("alpha").data == plugin.api_settings("beta").data
    assert stored == original and "pet_settings" not in stored
    assert plugin.api_save_pet_settings(request()).success
    assert plugin.settings("alpha")["scale"] == 0.8
    assert plugin.settings("beta")["scale"] == 1.5
    assert plugin.api_save_pet_settings(request("beta", 1.3, 0.7)).success
    records["alpha"]["name"] = "Renamed"
    plugin.init_plugin(deepcopy(stored))
    assert plugin.settings("alpha") == {
        "scale": 0.8, "speed": 1.2, "roam": "surfaces", "movement": "auto",
    }
    assert plugin.settings("beta")["speed"] == 0.7
    assert plugin.settings("ying")["scale"] == 1.5
    assert {k: v for k, v in stored.items() if k != "pet_settings"} == original
    assert plugin.api_editor().data["pet_settings"]["alpha"] == {"scale": 0.8, "speed": 1.2}


def test_built_in_stage_supports_independent_values():
    """小映支持独立大小和速度，不修改共享默认值"""
    plugin, stored, _ = setup_editor()
    assert plugin.api_save_pet_settings(request("ying")).success
    assert stored["scale"] == 1.5
    assert plugin.api_settings("ying").data["scale"] == 0.8


def test_shared_save_preserves_defaults_overrides_and_other_config():
    """共享活动写入保留默认大小、独立值和未知配置"""
    plugin, stored, _ = setup_editor()
    assert plugin.api_save_pet_settings(request()).success
    before = deepcopy(stored)
    result = plugin.api_save_shared_settings(SaveSharedSettingsRequest(
        roam="floor", movement="fixed", expected={"roam": "surfaces", "movement": "auto"}))
    assert result.success
    assert stored == {**before, "roam": "floor", "movement": "fixed"}
    assert plugin.settings("alpha")["scale"] == 0.8
    assert plugin.settings("beta")["movement"] == "fixed"


def test_legacy_default_write_retains_independent_overrides():
    """兼容旧默认设置接口，不覆盖已经保存的独立值"""
    plugin, stored, _ = setup_editor()
    assert plugin.api_save_pet_settings(request()).success
    assert plugin.api_save_settings(SaveSettingsRequest(scale=1.1, speed=0.9, roam="floor")).success
    assert plugin.settings("alpha")["scale"] == 0.8
    assert plugin.settings("beta")["scale"] == 1.1
    assert stored["pet_settings"]["alpha"]["speed"] == 1.2


def test_external_change_to_same_pet_or_shared_fields_is_not_overwritten():
    """同一 Pet 或共享字段的并发修改由旧值校验保护"""
    plugin, stored, _ = setup_editor()
    stored["pet_settings"] = {"alpha": {"scale": 1.2, "speed": 0.8}}
    before = deepcopy(stored)
    assert not plugin.api_save_pet_settings(request()).success
    assert stored == before
    stored["movement"] = "fixed"
    before = deepcopy(stored)
    assert not plugin.api_save_shared_settings(SaveSharedSettingsRequest(
        roam="floor", movement="auto", expected={"roam": "surfaces", "movement": "auto"})).success
    assert stored == before


def test_nonoverlapping_external_values_are_merged_from_latest_config():
    """非重叠的外部修改从最新配置合并，避免丢失其他形象设置"""
    plugin, stored, _ = setup_editor()
    stored["pet_settings"] = {"beta": {"scale": 0.6, "speed": 2.0}}
    stored["roam"] = "free"
    assert plugin.api_save_pet_settings(request()).success
    assert plugin.settings("alpha")["roam"] == "free"
    assert stored["pet_settings"]["beta"] == {"scale": 0.6, "speed": 2.0}


def test_concurrent_pet_saves_keep_both_entries():
    """并发保存不同 Pet 时串行合并并保留两份结果"""
    plugin, stored, _ = setup_editor()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda key: plugin.api_save_pet_settings(request(key)), ("alpha", "beta")))
    assert all(result.success for result in results)
    assert set(stored["pet_settings"]) == {"alpha", "beta"}


@pytest.mark.parametrize("key", ["missing", "projector-cat"])
def test_unknown_or_renderer_pets_cannot_read_or_write_stage_values(key):
    """失效 ID 和普通入口形象不能读取或写入舞台独立设置"""
    plugin, stored, _ = setup_editor()
    original = deepcopy(stored)
    assert not plugin.api_settings(key).success
    assert not plugin.api_save_pet_settings(request(key)).success
    assert stored == original


@pytest.mark.parametrize("kind", ["pet", "shared"])
@pytest.mark.parametrize("phase", ["read", "write", "readback", "mismatch", "false"])
def test_failed_save_does_not_publish_runtime_values(kind, phase):
    """读取、写入或回读失败时不发布未经确认的运行态设置"""
    plugin, stored, _ = setup_editor()
    original = deepcopy(stored)
    before = plugin.settings("alpha")
    calls = 0

    def read():
        """按请求阶段注入读取失败，验证首次读取和保存后回读边界"""
        nonlocal calls
        calls += 1
        if phase == "read" or (phase == "readback" and calls == 2):
            raise OSError("simulated failure")
        return deepcopy(stored)

    def persist(_config):
        """模拟配置持久化结果，供保存成功与失败回读路径验证"""
        if phase == "write":
            raise RuntimeError("simulated failure")
        return phase != "false"

    plugin.get_config = read
    plugin.update_config = persist
    result = plugin.api_save_pet_settings(request()) if kind == "pet" else plugin.api_save_shared_settings(
        SaveSharedSettingsRequest(roam="floor", movement="fixed", expected={"roam": "surfaces", "movement": "auto"}))
    assert not result.success
    assert plugin.settings("alpha") == before
    assert stored == original


@pytest.mark.parametrize("patch", [
    {"key": "../alpha"}, {"scale": 9}, {"speed": float("nan")},
    {"expected": None}, {"enabled": False}, {"roam": "floor"},
])
def test_pet_write_requires_valid_key_values_and_baseline(patch):
    """独立设置请求校验 ID、有限数值、范围和必需旧值"""
    with pytest.raises(ValidationError):
        SavePetSettingsRequest(**{
            "key": "alpha", "scale": 1, "speed": 1,
            "expected": {"scale": 1, "speed": 1}, **patch,
        })


@pytest.mark.parametrize("raw", [None, [], "bad", {"alpha": None}, {"alpha": {"scale": "bad", "speed": 9}}])
def test_invalid_legacy_override_data_is_normalized_without_migration(raw):
    """无效旧独立值只在读取时规整，不自动改写用户配置"""
    config = {"scale": 1.5, "speed": 1, "pet_settings": raw}
    plugin, stored, _ = setup_editor(config)
    assert 0.6 <= plugin.settings("alpha")["scale"] <= 1.6
    assert 0.5 <= plugin.settings("alpha")["speed"] <= 2
    assert stored == config


def test_new_routes_retain_admin_write_boundary():
    """新增独立与共享设置路由沿用管理员写权限"""
    plugin, _, _ = setup_editor()
    routes = {(r["path"], r["methods"][0]): r for r in plugin.get_api()}
    for path in ("/settings/pet", "/settings/shared"):
        assert routes[(path, "POST")]["dependencies"][0].dependency is require_admin
    assert "dependencies" not in routes[("/settings", "GET")]


def test_peek_angles_round_trip_without_touching_other_pets_or_legacy_defaults():
    """单只 Pet 三边角度跨重载保留，恢复默认不改变其他配置"""
    plugin, stored, _ = setup_editor()
    before = deepcopy(stored)
    angles = {"bottom": 20, "left": 15, "right": 40}
    default = {"bottom": 0, "left": 35, "right": 35}
    result = plugin.api_save_pet_settings(SavePetSettingsRequest(
        key="alpha", scale=1.5, speed=1, peek_angles=angles,
        expected={"scale": 1.5, "speed": 1, "peek_angles": default}))
    assert result.success
    plugin.init_plugin(deepcopy(stored))
    assert plugin.api_settings("alpha").data["peek_angles"] == angles
    response = plugin.api_settings("alpha").data
    response["peek_angles"]["bottom"] = 1
    assert plugin.api_settings("alpha").data["peek_angles"] == angles
    assert "peek_angles" not in plugin.api_settings("beta").data
    assert {k: v for k, v in stored.items() if k != "pet_settings"} == before
    stale = deepcopy(stored)
    assert not plugin.api_save_pet_settings(SavePetSettingsRequest(
        key="alpha", scale=1.5, speed=1, peek_angles=default,
        expected={"scale": 1.5, "speed": 1, "peek_angles": default})).success
    assert stored == stale
    assert plugin.api_save_pet_settings(SavePetSettingsRequest(
        key="alpha", scale=1.5, speed=1, peek_angles=default,
        expected={"scale": 1.5, "speed": 1, "peek_angles": angles})).success
    assert "peek_angles" not in plugin.api_settings("alpha").data
    assert "peek_angles" not in stored["pet_settings"]["alpha"]


def test_legacy_pet_and_default_writes_preserve_new_angles():
    """旧客户端只提交大小速度时，不清空新版独立角度"""
    angles = {"bottom": 20, "left": 35, "right": 35}
    plugin, stored, _ = setup_editor({
        "scale": 1.5, "speed": 1, "pet_settings": {"alpha": {
            "scale": 1.5, "speed": 1, "peek_angles": angles}}})
    assert plugin.api_save_pet_settings(request()).success
    assert stored["pet_settings"]["alpha"]["peek_angles"] == angles
    assert plugin.api_save_settings(SaveSettingsRequest(scale=1, speed=1, roam="floor")).success
    assert plugin.api_settings("alpha").data["peek_angles"] == angles


@pytest.mark.parametrize("angles", [
    {"bottom": -1}, {"left": 46}, {"right": float("nan")},
    {"bottom": float("inf")}, {"top": 20},
])
def test_invalid_angles_are_rejected_before_writing(angles):
    """拒绝越界、非有限值和不存在方向，保留原配置"""
    with pytest.raises(ValidationError):
        SavePetSettingsRequest(key="alpha", scale=1, speed=1, peek_angles=angles,
                               expected={"scale": 1, "speed": 1, "peek_angles": {}})


def test_new_angle_writes_require_a_baseline():
    """不能用缺失的旧值绕过角度并发保护"""
    with pytest.raises(ValidationError):
        SavePetSettingsRequest(key="alpha", scale=1, speed=1, peek_angles={"bottom": 20},
                               expected={"scale": 1, "speed": 1})


def test_upright_default_preserves_explicit_saved_angles_without_migrating_config():
    """底边默认归零，但已存三边角度不覆盖，也不批量迁移配置"""
    assert PeekAngles().model_dump() == {"bottom": 0, "left": 35, "right": 35}
    angles = {"bottom": 35, "left": 35, "right": 35}
    config = {"scale": 1.5, "speed": 1, "pet_settings": {
        "alpha": {"scale": 1.5, "speed": 1, "peek_angles": angles}}}
    plugin, stored, _ = setup_editor(config)
    assert plugin.api_settings("alpha").data["peek_angles"] == angles
    assert "peek_angles" not in plugin.api_settings("beta").data
    assert stored == config


@pytest.mark.parametrize("key", ["ying", "alpha", "builtin-kurisu"])
def test_dialogue_defaults_remain_implicit_and_do_not_migrate_existing_data(key):
    """未配置小映沿用旧台词，其他 Pet 静默；读取与重载不回写配置"""
    plugin, stored, _ = setup_editor()
    before = deepcopy(stored)
    assert "dialogue" not in plugin.api_settings(key).data
    assert "dialogue" not in plugin.api_editor().data["pet_settings"][key]
    expected = {"mode": "interaction", "voice": "default"} if key == "ying" else {"mode": "off", "voice": "neutral"}
    assert default_dialogue(key) == expected
    plugin.init_plugin(deepcopy(stored))
    assert stored == before


@pytest.mark.parametrize("key", ["ying", "alpha", "builtin-kurisu"])
def test_dialogue_round_trip_is_per_pet_and_preserves_all_other_data(key):
    """按 Pet 保存语气与话量，保留活动、角度、其他形象和未知配置"""
    angles = {"bottom": 20, "left": 30, "right": 35}
    config = {"enabled": True, "scale": 1.5, "speed": 1, "movement": "auto", "future": {"keep": 1},
              "pet_settings": {key: {"scale": 1.5, "speed": 1, "peek_angles": angles, "future_pet": {"keep": 2}},
                               "beta": {"scale": 1.2, "speed": 0.8}}}
    plugin, stored, records = setup_editor(config)
    before = deepcopy(stored)
    dialogue = {"mode": "occasional", "voice": "wry"}
    response = plugin.api_save_pet_settings(SavePetSettingsRequest(
        key=key, scale=1.5, speed=1, dialogue=dialogue,
        expected={"scale": 1.5, "speed": 1, "dialogue": default_dialogue(key)}))
    assert response.success
    before["pet_settings"][key]["dialogue"] = dialogue
    assert stored == before
    plugin.init_plugin(deepcopy(stored))
    if key in records:
        records[key]["name"] = "Renamed"
    result = plugin.api_settings(key).data
    assert result["dialogue"] == dialogue and result["peek_angles"] == angles
    result["dialogue"]["voice"] = "neutral"
    assert plugin.api_settings(key).data["dialogue"] == dialogue
    assert plugin.api_editor().data["pet_settings"][key]["dialogue"] == dialogue
    assert "dialogue" not in plugin.api_settings("beta").data


def test_new_dialogue_write_rejects_a_stale_voice_or_mode_without_changing_config():
    """新版台词保存必须核对有效旧值，不能覆盖另一个页面的修改"""
    dialogue = {"mode": "interaction", "voice": "lively"}
    plugin, stored, _ = setup_editor({"scale": 1.5, "speed": 1, "pet_settings": {
        "alpha": {"scale": 1.5, "speed": 1, "dialogue": dialogue}}})
    before = deepcopy(stored)
    response = plugin.api_save_pet_settings(SavePetSettingsRequest(
        key="alpha", scale=1.5, speed=1, dialogue={"mode": "off", "voice": "neutral"},
        expected={"scale": 1.5, "speed": 1, "dialogue": default_dialogue("alpha")}))
    assert not response.success and "台词" in response.message
    assert stored == before


def test_old_pet_default_and_shared_clients_preserve_explicit_dialogue():
    """旧客户端更新大小、默认值或活动方式，不能清空已存台词偏好"""
    dialogue = {"mode": "off", "voice": "wry"}
    plugin, stored, _ = setup_editor({"scale": 1.5, "speed": 1, "pet_settings": {
        "alpha": {"scale": 1.5, "speed": 1, "dialogue": dialogue, "future_pet": "keep"}}})
    assert plugin.api_save_pet_settings(request()).success
    assert stored["pet_settings"]["alpha"]["dialogue"] == dialogue
    assert stored["pet_settings"]["alpha"]["future_pet"] == "keep"
    assert plugin.api_save_settings(SaveSettingsRequest(scale=1, speed=1, roam="floor")).success
    assert plugin.api_save_shared_settings(SaveSharedSettingsRequest(
        roam="free", movement="auto", expected={"roam": "floor", "movement": "auto"})).success
    assert plugin.settings("alpha")["dialogue"] == dialogue
    assert "dialogue" not in plugin.settings("beta")
    assert "dialogue" not in stored


@pytest.mark.parametrize("dialogue", [
    {"mode": "unknown", "voice": "neutral"}, {"mode": "off", "voice": "unknown"},
    {"mode": "interaction"}, {"voice": "wry"}, [], "off",
    {"mode": "off", "voice": "wry", "future": True},
])
def test_invalid_dialogue_requests_are_rejected_before_writing(dialogue):
    """台词枚举、字段与结构严格校验，不接受任意人设或附加数据"""
    with pytest.raises(ValidationError):
        SavePetSettingsRequest(key="alpha", scale=1, speed=1, dialogue=dialogue,
                               expected={"scale": 1, "speed": 1, "dialogue": default_dialogue("alpha")})


def test_dialogue_writes_require_explicit_old_values_and_cannot_use_global_defaults_endpoint():
    """新台词请求不可缺失旧值，也不能从旧全局设置入口写入"""
    dialogue = {"mode": "interaction", "voice": "neutral"}
    with pytest.raises(ValidationError):
        SavePetSettingsRequest(key="alpha", scale=1, speed=1, dialogue=dialogue,
                               expected={"scale": 1, "speed": 1})
    with pytest.raises(ValidationError):
        SaveSettingsRequest(scale=1, speed=1, roam="floor", dialogue=dialogue)


@pytest.mark.parametrize("raw", [None, [], "off", {"mode": "unknown", "voice": "unknown"},
                                 {"mode": "interaction", "voice": "unknown"}, {"mode": "interaction"}])
def test_invalid_saved_dialogue_is_read_conservatively_without_rewriting_user_config(raw):
    """损坏旧偏好只保守规整为静默，不自动迁移原用户数据"""
    config = {"scale": 1, "speed": 1, "pet_settings": {"alpha": {"scale": 1, "speed": 1, "dialogue": raw}}}
    plugin, stored, _ = setup_editor(config)
    assert plugin.settings("alpha").get("dialogue", default_dialogue("alpha")) == {"mode": "off", "voice": "neutral"}
    assert stored == config
