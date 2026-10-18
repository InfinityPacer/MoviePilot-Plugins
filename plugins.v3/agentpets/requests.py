"""插件 API 的请求字段和输入边界"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .markets.contracts import MarketModel
from .settings import SCALE_RANGE, SPEED_RANGE


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
    mappings: dict[str, str] = Field(max_length=43, description="新的动作映射")
    expected_mappings: dict[str, str] = Field(max_length=43, description="读取时的动作映射")


class SaveCalibrationRequest(BaseModel):
    """核对旧值后保存所有动画共用的显示校准"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32, description="本地素材包 ID")
    calibration: dict[str, float] = Field(description="新的显示校准")
    expected_calibration: dict[str, float] = Field(description="读取时的显示校准")
