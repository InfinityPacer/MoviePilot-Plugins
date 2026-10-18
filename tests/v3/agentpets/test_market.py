"""市场接口与注册隔离；所有适配器均为内存实现，不访问网络"""

import sys
from copy import deepcopy
from io import BytesIO
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.plugins.agentpets import AgentPets, require_admin
from app.plugins.agentpets.markets import registry as market_registry
from app.plugins.agentpets.markets.contracts import (
    MarketAdapter,
    MarketError,
    MarketInfo,
    MarketItem,
    MarketPack,
    MarketPage,
    MarketQuery,
)
from app.plugins.agentpets.markets.registry import MarketRegistry, create_market_registry, register_market
from app.plugins.agentpets.packs.constants import MAX_IMAGE_BYTES
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import ImportMarketPackRequest


class MemoryMarket(MarketAdapter):
    """使用内存结果验证适配器契约，未知素材通过领域错误报告"""

    @property
    def info(self):
        """返回稳定的内存市场身份，注册时无需访问网络"""
        return MarketInfo(id="memory", name="内存市场")

    def search(self, query):
        """提供带命名空间的远程 ID，证明市场 ID 与本地素材 ID 独立"""
        return MarketPage(items=[MarketItem(id="author/pet", name="Pet")])

    def fetch(self, item_id):
        """以内存领域错误模拟形象不存在，不访问网络"""
        raise MarketError("形象不存在")


def test_adapter_requires_all_contract_methods():
    """抽象适配器缺少必需方法时不能实例化"""
    with pytest.raises(TypeError):
        MarketAdapter()


def test_plugin_uses_owned_store_implementation():
    """插件直接使用存储模块，写入方法和唯一写锁属于同一个模块实例"""
    from app.plugins.agentpets.packs import store

    assert AgentPets._store.__globals__["PackStore"] is store.PackStore
    assert store.PackStore.add.__globals__ is store.__dict__


def test_registry_keeps_instances_isolated_and_rejects_duplicates():
    """注册表不共享实例状态，重复 ID 明确失败而非覆盖"""
    registry = MarketRegistry()
    adapter = MemoryMarket()
    registry.register(adapter)
    assert registry.get("memory") is adapter
    assert [info.id for info in registry.list()] == ["memory"]
    assert MarketRegistry().list() == []
    with pytest.raises(MarketError, match="已注册"):
        registry.register(MemoryMarket())


def test_registry_rejects_unknown_market_without_resolution():
    """未知市场和任意 URL 不触发动态模块或地址解析"""
    with pytest.raises(MarketError, match="尚未接入"):
        MarketRegistry().get("https://example.com/untrusted")


@pytest.mark.parametrize("values", [
    {"page": 0}, {"page": 10001}, {"page_size": 0}, {"page_size": 51},
    {"keyword": "x" * 201}, {"url": "https://example.com"},
])
def test_query_rejects_invalid_limits_and_unknown_options(values):
    """搜索条件拒绝无效分页、过长关键词和任意 URL 扩展字段"""
    with pytest.raises(ValidationError):
        MarketQuery(**values)


def test_remote_ids_are_not_local_pack_ids_and_total_can_be_unknown():
    """远程 ID 允许市场命名空间，分页总数未知时保留为空"""
    result = MemoryMarket().search(MarketQuery())
    assert result.items[0].id == "author/pet"
    assert result.total is None
    assert result.model_dump(mode="json")["items"][0]["name"] == "Pet"


def test_market_metadata_rejects_non_http_links_and_impossible_totals():
    """展示链接和总量必须满足市场边界契约"""
    with pytest.raises(ValidationError):
        MarketInfo(id="memory", name="Memory", homepage="file:///etc/passwd")
    with pytest.raises(ValidationError):
        MarketPage(items=[MarketItem(id="pet", name="Pet")], total=0)


@pytest.fixture
def market_plugin(tmp_path, monkeypatch):
    """将内存适配器和生成图片接入真实临时存储，隔离宿主服务与数据"""
    output = BytesIO()
    Image.new("RGBA", (16, 16), (20, 180, 90, 255)).save(output, format="PNG")
    material = MarketPack(pack={
        "id": "pet", "name": "Pet", "grid": {"cols": 1, "rows": 1}, "frames": {"idle": 0},
    }, image=output.getvalue())
    adapter = MemoryMarket()
    monkeypatch.setattr(adapter, "fetch", lambda item_id: material)
    data = {}
    store = PackStore(lambda key: deepcopy(data.get(key)),
                      lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    plugin = object.__new__(AgentPets)
    plugin._markets = MarketRegistry([adapter])
    plugin._store = lambda: store
    return plugin, adapter, store, material


def test_market_list_and_search_dispatch(market_plugin, monkeypatch):
    """API 将裁剪后的关键词及分页条件分发到指定适配器并保留结果元信息"""
    plugin, adapter, _, _ = market_plugin
    queries = []

    def search(query):
        """记录收到的查询并返回受控下一页状态供分发断言使用"""
        queries.append(query)
        return MarketPage(items=[MarketItem(id="author/pet", name="Pet")], has_more=True)

    monkeypatch.setattr(adapter, "search", search)
    assert plugin.api_markets().data[0]["id"] == "memory"
    response = plugin.api_market_items("memory", "  pet  ", 2, 5)
    assert response.success
    assert queries == [MarketQuery(keyword="pet", page=2, page_size=5)]
    assert response.data["page"] == 2 and response.data["page_size"] == 5
    assert response.data["has_more"] and response.data["total"] is None


def test_no_registered_markets_is_a_valid_empty_state():
    """空注册表返回成功空列表，未知市场的搜索和导入明确失败"""
    plugin = AgentPets()
    plugin._markets = MarketRegistry()
    response = plugin.api_markets()
    assert response.success and response.data == []
    assert not plugin.api_market_items("missing").success
    assert not plugin.api_import_market_pack(ImportMarketPackRequest(market_id="missing", item_id="pet")).success


def test_default_market_registration_is_local_and_instance_scoped():
    """默认市场按顺序注册且实例独立，构造与列表读取不联网"""
    first = create_market_registry()
    second = create_market_registry()
    assert [info.id for info in first.list()] == ["codex-pets", "openpets", "petdex"]
    assert first.get("codex-pets") is not second.get("codex-pets")
    assert AgentPets().api_markets().data[0]["id"] == "codex-pets"


def test_new_provider_module_registers_without_factory_changes(tmp_path, monkeypatch):
    """新模块通过装饰器登记后自动被发现，工厂无需改动且适配器逐实例创建"""
    from app.plugins.agentpets.markets import providers

    monkeypatch.setattr(market_registry, "_market_types", dict(market_registry._market_types))
    monkeypatch.setattr(providers, "__path__", [*providers.__path__, str(tmp_path)])
    support_name = "agentpets_market_test_support"
    support = ModuleType(support_name)
    support.MemoryMarket = MemoryMarket
    monkeypatch.setitem(sys.modules, support_name, support)
    module_name = f"{providers.__name__}.new_market"
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, module_name, None)
        sys.modules.pop(module_name)
        try:
            (tmp_path / "new_market.py").write_text(
                "from agentpets_market_test_support import MemoryMarket\n"
                "from app.plugins.agentpets.markets.contracts import MarketInfo\n"
                "from app.plugins.agentpets.markets.registry import register_market\n"
                "@register_market\n"
                "class NewMarket(MemoryMarket):\n"
                "    \"\"\"显式装饰后由目录发现的临时供应商\"\"\"\n"
                "    market_id = 'new-market'\n"
                "    @property\n"
                "    def info(self):\n"
                "        \"\"\"返回与登记身份一致的展示信息\"\"\"\n"
                "        return MarketInfo(id=self.market_id, name='New Market')\n",
                encoding="utf-8",
            )
            first, second = create_market_registry(), create_market_registry()
            assert [info.id for info in first.list()] == ["codex-pets", "new-market", "openpets", "petdex"]
            assert first.get("new-market") is not second.get("new-market")
            assert MemoryMarket not in market_registry._market_types.values()
        finally:
            if hasattr(providers, "new_market"):
                delattr(providers, "new_market")


def test_decorator_registration_rejects_duplicates_and_abstract_types(monkeypatch):
    """装饰器不创建实例，重复身份、非法身份及未实现接口的类型均不能进入注册表"""
    monkeypatch.setattr(market_registry, "_market_types", dict(market_registry._market_types))

    class UnregisteredMarket(MemoryMarket):
        """只定义身份但不加装饰器的类不产生登记副作用"""

        market_id = "unregistered-market"

    assert UnregisteredMarket.market_id not in market_registry._market_types

    @register_market
    class RegisteredMarket(MemoryMarket):
        """继承完整接口并显式登记的具体供应商"""

        market_id = "registered-market"

    assert market_registry._market_types["registered-market"] is RegisteredMarket
    with pytest.raises(MarketError, match="已注册"):
        @register_market
        class DuplicateMarket(MemoryMarket):
            """使用重复标识的类型应在装饰时失败"""

            market_id = "registered-market"

    with pytest.raises(MarketError, match="标识无效"):
        @register_market
        class InvalidMarket(MemoryMarket):
            """非规范市场标识不能参与自动登记"""

            market_id = "Invalid ID"

    with pytest.raises(MarketError, match="抽象"):
        @register_market
        class AbstractMarket(MarketAdapter):
            """尚未实现接口的类型不能被工厂实例化"""

            market_id = "abstract-market"


def test_declared_market_identity_must_match_instance_info(monkeypatch):
    """供应商声明与展示身份必须相同，避免实例缓存以错误市场标识归属"""
    monkeypatch.setattr(market_registry, "_market_types", dict(market_registry._market_types))

    @register_market
    class MismatchedMarket(MemoryMarket):
        """故意继承不同身份的展示信息，验证实例装配检查"""

        market_id = "mismatched-market"

    with pytest.raises(MarketError, match="不一致"):
        MarketRegistry([MismatchedMarket()])


def test_market_import_persists_image_and_requires_explicit_copy(market_plugin, monkeypatch):
    """导入保存真实图片，重复 ID 不覆盖，只有显式副本模式生成新 ID"""
    plugin, adapter, store, material = market_plugin
    requested = []

    def fetch(item_id):
        """记录远程素材标识并返回完整内存素材，不自行写存储"""
        requested.append(item_id)
        return material

    monkeypatch.setattr(adapter, "fetch", fetch)
    request = ImportMarketPackRequest(market_id="memory", item_id="author/pet")
    response = plugin.api_import_market_pack(request)
    assert response.success and response.data["id"] == "pet"
    original = store.get("pet")
    assert store.image_path(original).read_bytes() == material.image
    assert requested == ["author/pet"]
    assert not plugin.api_import_market_pack(request).success
    copied = plugin.api_import_market_pack(request.model_copy(update={"mode": "copy"}))
    assert copied.success and copied.data["id"] != "pet"
    assert store.get("pet") == original and len(store.list()) == 2


@pytest.mark.parametrize("bad_field", ["image", "frames"])
def test_invalid_market_material_never_writes_records(market_plugin, monkeypatch, bad_field):
    """坏图片或越界帧在持久化前被拒绝，不留下记录和素材目录"""
    plugin, adapter, store, material = market_plugin
    if bad_field == "image":
        broken = MarketPack(pack=material.pack, image=b"not an image")
    else:
        broken = MarketPack(pack={**material.pack, "frames": {"idle": 1}}, image=material.image)
    monkeypatch.setattr(adapter, "fetch", lambda item_id: broken)
    response = plugin.api_import_market_pack(ImportMarketPackRequest(market_id="memory", item_id="pet"))
    assert not response.success
    assert store.list() == [] and not store._dir.exists()


@pytest.mark.parametrize("operation", ["search", "fetch"])
@pytest.mark.parametrize("error_type", [MarketError, OSError, RuntimeError, ValueError])
def test_market_failures_are_reported_without_leaking_upstream_details(market_plugin, monkeypatch, operation, error_type):
    """可预期错误可读，未知网络细节不进入 API 响应且不写入素材"""
    plugin, adapter, store, _ = market_plugin
    message = "市场暂不可用" if error_type is MarketError else "upstream credential=private"

    def fail(_argument):
        """在指定市场操作注入领域或底层错误，检验统一错误映射"""
        raise error_type(message)

    monkeypatch.setattr(adapter, operation, fail)
    response = (plugin.api_market_items("memory") if operation == "search" else
                plugin.api_import_market_pack(ImportMarketPackRequest(market_id="memory", item_id="pet")))
    assert not response.success and "private" not in response.message
    if error_type is MarketError:
        assert response.message == message
    assert store.list() == []


def test_oversized_market_page_is_rejected(market_plugin, monkeypatch):
    """供应商返回超过请求页大小时，API 拒绝结果而非静默截断"""
    plugin, adapter, _, _ = market_plugin
    monkeypatch.setattr(adapter, "search", lambda query: MarketPage(items=[
        MarketItem(id="one", name="One"), MarketItem(id="two", name="Two"),
    ]))
    assert not plugin.api_market_items("memory", page_size=1).success


def test_download_is_bounded_before_import(market_plugin):
    """适配器下载结果在进入存储前必须满足图片字节上限"""
    _, _, _, material = market_plugin
    with pytest.raises(ValidationError):
        MarketPack(pack=material.pack, image=b"x" * (MAX_IMAGE_BYTES + 1))


def test_market_api_permissions_and_http_validation(market_plugin):
    """实际 HTTP 路由验证参数与管理员权限，拒绝覆盖模式及任意下载字段"""
    plugin, _, _, _ = market_plugin
    app = FastAPI()
    for route in plugin.get_api():
        if route["path"].startswith("/markets"):
            assert route["auth"] == "bear"
            app.add_api_route(route["path"], route["endpoint"], methods=route["methods"],
                              dependencies=route.get("dependencies", []), response_model=route["response_model"])
    with pytest.raises(HTTPException) as denied:
        require_admin(SimpleNamespace(super_user=False))
    assert denied.value.status_code == 403
    app.dependency_overrides[require_admin] = lambda: require_admin(SimpleNamespace(super_user=False))
    with TestClient(app) as client:
        assert client.get("/markets").json()["success"]
        assert client.get("/markets/items", params={"market_id": "memory"}).json()["success"]
        for values in ({"page": 0}, {"page_size": 51}, {"keyword": "x" * 201}):
            assert client.get("/markets/items", params={"market_id": "memory", **values}).status_code == 422
        payload = {"market_id": "memory", "item_id": "author/pet"}
        assert client.post("/markets/import", json=payload).status_code == 403
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(super_user=True)
        assert client.post("/markets/import", json={**payload, "mode": "replace"}).status_code == 422
        assert client.post("/markets/import", json={**payload, "url": "http://localhost"}).status_code == 422
        assert client.post("/markets/import", json=payload).json()["success"]
