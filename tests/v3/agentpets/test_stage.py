"""助手形象插件的多形象声明、小映设置与联邦产物合同测试。"""

from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from PIL import Image

import app.plugins.agentpets as agentpets
from app.plugins.agentpets import AgentPets
from app.runtime.extensions.plugin.contracts import supports_plugin_hook

PLUGIN_ROOT = Path(__file__).parents[3] / "plugins.v3" / "agentpets"
DIST = PLUGIN_ROOT / "frontend" / "dist" / "assets"
POSES = [
    "idle", "blink", "talk", "think", "jump", "wave", "held", "fall", "sit",
    "walk1", "walk2", "walk3", "walk4", "doze", "confused", "alert", "victory", "busy",
]


def _plugin(config: dict | None = None) -> AgentPets:
    plugin = AgentPets()
    plugin.init_plugin(config)
    plugin.get_data = lambda key=None: None
    return plugin


def test_registers_stage_and_builtin_sprite_pets() -> None:
    """一个插件注册多个形象：小映为 stage，放映猫为 renderer，各自指定暴露组件。"""
    pets = _plugin({"enabled": True}).get_agent_pets()

    assert [(pet["key"], pet["mode"], pet["component"]) for pet in pets] == [
        ("ying", "stage", "AgentPet"),
        ("projector-cat", "renderer", "AgentPetSprite"),
    ]
    stage = pets[0]
    assert stage["bubbles"] == "host"
    for pet in pets:
        assert re.fullmatch(r"[a-z0-9_-]{1,32}", pet["key"])
        assert pet["api_version"] == 1
    assert supports_plugin_hook(AgentPets(), "get_agent_pets")


def test_builtin_images_are_small_decodable_inline_images() -> None:
    """宿主无需请求静态图片即可显示两只角色，保留透明背景与头像尺寸。"""
    assert (DIST / "remoteEntry.js").is_file()
    total = 0
    for pet in _plugin().get_agent_pets():
        for field in ("preview", "avatar"):
            header, payload = pet[field].split(",", 1)
            assert header == "data:image/webp;base64"
            total += len(pet[field])
            content = base64.b64decode(payload, validate=True)
            with Image.open(BytesIO(content)) as image:
                image.load()
                assert image.format == "WEBP"
                assert image.mode == "RGBA" and image.getextrema()[3][0] == 0
                bound = 128 if field == "avatar" else 320
                assert 0 < max(image.size) <= bound
                if field == "avatar":
                    assert image.width == image.height
    assert total < 64 * 1024


def test_builtin_images_are_encoded_once_across_declaration_reads(monkeypatch) -> None:
    agentpets._builtin_image.cache_clear()
    original = Image.open
    opened = []

    def track_open(path):
        opened.append(path)
        return original(path)

    monkeypatch.setattr(Image, "open", track_open)
    try:
        first = _plugin().get_agent_pets()
        assert _plugin().get_agent_pets() == first
        assert len(opened) == 4
    finally:
        agentpets._builtin_image.cache_clear()


@pytest.mark.parametrize("corrupt", [False, True])
def test_unreadable_builtin_image_preserves_registration(monkeypatch, tmp_path, corrupt) -> None:
    monkeypatch.setattr(agentpets, "PLUGIN_DIR", tmp_path)
    path = tmp_path / agentpets.DIST_PATH / agentpets.STAGE_PREVIEW
    if corrupt:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"broken PNG")
    agentpets._builtin_image.cache_clear()
    try:
        pets = _plugin().get_agent_pets()
        assert [pet["key"] for pet in pets] == ["ying", "projector-cat"]
        assert pets[0]["preview"] == agentpets.STAGE_PREVIEW
        assert pets[1]["avatar"] == agentpets.BUILTIN_AVATAR
    finally:
        agentpets._builtin_image.cache_clear()


def test_user_images_are_not_replaced_by_builtin_images() -> None:
    record = {"id": "custom", "name": "用户角色", "preview": "https://example.com/pet.png",
              "avatar": "data:image/png;base64,user-image"}
    plugin = _plugin()
    plugin._store = lambda: SimpleNamespace(list=lambda: [record])
    pet = plugin.get_agent_pets()[-1]
    assert pet["key"] == record["id"]
    assert pet["preview"] == record["preview"]
    assert pet["avatar"] == record["avatar"]


def test_every_pose_frame_is_shipped() -> None:
    """所有姿态帧（含四帧走路循环）都随源码和联邦产物一起分发。"""
    for pose in POSES:
        assert (PLUGIN_ROOT / "frontend" / "src" / "assets" / "ying" / f"{pose}.webp").is_file()
        assert (DIST / "ying" / f"{pose}.webp").is_file()


def test_registered_components_are_exposed() -> None:
    """小映、普通素材包与 Codex Pet 的组件都由联邦入口暴露。"""
    remote_entry = (DIST / "remoteEntry.js").read_text(encoding="utf-8")
    for name in ("./AgentPet", "./AgentPetSprite", "./AgentPetCodex", "./Config", "./Page"):
        assert f'"{name}"' in remote_entry


def test_settings_default_and_clamp() -> None:
    """小映设置缺省为 1 倍、站在页面元素上；越界和非法值按边界收敛。"""
    assert _plugin().settings() == {"scale": 1.0, "speed": 1.0, "roam": "surfaces"}
    assert _plugin({"scale": 9, "speed": 0.1, "roam": "free"}).settings() == {"scale": 1.6, "speed": 0.5, "roam": "free"}
    assert _plugin({"scale": "abc", "speed": float("nan"), "roam": "moon"}).settings() == {
        "scale": 1.0,
        "speed": 1.0,
        "roam": "surfaces",
    }


def test_settings_api_requires_login_and_returns_saved_values() -> None:
    """小映读取设置的接口只要求登录态，并返回已保存的值。"""
    plugin = _plugin({"enabled": True, "scale": 1.25, "speed": 0.8, "roam": "floor"})
    routes = {(route["path"], route["methods"][0]): route for route in plugin.get_api()}

    route = routes[("/settings", "GET")]
    assert route["auth"] == "bear" and "dependencies" not in route
    response = route["endpoint"]()
    assert response.success is True
    assert response.data == {"scale": 1.25, "speed": 0.8, "roam": "floor"}


def test_form_defaults_match_settings_and_state_follows_enabled() -> None:
    """表单默认值与设置默认值一致，启用状态由配置决定。"""
    _, defaults = AgentPets().get_form()

    assert defaults == {"enabled": False, "scale": 1.0, "speed": 1.0, "roam": "surfaces"}
    assert _plugin({"enabled": True}).get_state() is True
    assert _plugin({}).get_state() is False
    assert AgentPets.get_render_mode()[0] == "vue"
