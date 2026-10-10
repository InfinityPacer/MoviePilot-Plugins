"""助手形象插件的多形象声明、小映设置与联邦产物合同测试。"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

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
    assert stage["preview"] == "ying/preview.png"
    assert stage["avatar"] == "ying/avatar.png"
    assert pets[1]["avatar"] == "packs/projector-cat/avatar.png"
    for pet in pets:
        assert re.fullmatch(r"[a-z0-9_-]{1,32}", pet["key"])
        assert pet["api_version"] == 1
    assert supports_plugin_hook(AgentPets(), "get_agent_pets")


def test_declared_images_exist_in_the_federation_dist() -> None:
    """预览图和头像相对 remoteEntry 所在目录，且构建产物里真实存在；头像是方图。"""
    _, dist_path = AgentPets.get_render_mode()
    assert dist_path == "frontend/dist/assets"
    assert (DIST / "remoteEntry.js").is_file()
    for pet in _plugin().get_agent_pets():
        for field in ("preview", "avatar"):
            path = pet[field]
            assert not path.startswith("/") and ".." not in path
            assert (PLUGIN_ROOT / dist_path / path).is_file(), path
        with Image.open(PLUGIN_ROOT / dist_path / pet["avatar"]) as avatar:
            assert avatar.width == avatar.height


def test_every_pose_frame_is_shipped() -> None:
    """所有姿态帧（含四帧走路循环）都随源码和联邦产物一起分发。"""
    for pose in POSES:
        assert (PLUGIN_ROOT / "frontend" / "src" / "assets" / "ying" / f"{pose}.webp").is_file()
        assert (DIST / "ying" / f"{pose}.webp").is_file()


def test_both_components_are_exposed() -> None:
    """声明里的两个组件名都由联邦入口暴露。"""
    remote_entry = (DIST / "remoteEntry.js").read_text(encoding="utf-8")
    for name in ("./AgentPet", "./AgentPetSprite", "./Config", "./Page"):
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
