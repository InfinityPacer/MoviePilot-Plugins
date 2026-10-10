"""小映桌宠的形象声明、外观设置与联邦产物合同测试。"""

from __future__ import annotations

import re
from pathlib import Path

from app.plugins.agentpetying import AgentPetYing
from app.runtime.extensions.plugin.contracts import supports_plugin_hook

PLUGIN_ROOT = Path(__file__).parents[3] / "plugins.v3" / "agentpetying"
DIST = PLUGIN_ROOT / "frontend" / "dist" / "assets"
POSES = [
    "idle", "blink", "talk", "think", "jump", "wave", "held", "fall",
    "sit", "walk1", "walk2", "doze", "confused", "alert", "victory", "busy",
]


def _plugin(config: dict | None = None) -> AgentPetYing:
    plugin = AgentPetYing()
    plugin.init_plugin(config)
    return plugin


def test_declares_one_stage_pet_with_host_bubbles() -> None:
    """声明字段符合契约 v1：stage 模式、宿主气泡、默认暴露名。"""
    pets = _plugin({"enabled": True}).get_agent_pets()

    assert pets == [
        {
            "key": "ying",
            "name": "小映",
            "description": "原创 Q 版看板娘，可拖拽、下落并沿屏幕底边散步",
            "mode": "stage",
            "component": "AgentPet",
            "api_version": 1,
            "preview": "ying/preview.png",
            "bubbles": "host",
        }
    ]
    assert re.fullmatch(r"[a-z0-9_-]{1,32}", pets[0]["key"])
    assert supports_plugin_hook(AgentPetYing(), "get_agent_pets")


def test_preview_path_points_at_a_built_frame() -> None:
    """预览路径相对 remoteEntry 所在目录，且构建产物里真实存在。"""
    preview = _plugin().get_agent_pets()[0]["preview"]
    _, dist_path = AgentPetYing.get_render_mode()

    assert dist_path == "frontend/dist/assets"
    assert not preview.startswith("/") and ".." not in preview
    assert (PLUGIN_ROOT / dist_path / preview).is_file()
    assert (DIST / "remoteEntry.js").is_file()


def test_every_pose_frame_is_shipped() -> None:
    """所有姿态帧都随源码和联邦产物一起分发。"""
    for pose in POSES:
        assert (PLUGIN_ROOT / "frontend" / "src" / "assets" / "ying" / f"{pose}.webp").is_file()
        assert (DIST / "ying" / f"{pose}.webp").is_file()


def test_settings_default_and_clamp() -> None:
    """外观设置缺省为 1 倍，越界和非法值按边界收敛。"""
    assert _plugin().settings() == {"scale": 1.0, "speed": 1.0}
    assert _plugin({"scale": 9, "speed": 0.1}).settings() == {"scale": 1.6, "speed": 0.5}
    assert _plugin({"scale": "abc", "speed": float("nan")}).settings() == {"scale": 1.0, "speed": 1.0}


def test_settings_api_requires_login_and_returns_saved_values() -> None:
    """形象组件读取设置的接口只要求登录态，并返回已保存的值。"""
    plugin = _plugin({"enabled": True, "scale": 1.25, "speed": 0.8})
    routes = plugin.get_api()

    assert [(route["path"], route["methods"], route["auth"]) for route in routes] == [("/settings", ["GET"], "bear")]
    response = routes[0]["endpoint"]()
    assert response.success is True
    assert response.data == {"scale": 1.25, "speed": 0.8}


def test_form_defaults_match_settings_and_state_follows_enabled() -> None:
    """表单默认值与设置默认值一致，启用状态由配置决定。"""
    _, defaults = AgentPetYing().get_form()

    assert defaults == {"enabled": False, "scale": 1.0, "speed": 1.0}
    assert _plugin({"enabled": True}).get_state() is True
    assert _plugin({}).get_state() is False
    assert AgentPetYing.get_render_mode()[0] == "vue"
