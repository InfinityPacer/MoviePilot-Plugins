"""助手形象：一个插件注册多个 Agent 助手形象的参考实现。

- 小映（key ``ying``）是 stage 模式的全屏角色，插件拥有整个视口图层里的角色：
  拖拽、下落、站在页面元素上、散步和探头都由联邦组件 ``./AgentPet`` 完成。
- Codex Pet 素材包由 ``./AgentPetCodex`` 复用小映舞台，支持缩放、拖拽与自主漫游。
- 普通素材包是 renderer 模式的入口外观，共用 ``./AgentPetSprite``；内置放映猫与用户
  素材包各是一个形象，组件按 ``pet.key`` 读取素材包。

宿主保留 Agent 面板、会话、模型和回退；插件只决定形象的外观与动作。
"""

from __future__ import annotations

import base64
import math
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import schemas
from app.plugins import _PluginBase
from app.sdk.logging import logger
from app.sdk.security import verify_token

from .pack import BUILTIN_PACK_ID, PackError, PackStore, codex_pet_version, load_builtin_pack, parse_calibration, suggest_calibration, pack_revision

PLUGIN_DIR = Path(__file__).resolve().parent
DIST_PATH = "frontend/dist/assets"

# 小映的形象 key 写入用户的形象选择（``<plugin_id>:<key>``），改名会让已有选择失效。
STAGE_KEY = "ying"
# 以下图片路径都相对联邦产物目录（remoteEntry.js 所在目录），由构建按原名复制。
STAGE_PREVIEW = "ying/preview.png"
STAGE_AVATAR = "ying/avatar.png"
BUILTIN_PREVIEW = f"packs/{BUILTIN_PACK_ID}/preview.png"
BUILTIN_AVATAR = f"packs/{BUILTIN_PACK_ID}/avatar.png"

# 全屏角色的大小与移动速度范围；小映与 Codex Pet 使用同一组设置。
SCALE_RANGE = (0.6, 1.6)
SPEED_RANGE = (0.5, 2.0)
# 活动范围：surfaces 站在页面元素上，floor 只在底边，free 没有重力、自由停放。
ROAM_MODES = ("surfaces", "floor", "free")
DEFAULT_SETTINGS = {"scale": 1.0, "speed": 1.0, "roam": "surfaces", "movement": "auto"}


@lru_cache(maxsize=4)
def _builtin_image(path: str, size: int) -> str:
    """缓存内置小图的 data URL，供宿主卡片和消息头像直接显示。"""
    from PIL import Image

    try:
        with Image.open(PLUGIN_DIR / DIST_PATH / path) as source:
            image = source.convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=85, method=6)
        return "data:image/webp;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except (OSError, ValueError) as exc:
        # 缺图不影响其他形象注册；保留原路径，插件重载后重新尝试生成。
        logger.warning(f"助手形象：内置图片读取失败，保留原路径 {path}：{exc}")
        return path


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


class SaveSettingsRequest(BaseModel):
    """仅接受活动参数，避免详情页覆盖启用状态或其他插件配置。"""

    model_config = ConfigDict(extra="forbid")
    scale: float = Field(ge=SCALE_RANGE[0], le=SCALE_RANGE[1], allow_inf_nan=False)
    speed: float = Field(ge=SPEED_RANGE[0], le=SPEED_RANGE[1], allow_inf_nan=False)
    roam: Literal["surfaces", "floor", "free"]
    movement: Literal["auto", "fixed"] = "auto"


class AddPackRequest(BaseModel):
    """配置页添加素材包的请求。"""

    pack: Any  # 素材包 JSON 文本或已解析对象
    image: str | None = Field(default=None, max_length=6 * 1024 * 1024)  # 精灵图 data URL；为空时 sheet 必须是 URL


class ImportPackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pack: dict[str, Any]
    image: str = Field(min_length=1, max_length=6 * 1024 * 1024)
    mode: Literal["new", "copy", "replace"] = "new"
    expected_revision: str | None = Field(default=None, max_length=64)


class DeletePackRequest(BaseModel):
    """删除用户素材包的请求。"""

    id: str = Field(min_length=1, max_length=32)  # 素材包 ID


class RenamePackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=40)
    expected_name: str = Field(min_length=1, max_length=40)


class SaveMappingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    mappings: dict[str, str] = Field(max_length=43)
    expected_mappings: dict[str, str] = Field(max_length=43)


class SaveCalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    calibration: dict[str, float]
    expected_calibration: dict[str, float]


class AgentPets(_PluginBase):
    """为 Agent 助手提供小映全屏角色和精灵图素材包两类形象。"""

    plugin_name = "助手形象"
    plugin_desc = "为 Agent 助手换上小映或自定义精灵图形象。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/agentpets.png"
    plugin_version = "0.1.3"
    plugin_author = "InfinityPacer,Kurisu"
    author_url = "https://github.com/z2561221"
    plugin_config_prefix = "agentpets_"
    plugin_order = 60
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._settings = dict(DEFAULT_SETTINGS)
        self._builtin: dict[str, Any] | None = None

    def init_plugin(self, config: dict | None = None):
        """读取启用状态与全屏角色设置，越界值按边界收敛。"""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        roam = config.get("roam")
        self._settings = {
            "scale": _clamp(config.get("scale"), SCALE_RANGE, DEFAULT_SETTINGS["scale"]),
            "speed": _clamp(config.get("speed"), SPEED_RANGE, DEFAULT_SETTINGS["speed"]),
            "roam": roam if roam in ROAM_MODES else DEFAULT_SETTINGS["roam"],
            "movement": "fixed" if config.get("movement") == "fixed" else "auto",
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
                "preview": _builtin_image(STAGE_PREVIEW, 320),
                "avatar": _builtin_image(STAGE_AVATAR, 128),
                "bubbles": "host",
            },
            self._sprite_pet(
                BUILTIN_PACK_ID, self.builtin_pack(),
                _builtin_image(BUILTIN_PREVIEW, 320), _builtin_image(BUILTIN_AVATAR, 128),
            ),
        ]
        for record in self._store().list():
            pets.append(
                self._sprite_pet(record["id"], record, record.get("preview") or None, record.get("avatar") or None)
            )
        return pets

    @staticmethod
    def _sprite_pet(key: str, pack: dict[str, Any], preview: str | None, avatar: str | None) -> dict[str, Any]:
        """Codex Pet 进入舞台；普通素材包保留入口外观，形象 key 不变。"""
        stage = codex_pet_version(pack) is not None
        item: dict[str, Any] = {
            "key": key,
            "name": pack["name"],
            "description": pack.get("description") or "",
            "mode": "stage" if stage else "renderer",
            "component": "AgentPetCodex" if stage else "AgentPetSprite",
            "api_version": 1,
        }
        if preview:
            item["preview"] = preview
        if avatar:
            item["avatar"] = avatar
        if stage:
            item["bubbles"] = "host"
        elif pack.get("random_actions"):
            item["random_actions"] = list(pack["random_actions"])
        return item

    def settings(self) -> dict[str, Any]:
        """全屏角色启动时读取的已保存设置。"""
        return dict(self._settings)

    def api_settings(self):
        return schemas.Response(success=True, data=self.settings())

    def api_editor(self):
        """编辑页只取得必要的状态与形象，不暴露其他配置。"""
        pets = [
            {
                "key": pet["key"],
                "name": pet["name"],
                "description": pet.get("description", ""),
                "mode": pet["mode"],
                "preview": pet.get("avatar") or pet.get("preview") or "",
                "builtin": pet["key"] in (STAGE_KEY, BUILTIN_PACK_ID),
            }
            for pet in self.get_agent_pets()
        ]
        return schemas.Response(success=True, data={
            "enabled": self._enabled, "settings": self.settings(), "pets": pets,
        })

    def api_save_settings(self, request: SaveSettingsRequest):
        """合并并回读活动设置；持久化失败时不改变运行中的参数。"""
        values = request.model_dump()
        values["scale"] = round(values["scale"], 2)
        values["speed"] = round(values["speed"], 2)
        try:
            config = dict(self.get_config() or {})
            if "movement" not in request.model_fields_set:
                values["movement"] = "fixed" if config.get("movement") == "fixed" else "auto"
            config.update(values)
            if self.update_config(config) is False:
                return schemas.Response(success=False, message="活动设置保存失败，请重试")
            persisted = self.get_config() or {}
            if any(persisted.get(key) != value for key, value in values.items()):
                return schemas.Response(success=False, message="活动设置回读不一致，请刷新后重试")
        except (OSError, RuntimeError, ValueError):
            logger.error("助手形象：保存活动设置失败")
            return schemas.Response(success=False, message="活动设置保存失败，请查看插件日志")
        self._settings = values
        return schemas.Response(success=True, data=self.settings())

    @staticmethod
    def _summary(record: dict[str, Any], builtin: bool = False) -> dict[str, Any]:
        return {
            "id": record["id"],
            "name": record["name"],
            "description": record.get("description") or "",
            "builtin": builtin,
            "mode": "stage" if codex_pet_version(record) else "renderer",
            "source": "builtin" if builtin else record.get("source", ""),
            "preview": BUILTIN_PREVIEW if builtin else record.get("preview", ""),
            "grid": record.get("grid"),
            "frame_count": len(record.get("frames") or {}),
            "action_count": len(record.get("actions") or {}),
            "revision": pack_revision(record),
            "mapping_count": len(record.get("action_mappings") or {}),
            "calibrated": parse_calibration(record.get("calibration")) != parse_calibration(),
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
        pack["preview"] = record.get("preview", "")
        pack["avatar"] = record.get("avatar", "")
        pack["action_mappings"] = record.get("action_mappings", {})
        pack["calibration"] = parse_calibration(record.get("calibration"))
        version = codex_pet_version(record)
        if version:
            pack["codex_version"] = version
        return schemas.Response(success=True, data={"pack": pack, "builtin": False, "sheet_src": sheet_src})

    def api_add_pack(self, request: AddPackRequest):
        try:
            record = self._store().add(request.pack, request.image)
        except PackError as exc:
            return schemas.Response(success=False, message=str(exc))
        except (OSError, RuntimeError):
            logger.error("助手形象：添加素材包失败")
            return schemas.Response(success=False, message="添加素材包失败，请刷新核对后重试")
        logger.info(f"助手形象：已添加素材包 {record['id']}（{record['source']}）")
        return schemas.Response(success=True, data=self._summary(record))

    def api_import_pack(self, request: ImportPackRequest):
        try:
            record = self._store().import_pack(request.pack, request.image, request.mode, request.expected_revision)
            return schemas.Response(success=True, data=self._summary(record))
        except (PackError, OSError, RuntimeError) as exc:
            return schemas.Response(success=False, message=str(exc))

    def api_rename_pack(self, request: RenamePackRequest):
        try:
            record = self._store().update(request.id, name=request.name, expected_name=request.expected_name)
        except (PackError, OSError, RuntimeError) as exc:
            return schemas.Response(success=False, message=str(exc))
        return schemas.Response(success=True, data=self._summary(record))

    def api_save_mappings(self, request: SaveMappingsRequest):
        try:
            record = self._store().update(request.id, mappings=request.mappings,
                                         expected_mappings=request.expected_mappings)
        except (PackError, OSError, RuntimeError) as exc:
            return schemas.Response(success=False, message=str(exc))
        return schemas.Response(success=True, data={"id": record["id"], "mappings": record.get("action_mappings", {})})

    def api_save_calibration(self, request: SaveCalibrationRequest):
        try:
            record = self._store().calibrate(request.id, request.calibration, request.expected_calibration)
            return schemas.Response(success=True, data={"id": record["id"], "calibration": record["calibration"]})
        except (PackError, OSError, RuntimeError) as exc:
            return schemas.Response(success=False, message=str(exc))

    def api_suggest_calibration(self, key: str):
        try:
            store = self._store()
            record = store.get(key)
            path = store.image_path(record) if record else None
            if not record or not path:
                raise PackError("自动识别需要已上传的图片；此素材仍可手动校准")
            return schemas.Response(success=True, data=suggest_calibration(path.read_bytes(), record))
        except (PackError, OSError, RuntimeError) as exc:
            return schemas.Response(success=False, message=str(exc))

    def api_delete_pack(self, request: DeletePackRequest):
        if request.id == BUILTIN_PACK_ID:
            return schemas.Response(success=False, message="内置素材包不能删除")
        try:
            if not self._store().remove(request.id):
                return schemas.Response(success=False, message=f"素材包 {request.id} 不存在")
        except PackError as exc:
            return schemas.Response(success=False, message=str(exc))
        except (OSError, RuntimeError):
            logger.error("助手形象：删除素材包失败")
            return schemas.Response(success=False, message="删除素材包失败，请刷新核对后重试")
        logger.info(f"助手形象：已删除素材包 {request.id}")
        return schemas.Response(success=True)

    def get_api(self) -> list[dict[str, Any]]:
        """形象对所有登录用户显示，读取接口只要求登录；素材包写接口额外要求管理员。"""
        admin = [Depends(require_admin)]
        return [
            {
                "path": "/packs/import", "endpoint": self.api_import_pack, "methods": ["POST"],
                "auth": "bear", "dependencies": list(admin), "summary": "导入或更新完整素材包",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs/calibration", "endpoint": self.api_save_calibration, "methods": ["POST"],
                "auth": "bear", "dependencies": list(admin), "summary": "保存素材显示校准",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs/calibration/suggest", "endpoint": self.api_suggest_calibration, "methods": ["GET"],
                "auth": "bear", "summary": "读取显示校准建议",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs/rename", "endpoint": self.api_rename_pack, "methods": ["POST"],
                "auth": "bear", "dependencies": list(admin), "summary": "重命名导入的 Codex Pet",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/packs/mappings", "endpoint": self.api_save_mappings, "methods": ["POST"],
                "auth": "bear", "dependencies": list(admin), "summary": "保存 Codex Pet 动作映射",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/editor",
                "endpoint": self.api_editor,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取形象编辑页",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/settings",
                "endpoint": self.api_save_settings,
                "methods": ["POST"],
                "auth": "bear",
                "dependencies": list(admin),
                "summary": "保存全屏角色活动设置",
                "response_model": schemas.Response[dict],
            },
            {
                "path": "/settings",
                "endpoint": self.api_settings,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取全屏角色设置",
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
        """详情页由联邦组件 ``./Page`` 提供形象调整、实时预览与应用，返回值不被使用。"""
        return None

    def stop_service(self):
        """没有后台任务需要停止。"""
        pass
