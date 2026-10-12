"""改名和动作映射独立持久化，验证数据保留、并发旧值和管理员边界。"""
from copy import deepcopy

import pytest

from app.plugins.agentpets import AgentPets, RenamePackRequest, SaveMappingsRequest, require_admin
from app.plugins.agentpets.pack import PackError, PackStore


@pytest.fixture
def state(tmp_path):
    record = {
        "id": "rem", "name": "Rem", "codex_version": "v1", "grid": {"cols": 8, "rows": 9},
        "frames": {"idle": 0}, "actions": {"idle": {"frames": ["idle"], "frame_ms": 360, "loop": True}},
        "source": "upload", "image_file": "rem.webp", "future_field": {"keep": 1},
    }
    data = {"packs": [record, {**deepcopy(record), "id": "other", "name": "Other"}]}
    store = PackStore(lambda key: data.get(key), lambda key, value: data.__setitem__(key, value), tmp_path)
    return store, data, record


def test_rename_preserves_identity_assets_and_other_pet(state):
    store, data, before = state
    snapshot = deepcopy(data)
    result = store.update("rem", name="  蕾姆  ", expected_name="Rem")
    assert result["name"] == "蕾姆"
    assert {**result, "name": "Rem"} == before
    assert data["packs"][1] == snapshot["packs"][1]
    assert before["name"] == "Rem", "must not mutate a cached original record"


def test_mappings_preserve_raw_animation_and_rename_and_reset(state):
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
    store, data, _ = state
    before = deepcopy(data)
    with pytest.raises(PackError):
        store.update("rem", **kwargs)
    assert data == before


def test_v2_direction_mapping_and_failed_persistence(state):
    store, data, _ = state
    data["packs"][0].update(codex_version="v2", grid={"cols": 8, "rows": 11})
    assert store.update("rem", mappings={"stage.think": "look-337-5"}, expected_mappings={})["action_mappings"]
    before = deepcopy(data)
    store._save_data = lambda *_: False
    with pytest.raises(PackError, match="保存失败"):
        store.update("rem", name="New", expected_name="Rem")
    assert data == before


def test_missing_builtin_and_non_codex_cannot_be_edited(state):
    store, data, _ = state
    for key in ("missing", "projector-cat", "ying"):
        with pytest.raises(PackError):
            store.update(key, name="New", expected_name="Rem")
    data["packs"][0].pop("codex_version")
    data["packs"][0]["grid"] = {"cols": 1, "rows": 1}
    with pytest.raises(PackError, match="Codex"):
        store.update("rem", name="New", expected_name="Rem")


def test_api_readback_and_permissions(state):
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
    store, _, _ = state
    store._save_data = lambda *_: None
    with pytest.raises(PackError, match="回读"):
        store.update("rem", name="New", expected_name="Rem")
