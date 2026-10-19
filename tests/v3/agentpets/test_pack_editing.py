"""改名、备注和动作映射独立持久化，验证数据保留、并发旧值和管理员边界。"""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.plugins.agentpets import AgentPets, require_admin
from app.plugins.agentpets.packs.constants import PackError
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import RenamePackRequest, SaveDescriptionRequest, SaveMappingsRequest


@pytest.fixture
def state(tmp_path):
    """提供两份 Codex 记录与未知字段，用于验证局部编辑和实例内隔离"""
    record = {
        "id": "rem", "name": "Rem", "codex_version": "v1", "grid": {"cols": 8, "rows": 9},
        "frames": {"idle": 0}, "actions": {"idle": {"frames": ["idle"], "frame_ms": 360, "loop": True}},
        "source": "upload", "image_file": "rem.webp", "future_field": {"keep": 1},
    }
    data = {"packs": [record, {**deepcopy(record), "id": "other", "name": "Other"}]}
    store = PackStore(lambda key: data.get(key), lambda key, value: data.__setitem__(key, value), tmp_path)
    return store, data, record


def test_rename_preserves_identity_assets_and_other_pet(state):
    """重命名只改目标名称，不变更缓存原对象、未知字段和其他素材"""
    store, data, before = state
    snapshot = deepcopy(data)
    result = store.update("rem", name="  蕾姆  ", expected_name="Rem")
    assert result["name"] == "蕾姆"
    assert {**result, "name": "Rem"} == before
    assert data["packs"][1] == snapshot["packs"][1]
    assert before["name"] == "Rem", "must not mutate a cached original record"


def test_mappings_preserve_raw_animation_and_rename_and_reset(state):
    """映射编辑不改原始动画，改名后映射保留且可恢复默认"""
    store, _, before = state
    mapping = {"stage.think": "review", "stage.walk-left": "running-left", "action.nod": "waving"}
    result = store.update("rem", mappings=mapping, expected_mappings={})
    assert result["actions"] == before["actions"] and result["frames"] == before["frames"]
    renamed = store.update("rem", name="蕾姆", expected_name="Rem")
    assert renamed["action_mappings"] == mapping
    reset = store.update("rem", mappings={}, expected_mappings=mapping)
    assert reset.get("action_mappings", {}) == {} and reset["name"] == "蕾姆"


@pytest.mark.parametrize("kwargs", [
    {"name": " ", "expected_name": "Rem"}, {"name": "x" * 41, "expected_name": "Rem"},
    {"name": "New", "expected_name": "outdated"},
    {"mappings": {"stage.unknown": "idle"}, "expected_mappings": {}},
    {"mappings": {"stage.think": "missing"}, "expected_mappings": {}},
    {"mappings": {"stage.think": "look-000"}, "expected_mappings": {}},
    {"mappings": {}, "expected_mappings": {"stage.think": "review"}},
])
def test_invalid_or_stale_edits_do_not_write(state, kwargs):
    """非法名称、触发器、动画或过期旧值不得写入元数据"""
    store, data, _ = state
    before = deepcopy(data)
    with pytest.raises(PackError):
        store.update("rem", **kwargs)
    assert data == before


def test_v2_direction_mapping_and_failed_persistence(state):
    """v2 可映射视线动作，保存失败时原数据不发生变化"""
    store, data, _ = state
    data["packs"][0].update(codex_version="v2", grid={"cols": 8, "rows": 11})
    assert store.update("rem", mappings={"stage.think": "look-337-5"}, expected_mappings={})["action_mappings"]
    before = deepcopy(data)
    store._save_data = lambda *_: False
    with pytest.raises(PackError, match="保存失败"):
        store.update("rem", name="New", expected_name="Rem")
    assert data == before


def test_missing_builtin_and_non_codex_cannot_be_edited(state):
    """仅已有用户 Codex 素材可编辑，内置、缺失和普通入口素材被拒绝"""
    store, data, _ = state
    for key in ("missing", "projector-cat", "ying"):
        with pytest.raises(PackError):
            store.update(key, name="New", expected_name="Rem")
    data["packs"][0].pop("codex_version")
    data["packs"][0]["grid"] = {"cols": 1, "rows": 1}
    with pytest.raises(PackError, match="Codex"):
        store.update("rem", name="New", expected_name="Rem")


def test_api_readback_and_permissions(state):
    """API 回读改名和映射结果，形象声明同步且写路由均要求管理员"""
    store, _, _ = state
    plugin = AgentPets()
    plugin._store = lambda: store
    renamed = plugin.api_rename_pack(RenamePackRequest(id="rem", name="蕾姆", expected_name="Rem"))
    assert renamed.success and renamed.data["name"] == "蕾姆"
    mappings = {"stage.think": "review"}
    result = plugin.api_save_mappings(SaveMappingsRequest(id="rem", mappings=mappings, expected_mappings={}))
    assert result.success and result.data == {"id": "rem", "mappings": mappings}
    assert next(pet for pet in plugin.get_agent_pets() if pet["key"] == "rem")["name"] == "蕾姆"
    for route in plugin.get_api():
        if route["path"] in ("/packs/rename", "/packs/mappings"):
            assert route["auth"] == "bear" and route["methods"] == ["POST"]
            assert route["dependencies"][0].dependency is require_admin


def test_failed_readback_is_not_reported_as_success(state):
    """保存未真正落地时回读检查失败，不把无效持久化报告为成功"""
    store, _, _ = state
    store._save_data = lambda *_: None
    with pytest.raises(PackError, match="回读"):
        store.update("rem", name="New", expected_name="Rem")


def test_description_preserves_all_other_fields_and_cached_record(state):
    """只改备注，其他元数据及缓存原记录均保持不变"""
    store, data, before = state
    before.update(description="Original", calibration={"eye_y": 0.2}, action_mappings={"stage.peek": "idle"})
    snapshot = deepcopy(data)
    result = store.update("rem", description="  z256专属  ", expected_description="Original")
    assert result["description"] == "z256专属"
    assert {**result, "description": "Original"} == snapshot["packs"][0]
    assert data["packs"][1] == snapshot["packs"][1]
    assert before["description"] == "Original"
    assert store.update("rem", description="", expected_description="z256专属")["description"] == ""


@pytest.mark.parametrize("kwargs", [
    {"description": "new", "expected_description": "stale"},
    {"description": "new"},
    {"description": "x" * 121, "expected_description": ""},
    {"description": 42, "expected_description": ""},
])
def test_invalid_or_stale_description_does_not_write(state, kwargs):
    """无效或过期备注拒绝写入，不覆盖并发修改"""
    store, data, _ = state
    before = deepcopy(data)
    with pytest.raises(PackError):
        store.update("rem", **kwargs)
    assert data == before


@pytest.mark.parametrize("failure", [False, None])
def test_description_persistence_failures_are_not_success(state, failure):
    """保存失败或回读不一致不能冒充备注保存成功"""
    store, data, _ = state
    before = deepcopy(data)
    store._save_data = lambda *_: failure
    with pytest.raises(PackError, match="保存"):
        store.update("rem", description="New", expected_description="")
    assert data == before


@pytest.mark.parametrize("changes", [
    {"description": None}, {"description": "x" * 121}, {"expected_description": None},
    {"image": "replacement"}, {"name": "replacement"}, {"id": ""},
])
def test_description_request_rejects_invalid_or_unrelated_fields(changes):
    """备注请求拒绝超长、无效及无关字段"""
    with pytest.raises(ValidationError):
        SaveDescriptionRequest(**{"id": "rem", "description": "new", "expected_description": "", **changes})


def test_description_api_permissions_readback_and_conflict(state):
    """备注写入保留管理员边界、正确回读与旧值冲突保护"""
    store, _, _ = state
    plugin = AgentPets()
    plugin._store = lambda: store
    request = SaveDescriptionRequest(id="rem", description="z256专属", expected_description="")
    result = plugin.api_save_description(request)
    assert result.success and result.data.model_dump() == {"id": "rem", "description": "z256专属"}
    assert not plugin.api_save_description(request).success
    assert next(pet for pet in plugin.get_agent_pets() if pet["key"] == "rem")["description"] == "z256专属"
    route = next(item for item in plugin.get_api() if item["path"] == "/packs/description")
    assert route["auth"] == "bear" and route["methods"] == ["POST"]
    assert route["dependencies"][0].dependency is require_admin
    assert route["response_model"].model_validate(result.model_dump()).data.description == "z256专属"
    for key in ("missing", "builtin-kurisu"):
        assert not plugin.api_save_description(request.model_copy(update={"id": key})).success
