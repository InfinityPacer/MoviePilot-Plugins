"""自动发现本地供应商类型并为插件实例创建独立市场注册表"""

from importlib import import_module
from inspect import isabstract
from pkgutil import iter_modules
from typing import Iterable, TypeVar

from . import providers
from .contracts import MarketAdapter, MarketError, MarketInfo

AdapterType = TypeVar("AdapterType", bound=MarketAdapter)
_market_types: dict[str, type[MarketAdapter]] = {}


def register_market(adapter_type: type[AdapterType]) -> type[AdapterType]:
    """显式登记具体供应商类型，校验身份且不创建实例，返回原类型以保留类行为"""
    if not isinstance(adapter_type, type) or not issubclass(adapter_type, MarketAdapter):
        raise MarketError("市场供应商必须实现 MarketAdapter")
    market_id = adapter_type.market_id
    try:
        info = MarketInfo(id=market_id, name=market_id)
        if market_id != info.id:
            raise ValueError("非规范标识")
    except ValueError as exc:
        raise MarketError("市场类声明的标识无效") from exc
    if isabstract(adapter_type):
        raise MarketError("抽象市场类不能登记为供应商")
    if market_id in _market_types:
        raise MarketError(f"市场 {market_id} 已注册")
    _market_types[market_id] = adapter_type
    return adapter_type


class MarketRegistry:
    """持有插件实例独享的市场适配器；不根据请求导入模块或访问任意 URL"""

    def __init__(self, adapters: Iterable[MarketAdapter] = ()) -> None:
        """建立实例独享的市场索引，按传入顺序注册并拒绝重复标识"""
        self._adapters: dict[str, MarketAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: MarketAdapter) -> None:
        """注册适配器，重复市场 ID 直接报错以避免静默替换"""
        market_id = adapter.info.id
        if type(adapter).market_id and type(adapter).market_id != market_id:
            raise MarketError("市场类声明的标识与展示信息不一致")
        if market_id in self._adapters:
            raise MarketError(f"市场 {market_id} 已注册")
        self._adapters[market_id] = adapter

    def list(self) -> list[MarketInfo]:
        """按注册顺序返回市场信息；尚未接入任何市场时返回空列表"""
        return [adapter.info for adapter in self._adapters.values()]

    def get(self, market_id: str) -> MarketAdapter:
        """只解析已注册市场，未知标识返回可展示的错误"""
        try:
            return self._adapters[market_id]
        except KeyError as exc:
            raise MarketError("该形象市场尚未接入") from exc


def create_market_registry() -> MarketRegistry:
    """导入受信任本地供应商模块并装配已登记类型，新增供应商无需修改工厂"""
    modules = sorted(iter_modules(providers.__path__), key=lambda item: item.name)
    for module in modules:
        if not module.name.startswith("_"):
            import_module(f"{providers.__name__}.{module.name}")
    return MarketRegistry(_market_types[market_id]() for market_id in sorted(_market_types))
