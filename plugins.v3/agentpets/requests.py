"""插件 API 的请求字段和输入边界"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .markets.contracts import MarketModel
from .settings import DEFAULT_PEEK_ANGLES, PEEK_ANGLE_RANGE, SCALE_RANGE, SPEED_RANGE


class SaveSettingsRequest(BaseModel):
    """只接受活动参数，避免详情页覆盖启用状态或其他插件配置"""

    model_config = ConfigDict(extra="forbid")
    scale: float = Field(ge=SCALE_RANGE[0], le=SCALE_RANGE[1], allow_inf_nan=False, description="角色大小")
    speed: float = Field(ge=SPEED_RANGE[0], le=SPEED_RANGE[1], allow_inf_nan=False, description="移动速度")
    roam: Literal["surfaces", "floor", "free"] = Field(description="自主活动范围")
    movement: Literal["auto", "fixed"] = Field(default="auto", description="自主活动或固定位置")


class AddPackRequest(BaseModel):
    """新增素材包；未上传图片时，素材描述必须提供有效的图片 URL"""

    pack: Any = Field(description="素材包 JSON 文本或已解析对象")
    image: str | None = Field(default=None, max_length=6 * 1024 * 1024, description="精灵图 data URL")


class ImportPackRequest(BaseModel):
    """导入完整素材；覆盖时核对调用方读取的修订号"""

    model_config = ConfigDict(extra="forbid")
    pack: dict[str, Any] = Field(description="完整素材描述")
    image: str = Field(min_length=1, max_length=6 * 1024 * 1024, description="精灵图 data URL")
    mode: Literal["new", "copy", "replace"] = Field(default="new", description="新增、副本或覆盖")
    expected_revision: str | None = Field(default=None, max_length=64, description="覆盖目标的原修订号")


class ImportMarketPackRequest(MarketModel):
    """只从已注册市场新增素材或导入副本，不允许远程覆盖本地素材"""

    market_id: str = Field(pattern=r"^[a-z0-9_-]{1,32}$", description="已注册市场标识")
    item_id: str = Field(min_length=1, max_length=512, description="市场内形象标识")
    mode: Literal["new", "copy"] = Field(default="new", description="新增或导入副本")


class DeletePackRequest(BaseModel):
    """删除一个非内置素材包"""

    id: str = Field(min_length=1, max_length=32, description="本地素材包 ID")


class RenamePackRequest(BaseModel):
    """核对旧名称后修改显示名称，保持素材 ID 和动作不变"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32, description="本地素材包 ID")
    name: str = Field(min_length=1, max_length=40, description="新名称")
    expected_name: str = Field(min_length=1, max_length=40, description="读取时的名称")


class SaveMappingsRequest(BaseModel):
    """核对旧映射后保存动作映射，空对象表示恢复默认"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32, description="本地素材包 ID")
    mappings: dict[str, str] = Field(max_length=44, description="新的动作映射")
    expected_mappings: dict[str, str] = Field(max_length=44, description="读取时的动作映射")


class SaveCalibrationRequest(BaseModel):
    """核对旧值后保存所有动画共用的显示校准"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32, description="本地素材包 ID")
    calibration: dict[str, float | None] = Field(description="新的显示校准")
    expected_calibration: dict[str, float | None] = Field(description="读取时的显示校准")


class CalibrationData(BaseModel):
    """Persisted display calibration returned by the read and save endpoints."""

    model_config = ConfigDict(extra="forbid")
    id: str
    calibration: dict[str, float | None]


class PeekAngles(BaseModel):
    """独立偷看角度；底边默认 0 度，左右侧边默认 35 度"""
    model_config = ConfigDict(extra="forbid")
    bottom: float = Field(default=DEFAULT_PEEK_ANGLES["bottom"], ge=PEEK_ANGLE_RANGE[0], le=PEEK_ANGLE_RANGE[1], allow_inf_nan=False)
    left: float = Field(default=DEFAULT_PEEK_ANGLES["left"], ge=PEEK_ANGLE_RANGE[0], le=PEEK_ANGLE_RANGE[1], allow_inf_nan=False)
    right: float = Field(default=DEFAULT_PEEK_ANGLES["right"], ge=PEEK_ANGLE_RANGE[0], le=PEEK_ANGLE_RANGE[1], allow_inf_nan=False)


class PetAppearance(BaseModel):
    """单只舞台形象的大小、速度与角度，不允许夹带共享设置"""
    model_config = ConfigDict(extra="forbid")
    scale: float = Field(ge=SCALE_RANGE[0], le=SCALE_RANGE[1], allow_inf_nan=False)
    speed: float = Field(ge=SPEED_RANGE[0], le=SPEED_RANGE[1], allow_inf_nan=False)
    peek_angles: PeekAngles | None = None


class SavePetSettingsRequest(PetAppearance):
    """用稳定 Pet ID 和读取时的旧值保护独立设置写入"""
    key: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    expected: PetAppearance

    @model_validator(mode="after")
    def require_angle_baseline(self):
        """写角度的新客户端必须提供角度旧值；旧客户端只更新大小速度"""
        if self.peek_angles is not None and self.expected.peek_angles is None:
            raise ValueError("修改偷看角度必须提供读取时的角度")
        return self


class SharedActivity(BaseModel):
    """所有舞台形象共用的活动方式和范围"""
    model_config = ConfigDict(extra="forbid")
    roam: Literal["surfaces", "floor", "free"]
    movement: Literal["auto", "fixed"]


class SaveSharedSettingsRequest(SharedActivity):
    """保存共享活动参数时必须同时提交读取时的旧值"""
    expected: SharedActivity


class SaveDescriptionRequest(BaseModel):
    """用旧备注校验保护局部编辑，不接受图片或动画字段"""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    description: str = Field(max_length=120)
    expected_description: str = Field(max_length=120)


class PackDescriptionData(BaseModel):
    """备注保存接口只回传素材身份与实际保存的文本"""
    id: str
    description: str
