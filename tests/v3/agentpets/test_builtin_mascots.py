import json
import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageOps

from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.requests import SavePetSettingsRequest
from app.plugins.agentpets.packs.constants import BUILTIN_PACK_IDS, BUILTIN_STAGE_PACKS, PackError
from app.plugins.agentpets.packs.schema import codex_pet_version, parse_pack
from app.plugins.agentpets.packs.store import load_builtin_pack

ROOT = Path(__file__).parents[3] / "plugins.v3" / "agentpets"
ASSETS = ROOT / "frontend" / "src" / "assets"
NATIVE_MASCOTS = ("builtin-chibiterasu", "builtin-nailong", "builtin-kurisu")


@pytest.mark.parametrize("key", NATIVE_MASCOTS)
def test_builtin_assets_are_valid_offline_packs_with_complete_action_references(key):
    """逐只校验内置原生动作、眼位、出处与素材转换参数"""
    pack = load_builtin_pack(ASSETS, key)
    assert pack["id"] == key and codex_pet_version(pack) is None
    assert pack["description"] == "shine lock专属"
    calibration = pack["calibration"]
    assert calibration["left_eye_x"] < calibration["right_eye_x"]
    assert calibration["head_top_y"] < min(calibration["left_eye_y"], calibration["right_eye_y"])
    assert len(pack["actions"]) == 36
    assert len(pack["action_mappings"]) == 17
    assert pack["action_mappings"]["stage.held"] == "drag"
    assert pack["action_mappings"]["stage.fall"] == "fall"
    peeking = pack["actions"]["peek"]
    idle_frames = pack["actions"]["idle"]["frames"]
    assert peeking["frames"][0] == idle_frames[0]
    if key == "builtin-chibiterasu":
        assert peeking["frames"] == idle_frames[:1] and not peeking["loop"]
    else:
        assert peeking["frames"] == idle_frames[:2] and peeking["loop"]
        assert peeking["frame_durations"] == [3200, 140]
    metadata = json.loads((ASSETS / "packs" / key / "provenance.json").read_text(encoding="utf-8"))
    assert metadata["archive_sha256"] == "019cbc33013486db096d31547738cf948bdeaad7798734977b79cdcdb2c11686"
    assert metadata["tick_ms"] == 33
    width, height = metadata["cell_size"]
    converter = runpy.run_path(str(ROOT.parents[1] / "scripts" / "agentpets" / "convert_agentmascot.py"))
    assert converter["peek_action"](key.removeprefix("builtin-"), idle_frames) == peeking
    expected = converter["face_landmarks"](key.removeprefix("builtin-"), width, height)
    assert {name: calibration[name] for name in expected} == expected
    with pytest.raises(ValueError, match="Remeasure"):
        converter["face_landmarks"](key.removeprefix("builtin-"), width + 1, height)
    with Image.open(ASSETS / "packs" / key / "sheet.webp") as sheet:
        assert sheet.size == (width * pack["grid"]["cols"], height * pack["grid"]["rows"])
        assert max(sheet.size) <= 4096
        assert sheet.mode == "RGBA"
        for index in set(pack["frames"].values()):
            x, y = index % pack["grid"]["cols"] * width, index // pack["grid"]["cols"] * height
            assert sheet.crop((x, y, x + width, y + height)).getbbox()
    assert (ASSETS / "packs" / key / "sheet.webp").stat().st_size < 4 * 1024 * 1024
    assert (ASSETS / "packs" / key / "pack.json").stat().st_size < 64 * 1024


@pytest.mark.parametrize("key", NATIVE_MASCOTS)
def test_native_left_walk_and_mirrored_right_walk_are_distinct_cells(key):
    """左右行走使用各自帧格，镜像结果不与原帧混淆"""
    pack = load_builtin_pack(ASSETS, key)
    with Image.open(ASSETS / "packs" / key / "sheet.webp") as source:
        width = source.width // pack["grid"]["cols"]
        height = source.height // pack["grid"]["rows"]

        def crop(name):
            """按帧索引裁出原生格子以比较图像内容"""
            index = pack["frames"][name]
            x, y = index % pack["grid"]["cols"] * width, index // pack["grid"]["cols"] * height
            cell = source.crop((x, y, x + width, y + height))
            return cell.crop(cell.getbbox())

        for left, right in zip(pack["actions"]["running-left"]["frames"], pack["actions"]["running-right"]["frames"]):
            assert pack["frames"][left] != pack["frames"][right]
            a, b = ImageOps.mirror(crop(left)), crop(right)
            assert a.size == b.size
            background_a = Image.new("RGBA", a.size, "white")
            background_b = Image.new("RGBA", b.size, "white")
            background_a.alpha_composite(a)
            background_b.alpha_composite(b)
            assert background_a.tobytes() == background_b.tobytes()


def test_builtin_registry_does_not_touch_or_shadow_existing_user_packs(tmp_path):
    """注册内置形象不覆盖用户素材，保留 ID 与独立活动设置"""
    plugin = AgentPets()
    config = {"enabled": True, "scale": 1.5, "speed": 1, "roam": "floor"}
    stored = deepcopy(config)
    plugin.init_plugin(config)
    records = [{"id": "kurisu-v2", "name": "Existing", "grid": {"cols": 8, "rows": 11}, "codex_version": "v2"}]
    original = deepcopy(records)
    plugin.get_data = lambda key=None: records if key == "packs" else None
    plugin.save_data = lambda *_args: pytest.fail("Built-ins must not write user pack data")
    plugin.get_data_path = lambda: tmp_path
    plugin.get_config = lambda: deepcopy(stored)

    def save(value):
        """把配置保存在内存中，避免测试写入真实插件配置"""
        stored.clear()
        stored.update(deepcopy(value))
        return True

    plugin.update_config = save
    pets = plugin.get_agent_pets()
    assert len({p["key"] for p in pets}) == len(pets)
    assert {p["key"] for p in pets if p["mode"] == "stage"} == {"ying", "kurisu-v2", *BUILTIN_STAGE_PACKS}
    assert len(plugin.api_packs().data) == len(BUILTIN_PACK_IDS) + 1
    for key in BUILTIN_STAGE_PACKS:
        assert plugin.api_pack(key).data["builtin"]
        assert not plugin.api_delete_pack(SimpleNamespace(id=key)).success
        assert not plugin.api_add_pack(SimpleNamespace(pack=load_builtin_pack(ASSETS, key), image=None)).success
    response = plugin.api_save_pet_settings(SavePetSettingsRequest(
        key="builtin-kurisu", scale=0.8, speed=1.2, expected={"scale": 1.5, "speed": 1}))
    assert response.success
    plugin.init_plugin(stored)
    assert plugin.settings("builtin-kurisu")["scale"] == 0.8
    assert plugin.settings("kurisu-v2")["scale"] == plugin.settings("builtin-nailong")["scale"] == 1.5
    assert records == original


@pytest.mark.parametrize("durations", [[40], [40, 5001], [False, 80], [33, 100], "40,80"])
def test_invalid_individual_timings_are_rejected(durations):
    """逐帧时长拒绝越界、错误类型和与帧数不匹配的数据"""
    with pytest.raises(PackError):
        parse_pack({"name": "test", "grid": {"cols": 2, "rows": 1}, "frames": {"idle": 0, "other": 1},
                    "actions": {"idle": {"frames": ["idle", "other"], "frame_durations": durations}}})


def test_timing_extension_is_additive_and_validated():
    """旧固定帧时长保持兼容，合法逐帧时长按原值保留"""
    value = {"name": "test", "grid": {"cols": 2, "rows": 1}, "frames": {"idle": 0, "other": 1},
             "actions": {"idle": {"frames": ["idle", "other"], "frame_ms": 160, "frame_durations": [99, 231]}}}
    assert parse_pack(value)["actions"]["idle"]["frame_durations"] == [99, 231]
    with pytest.raises(PackError):
        load_builtin_pack(ASSETS, "../missing")


@pytest.mark.parametrize("key", ["builtin-nailong", "builtin-kurisu"])
def test_ground_baselines_keep_feet_inside_and_preserve_air_and_running_offsets(key):
    """内置动作脚底基线保持接地，同时保留空中与奔跑的原生位移"""
    pack = load_builtin_pack(ASSETS, key)
    baselines = pack["action_baselines"]
    with Image.open(ASSETS / "packs" / key / "sheet.webp") as sheet:
        width, height = sheet.width // pack["grid"]["cols"], sheet.height // pack["grid"]["rows"]

        def bottoms(action):
            """提取各动作帧的透明边界底部，用于核对接地位置"""
            values = []
            for frame in pack["actions"][action]["frames"]:
                index = pack["frames"][frame]
                x, y = index % pack["grid"]["cols"] * width, index // pack["grid"]["cols"] * height
                values.append(sheet.crop((x, y, x + width, y + height)).getbbox()[3])
            return values

        for action, baseline in baselines.items():
            assert max(bottoms(action)) <= baseline * height + 0.03, action
        for action in ("idle", "running-left", "running-right", "think", "sleep", "land", "peek"):
            assert abs(max(bottoms(action)) - baselines[action] * height) < 0.03, action
        assert abs(baselines["run"] * height - max(bottoms("run")) - 30) < 0.03
        assert abs(baselines["dash"] * height - max(bottoms("dash")) - 21) < 0.03
    for action in ("jump", "fall", "drag", "resist", "hold-wall", "hold-ceiling", "sit-feet-down", "dangle-feet"):
        assert action not in baselines
    assert "action_baselines" not in load_builtin_pack(ASSETS, "builtin-chibiterasu")


@pytest.mark.parametrize("baselines", [None, [], "idle", {"missing": .8}, {"idle": True}, {"idle": -.1},
                                       {"idle": 1.1}, {"idle": float("nan")}, {"idle": "0.8"}, {"idle": 0}])
def test_action_baselines_reject_invalid_values(baselines):
    """动作基线拒绝越界及未定义动作，避免生成不可显示素材"""
    with pytest.raises(PackError):
        parse_pack({"id": "builtin-nailong", "name": "test", "grid": {"cols": 1, "rows": 1}, "frames": {"idle": 0},
                    "actions": {"idle": ["idle"]}, "action_baselines": baselines})


def test_action_baselines_are_not_an_imported_pet_behavior_change():
    """动作专用基线仅限内置逐帧形象，不悄悄改变导入素材契约"""
    with pytest.raises(PackError, match="仅供内置"):
        parse_pack({"id": "custom", "name": "test", "grid": {"cols": 1, "rows": 1}, "frames": {"idle": 0},
                    "actions": {"idle": ["idle"]}, "action_baselines": {"idle": .8}})
