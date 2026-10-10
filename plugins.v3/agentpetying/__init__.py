"""小映桌宠：stage 模式的 Agent 助手形象参考实现。

插件拥有整个视口图层中的角色（外观、拖拽、下落、散步、探头），点击角色经宿主
``moviepilot:agent`` 打开原生 Agent 面板；会话、模型和面板本身仍归宿主所有。
"""

from __future__ import annotations

import math
from typing import Any

from app import schemas
from app.plugins import _PluginBase
from app.sdk.logging import logger

# 形象 key 写入用户的形象选择（``<plugin_id>:<key>``），改名会让已有选择失效。
PET_KEY = "ying"

# 角色大小与移动速度的允许范围；前端设置页与形象组件使用同一组边界。
SCALE_RANGE = (0.6, 1.6)
SPEED_RANGE = (0.5, 2.0)
DEFAULT_SCALE = 1.0
DEFAULT_SPEED = 1.0


def _clamp(value: Any, bounds: tuple[float, float], default: float) -> float:
    """把配置值规整到范围内；非数字或非有限值回落默认值。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    low, high = bounds
    return round(min(max(number, low), high), 2)


class AgentPetYing(_PluginBase):
    """原创 Q 版看板娘，在视口底部生活并随 Agent 状态播放动作。"""

    plugin_name = "小映桌宠"
    plugin_desc = "原创 Q 版看板娘助手形象，可拖拽、下落、沿屏幕底边散步，并随 Agent 状态播放动作。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/agentpetying.png"
    plugin_version = "0.1.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "agentpetying_"
    plugin_order = 60
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._scale = DEFAULT_SCALE
        self._speed = DEFAULT_SPEED

    def init_plugin(self, config: dict | None = None):
        """读取启用状态与角色外观设置，越界值按边界收敛。"""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._scale = _clamp(config.get("scale"), SCALE_RANGE, DEFAULT_SCALE)
        self._speed = _clamp(config.get("speed"), SPEED_RANGE, DEFAULT_SPEED)
        logger.info(f"小映桌宠配置加载完成：enabled={self._enabled} scale={self._scale} speed={self._speed}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_render_mode():
        return "vue", "frontend/dist/assets"

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        return []

    def get_agent_pets(self) -> list[dict[str, Any]]:
        """声明 stage 形象；预览图路径相对 ``frontend/dist/assets``，由构建原样复制帧图。"""
        return [
            {
                "key": PET_KEY,
                "name": "小映",
                "description": "原创 Q 版看板娘，可拖拽、下落并沿屏幕底边散步",
                "mode": "stage",
                "component": "AgentPet",
                "api_version": 1,
                "preview": "ying/preview.png",
                "bubbles": "host",
            }
        ]

    def settings(self) -> dict[str, float]:
        """形象组件启动时读取的已保存外观设置。"""
        return {"scale": self._scale, "speed": self._speed}

    def api_settings(self):
        return schemas.Response(success=True, data=self.settings())

    def get_api(self) -> list[dict[str, Any]]:
        """形象对所有登录用户显示，读取外观设置只要求登录态；修改走宿主的插件配置保存。"""
        return [
            {
                "path": "/settings",
                "endpoint": self.api_settings,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取角色外观设置",
                "response_model": schemas.Response[dict],
            }
        ]

    def get_form(self):
        """表单由联邦配置页承担，这里只给出默认值。"""
        return [], {"enabled": False, "scale": DEFAULT_SCALE, "speed": DEFAULT_SPEED}

    def get_page(self):
        """详情页由联邦组件 ``./Page`` 提供开发预览，返回值不被使用。"""
        return None

    def stop_service(self):
        """没有后台任务需要停止。"""
        pass
