"""助手形象：一个插件注册多个 Agent 助手形象的参考实现。

- 小映（key ``ying``）是 stage 模式的全屏角色，插件拥有整个视口图层里的角色：
  拖拽、下落、站在页面元素上、散步和探头都由联邦组件 ``./AgentPet`` 完成。
- 素材包是 renderer 模式的入口外观，内置放映猫（key ``projector-cat``）和用户添加的
  每个素材包各是一个形象，共用联邦组件 ``./AgentPetSprite``，组件按 ``pet.key`` 读取素材包。

宿主保留 Agent 面板、会话、模型和回退；插件只决定形象的外观与动作。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import schemas
from app.plugins import _PluginBase
from app.sdk.logging import logger
from app.sdk.security import verify_token

from .pack import BUILTIN_PACK_ID, PackError, PackStore, load_builtin_pack

PLUGIN_DIR = Path(__file__).resolve().parent
DIST_PATH = "frontend/dist/assets"

# 小映的形象 key 写入用户的形象选择（``<plugin_id>:<key>``），改名会让已有选择失效。
STAGE_KEY = "ying"
# 以下图片路径都相对联邦产物目录（remoteEntry.js 所在目录），由构建按原名复制。
STAGE_PREVIEW = "ying/preview.png"
STAGE_AVATAR = "ying/avatar.png"
BUILTIN_PREVIEW = f"packs/{BUILTIN_PACK_ID}/preview.png"
BUILTIN_AVATAR = f"packs/{BUILTIN_PACK_ID}/avatar.png"

# 小映的角色大小与移动速度范围；前端设置页与形象组件使用同一组边界。
SCALE_RANGE = (0.6, 1.6)
SPEED_RANGE = (0.5, 2.0)
# 活动范围：surfaces 站在页面元素上，floor 只在底边，free 没有重力、自由停放。
ROAM_MODES = ("surfaces", "floor", "free")
DEFAULT_SETTINGS = {"scale": 1.0, "speed": 1.0, "roam": "surfaces"}


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


def require_admin(payload=Depends(verify_token)):
    """添加和删除素材包会写插件数据目录，只允许管理员调用。"""
    if not payload.super_user:
        raise HTTPException(status_code=403, detail="用户权限不足")
    return payload


class AddPackRequest(BaseModel):
    """配置页添加素材包的请求。"""

    pack: Any  # 素材包 JSON 文本或已解析对象
    image: str | None = Field(default=None, max_length=6 * 1024 * 1024)  # 精灵图 data URL；为空时 sheet 必须是 URL


class DeletePackRequest(BaseModel):
    """删除用户素材包的请求。"""

    id: str = Field(min_length=1, max_length=32)  # 素材包 ID


class AgentPets(_PluginBase):
    """为 Agent 助手提供小映全屏角色和精灵图素材包两类形象。"""

    plugin_name = "助手形象"
    plugin_desc = "为 Agent 助手提供可替换的形象：全屏活动的看板娘小映，以及用精灵图素材包定制的入口外观。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/agentpets.png"
    plugin_version = "0.1.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "agentpets_"
    plugin_order = 60
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._settings = dict(DEFAULT_SETTINGS)
        self._builtin: dict[str, Any] | None = None

    def init_plugin(self, config: dict | None = None):
        """读取启用状态与小映设置，越界值按边界收敛。"""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        roam = config.get("roam")
        self._settings = {
            "scale": _clamp(config.get("scale"), SCALE_RANGE, DEFAULT_SETTINGS["scale"]),
            "speed": _clamp(config.get("speed"), SPEED_RANGE, DEFAULT_SETTINGS["speed"]),
            "roam": roam if roam in ROAM_MODES else DEFAULT_SETTINGS["roam"],
        }
        logger.info(f"助手形象配置加载完成：enabled={self._enabled} settings={self._settings}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_render_mode():
        return "vue", DIST_PATH

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        return []

    def _store(self) -> PackStore:
        return PackStore(self.get_data, self.save_data, self.get_data_path())

    def builtin_pack(self) -> dict[str, Any]:
        """内置素材包描述；读取失败时退回只有名称的最小声明，不影响其他形象。"""
        if self._builtin is None:
            try:
                self._builtin = load_builtin_pack(PLUGIN_DIR / DIST_PATH)
            except (OSError, PackError) as exc:
                logger.warning(f"助手形象：内置素材包读取失败：{exc}")
                return {"id": BUILTIN_PACK_ID, "name": "放映猫", "description": "", "random_actions": []}
        return self._builtin

    def get_agent_pets(self) -> list[dict[str, Any]]:
        """一个插件注册多个形象：小映、内置素材包、每个用户素材包各一项，key 在插件内唯一。"""
        pets = [
            {
                "key": STAGE_KEY,
                "name": "小映",
                "description": "原创 Q 版看板娘，可拖拽，会站在页面元素上散步",
                "mode": "stage",
                "component": "AgentPet",
                "api_version": 1,
                "preview": STAGE_PREVIEW,
                "avatar": STAGE_AVATAR,
                "bubbles": "host",
            },
            self._sprite_pet(BUILTIN_PACK_ID, self.builtin_pack(), BUILTIN_PREVIEW, BUILTIN_AVATAR),
        ]
        for record in self._store().list():
            pets.append(
                self._sprite_pet(record["id"], record, record.get("preview") or None, record.get("avatar") or None)
            )
        return pets

    @staticmethod
    def _sprite_pet(key: str, pack: dict[str, Any], preview: str | None, avatar: str | None) -> dict[str, Any]:
        """素材包形象共用 ``./AgentPetSprite``；URL 方式的素材包没写头像时不声明 avatar。"""
        item: dict[str, Any] = {
            "key": key,
            "name": pack["name"],
            "description": pack.get("description") or "",
            "mode": "renderer",
            "component": "AgentPetSprite",
            "api_version": 1,
        }
        if preview:
            item["preview"] = preview
        if avatar:
            item["avatar"] = avatar
        if pack.get("random_actions"):
            item["random_actions"] = list(pack["random_actions"])
        return item

    def settings(self) -> dict[str, Any]:
        """小映启动时读取的已保存设置。"""
        return dict(self._settings)

    def api_settings(self):
        return schemas.Response(success=True, data=self.settings())

    @staticmethod
    def _summary(record: dict[str, Any], builtin: bool = False) -> dict[str, Any]:
        return {
            "id": record["id"],
            "name": record["name"],
            "description": record.get("description") or "",
            "builtin": builtin,
            "source": "builtin" if builtin else record.get("source", ""),
            "preview": BUILTIN_PREVIEW if builtin else record.get("preview", ""),
            "grid": record.get("grid"),
            "frame_count": len(record.get("frames") or {}),
            "action_count": len(record.get("actions") or {}),
        }

    def api_packs(self):
        """素材包列表，内置在前。"""
        packs = [self._summary(self.builtin_pack(), builtin=True)]
        packs += [self._summary(record) for record in self._store().list()]
        return schemas.Response(success=True, data=packs)

    def api_pack(self, key: str = BUILTIN_PACK_ID):
        """素材包组件读取的完整素材包；内置素材包的精灵图由前端从联邦产物加载。"""
        if key == BUILTIN_PACK_ID:
            return schemas.Response(success=True, data={"pack": dict(self.builtin_pack()), "builtin": True, "sheet_src": ""})
        store = self._store()
        record = store.get(key)
        if not record:
            return schemas.Response(success=False, message=f"素材包 {key} 不存在")
        try:
            sheet_src = store.sheet_src(record)
        except PackError as exc:
            return schemas.Response(success=False, message=str(exc))
        pack = {name: record.get(name) for name in ("id", "name", "description", "grid", "frames", "actions", "random_actions")}
        return schemas.Response(success=True, data={"pack": pack, "builtin": False, "sheet_src": sheet_src})

    def api_add_pack(self, request: AddPackRequest):
        try:
            record = self._store().add(request.pack, request.image)
        except PackError as exc:
            return schemas.Response(success=False, message=str(exc))
        logger.info(f"助手形象：已添加素材包 {record['id']}（{record['source']}）")
        return schemas.Response(success=True, data=self._summary(record))

    def api_delete_pack(self, request: DeletePackRequest):
        if request.id == BUILTIN_PACK_ID:
            return schemas.Response(success=False, message="内置素材包不能删除")
        if not self._store().remove(request.id):
            return schemas.Response(success=False, message=f"素材包 {request.id} 不存在")
        logger.info(f"助手形象：已删除素材包 {request.id}")
        return schemas.Response(success=True)

    def get_api(self) -> list[dict[str, Any]]:
        """形象对所有登录用户显示，读取接口只要求登录；素材包写接口额外要求管理员。"""
        admin = [Depends(require_admin)]
        return [
            {
                "path": "/settings",
                "endpoint": self.api_settings,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取小映设置",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs",
                "endpoint": self.api_packs,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "素材包列表",
                "response_model": schemas.Response[list],
            },
            {
                "path": "/pack",
                "endpoint": self.api_pack,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取素材包与精灵图",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs",
                "endpoint": self.api_add_pack,
                "methods": ["POST"],
                "auth": "bear",
                "dependencies": list(admin),
                "summary": "添加素材包",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs/delete",
                "endpoint": self.api_delete_pack,
                "methods": ["POST"],
                "auth": "bear",
                "dependencies": list(admin),
                "summary": "删除素材包",
                "response_model": schemas.Response[dict],
            },
        ]

    def get_form(self):
        """表单由联邦配置页承担，这里只给出默认值；素材包存于插件数据，不进入配置。"""
        return [], {"enabled": False, **DEFAULT_SETTINGS}

    def get_page(self):
        """详情页由联邦组件 ``./Page`` 提供开发预览，返回值不被使用。"""
        return None

    def stop_service(self):
        """没有后台任务需要停止。"""
        pass
