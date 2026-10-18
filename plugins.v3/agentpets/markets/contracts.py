"""在线形象市场契约；适配器只发现和转换素材，本地导入由 PackStore 负责"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from ..packs.constants import MAX_IMAGE_BYTES


class MarketError(ValueError):
    """可向用户展示的市场访问或素材转换错误，不应包含凭据或上游响应正文"""


class MarketModel(BaseModel):
    """市场边界的严格数据模型，拒绝未知字段"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class MarketInfo(MarketModel):
    """市场身份信息；id 是长期稳定的插件内标识，不是模块名或访问地址"""

    id: str = Field(pattern=r"^[a-z0-9_-]{1,32}$", description="市场标识")
    name: str = Field(min_length=1, max_length=80, description="市场名称")
    description: str = Field(default="", max_length=500, description="市场说明")
    homepage: HttpUrl | None = Field(default=None, description="市场主页")


class MarketQuery(MarketModel):
    """单个市场的分页搜索条件；空关键词表示浏览，页码从 1 开始"""

    keyword: str = Field(default="", max_length=200, description="搜索关键词")
    page: int = Field(default=1, ge=1, le=10000, description="页码")
    page_size: int = Field(default=20, ge=1, le=50, description="每页条数")


class MarketItem(MarketModel):
    """远程形象摘要；id 仅在所属市场内唯一，与本地素材包 ID 相互独立"""

    id: str = Field(min_length=1, max_length=512, description="市场内形象标识")
    name: str = Field(min_length=1, max_length=120, description="形象名称")
    description: str = Field(default="", max_length=2000, description="形象说明")
    author: str = Field(default="", max_length=200, description="作者署名")
    license: str = Field(default="", max_length=200, description="上游声明的素材许可，空值表示未知")
    preview: HttpUrl | None = Field(default=None, description="预览图片地址")
    source_url: HttpUrl | None = Field(default=None, description="形象来源页面")


class MarketPage(MarketModel):
    """市场分页结果；总量未知时保留 None，以 has_more 表达能否继续翻页"""

    items: list[MarketItem] = Field(default_factory=list, max_length=50, description="当前页形象")
    total: int | None = Field(default=None, ge=0, description="匹配总条数，未知时为空")
    has_more: bool = Field(default=False, description="是否还有下一页")

    @model_validator(mode="after")
    def _check_total(self) -> MarketPage:
        """总量已知时不得小于本页结果数，未知总量保留为空"""
        if self.total is not None and self.total < len(self.items):
            raise ValueError("市场总条数不能少于当前页条数")
        return self


class MarketPack(MarketModel):
    """已下载并转换的素材；pack 必须符合 parse_pack，图片仍由 PackStore 校验"""

    pack: dict[str, Any] = Field(description="AgentPets 规范素材描述，不包含下载地址指令")
    image: bytes = Field(strict=True, min_length=1, max_length=MAX_IMAGE_BYTES, description="原始精灵图字节")


class MarketAdapter(ABC):
    """同步市场接口；网络实现须自行限制超时、重定向、响应与解压大小并遵守宿主 URL 安全策略

    适配器负责上游搜索、下载和格式转换，不写插件配置、文件或 PackStore
    可预期的上游失败应转换为 MarketError，消息中不得泄露凭据
    基类只定义契约，具体供应商由注册模块的装饰器显式登记
    """

    market_id: ClassVar[str] = ""

    @property
    @abstractmethod
    def info(self) -> MarketInfo:
        """返回稳定的市场身份与展示信息"""
        raise NotImplementedError

    @abstractmethod
    def search(self, query: MarketQuery) -> MarketPage:
        """浏览或搜索单个市场；结果条数不能超过 query.page_size"""
        raise NotImplementedError

    @abstractmethod
    def fetch(self, item_id: str) -> MarketPack:
        """按市场内标识获取完整素材并转换；未知形象或不支持的格式抛出 MarketError"""
        raise NotImplementedError
