"""助手形象素材包：renderer 模式的 Agent 助手形象参考实现。

每个素材包是一张精灵图加一份动作映射 JSON。宿主负责入口的拖拽、贴边和气泡，
插件组件只按宿主传入的 action / intent 播放对应帧。
"""

from __future__ import annotations

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
# 内置素材包的预览图随构建原名复制，路径相对联邦产物目录。
BUILTIN_PREVIEW = f"packs/{BUILTIN_PACK_ID}/preview.png"


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


class AgentPetSprites(_PluginBase):
    """读取精灵图素材包，为宿主内置入口提供可替换的形象绘制。"""

    plugin_name = "助手形象素材包"
    plugin_desc = "用精灵图和动作映射 JSON 定制 Agent 助手形象，内置放映猫素材包，可在配置页添加更多素材包。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/agentpetsprites.png"
    plugin_version = "0.1.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "agentpetsprites_"
    plugin_order = 61
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._builtin: dict[str, Any] | None = None

    def init_plugin(self, config: dict | None = None):
        self._enabled = bool((config or {}).get("enabled", False))
        logger.info(f"助手形象素材包配置加载完成：enabled={self._enabled}")

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
        """内置素材包描述；读取失败时退回只有名称的最小声明，不影响用户素材包。"""
        if self._builtin is None:
            try:
                self._builtin = load_builtin_pack(PLUGIN_DIR / DIST_PATH)
            except (OSError, PackError) as exc:
                logger.warning(f"助手形象素材包：内置素材包读取失败：{exc}")
                return {"id": BUILTIN_PACK_ID, "name": "放映猫", "description": "", "random_actions": []}
        return self._builtin

    def get_agent_pets(self) -> list[dict[str, Any]]:
        """内置素材包和每个用户素材包各声明一个 renderer 形象，key 即素材包 ID。"""
        builtin = self.builtin_pack()
        pets = [self._pet(BUILTIN_PACK_ID, builtin, BUILTIN_PREVIEW)]
        for record in self._store().list():
            pets.append(self._pet(record["id"], record, record.get("preview") or None))
        return pets

    @staticmethod
    def _pet(key: str, pack: dict[str, Any], preview: str | None) -> dict[str, Any]:
        item: dict[str, Any] = {
            "key": key,
            "name": pack["name"],
            "description": pack.get("description") or "",
            "mode": "renderer",
            "component": "AgentPet",
            "api_version": 1,
        }
        if preview:
            item["preview"] = preview
        if pack.get("random_actions"):
            item["random_actions"] = list(pack["random_actions"])
        return item

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
        """形象组件读取的完整素材包；内置素材包的精灵图由前端从联邦产物加载。"""
        if key == BUILTIN_PACK_ID:
            pack = dict(self.builtin_pack())
            return schemas.Response(success=True, data={"pack": pack, "builtin": True, "sheet_src": ""})
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
        logger.info(f"助手形象素材包：已添加 {record['id']}（{record['source']}）")
        return schemas.Response(success=True, data=self._summary(record))

    def api_delete_pack(self, request: DeletePackRequest):
        if request.id == BUILTIN_PACK_ID:
            return schemas.Response(success=False, message="内置素材包不能删除")
        if not self._store().remove(request.id):
            return schemas.Response(success=False, message=f"素材包 {request.id} 不存在")
        logger.info(f"助手形象素材包：已删除 {request.id}")
        return schemas.Response(success=True)

    def get_api(self) -> list[dict[str, Any]]:
        """读取接口对登录用户开放（形象对所有用户显示）；写接口额外要求管理员。"""
        admin = [Depends(require_admin)]
        return [
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
        """表单由联邦配置页承担；素材包存于插件数据，不进入配置。"""
        return [], {"enabled": False}

    def get_page(self):
        """详情页由联邦组件 ``./Page`` 提供开发预览，返回值不被使用。"""
        return None

    def stop_service(self):
        """没有后台任务需要停止。"""
        pass
