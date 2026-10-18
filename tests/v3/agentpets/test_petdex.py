"""Petdex 使用生成素材和录制响应结构，所有网络边界均由测试桩替代"""

import json
import zipfile
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image

from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.formats.codex import build_codex_pack
from app.plugins.agentpets.markets.contracts import MarketError, MarketQuery
from app.plugins.agentpets.markets.http import read_market_bytes
from app.plugins.agentpets.markets.providers import petdex
from app.plugins.agentpets.markets.providers.codexpets import CodexPetsMarket
from app.plugins.agentpets.packs.constants import PackError
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import ImportMarketPackRequest


def _image(version=2, scale=1):
    """生成有整数网格的 v1/v2 图片，不依赖第三方版权素材"""
    output = BytesIO()
    Image.new("RGBA", (int(1536 * scale), int((1872 if version == 1 else 2288) * scale)),
              (30, 170, 80, 255)).save(output, format="PNG")
    return output.getvalue()


def _manifest(zip_path="pets/boba/pack.zip"):
    """提供与公开 v2 manifest 相同的紧凑字段顺序"""
    return {"v": 2, "assetBase": "https://assets.petdex.dev", "fields": list(petdex._FIELDS), "total": 1,
            "pets": [["boba", "Boba", "creature", "Creator", "pets/boba/sprite.png",
                      "pets/boba/pet.json", zip_path, 1]]}


def _archive(version=2, scale=1, declared=None):
    """生成 ZIP，目录的版本标签可与下载清单不同"""
    output = BytesIO()
    manifest = {"displayName": "Boba", "spritesheetPath": "sprite.png",
                "spriteVersionNumber": version if declared is None else declared}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pet.json", json.dumps(manifest))
        archive.writestr("sprite.png", _image(version, scale))
    return output.getvalue()


@pytest.fixture
def routes(monkeypatch):
    """拦截供应商读取边界，保留原始 URL、限额和跳转策略供断言核对"""
    state = {"calls": [], "responses": {}}

    def read(url, limit, **kwargs):
        """只返回显式注册的响应；意外请求立即失败"""
        state["calls"].append((url, limit, kwargs))
        value = state["responses"][url]
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    monkeypatch.setattr(petdex, "read_market_bytes", read)
    return state


def test_search_converts_offset_and_declared_metadata(routes):
    """统一页码转换为 offset，摘要不伪造缺失许可"""
    routes["responses"][petdex.BASE_URL + "/api/pets/search"] = {
        "pets": [{"slug": "boba", "displayName": "Boba", "description": "A pet",
                  "submittedBy": {"name": "Creator"}, "spritesheetPath": "https://assets.petdex.dev/pets/boba/sprite.png"}],
        "nextCursor": 2, "total": 3,
    }
    page = petdex.PetdexMarket().search(MarketQuery(keyword="boba", page=2, page_size=1))
    assert page.total == 3 and page.has_more and page.items[0].author == "Creator"
    assert page.items[0].license == "" and str(page.items[0].source_url) == "https://petdex.dev/pets/boba"
    assert routes["calls"][0][2]["params"] == {"q": "boba", "cursor": 1, "limit": 1, "sort": "alpha", "includeMeta": 1}


def test_empty_page_without_total_and_untrusted_preview(routes):
    """总量可缺省，末页与不可信可选预览不会产生额外访问"""
    url = petdex.BASE_URL + "/api/pets/search"
    routes["responses"][url] = {"pets": [], "nextCursor": None}
    page = petdex.PetdexMarket().search(MarketQuery())
    assert page.items == [] and page.total is None and not page.has_more
    routes["responses"][url] = {"pets": [{"slug": "boba", "displayName": "Boba",
        "spritesheetPath": "http://localhost/private", "license": "CC0-1.0"}], "nextCursor": None, "total": 1}
    item = petdex.PetdexMarket().search(MarketQuery()).items[0]
    assert item.preview is None and item.license == "CC0-1.0"


@pytest.mark.parametrize("changes", [{"nextCursor": 0}, {"nextCursor": True}, {"nextCursor": 7},
    {"total": True}, {"total": -1}, {"pets": "invalid"}])
def test_invalid_search_metadata_is_rejected(routes, changes):
    """游标必须单调且与返回条数一致，数量不能使用布尔值蒙混通过"""
    routes["responses"][petdex.BASE_URL + "/api/pets/search"] = {"pets": [], "nextCursor": None, "total": 0, **changes}
    with pytest.raises(MarketError):
        petdex.PetdexMarket().search(MarketQuery())


@pytest.mark.parametrize("fault", ["fields", "version", "total", "duplicate", "host", "base", "row", "oversize", "boolean"])
def test_manifest_is_validated_before_caching(fault):
    """紧凑目录须整体通过字段、数量和所有资源地址检查"""
    data = _manifest()
    if fault == "fields":
        data["fields"] = list(reversed(data["fields"]))
    elif fault == "version":
        data["v"] = 3
    elif fault == "total":
        data["total"] = 0
    elif fault == "duplicate":
        data["pets"] *= 2
        data["total"] = 2
    elif fault == "host":
        data["pets"][0][4] = "https://evil.test/sprite.png"
    elif fault == "base":
        data["assetBase"] = "http://127.0.0.1"
    elif fault == "row":
        data["pets"][0].pop()
    elif fault == "oversize":
        data["pets"] *= petdex.MAX_MANIFEST_ITEMS + 1
        data["total"] = len(data["pets"])
    else:
        data["pets"][0][7] = True
    with pytest.raises(MarketError):
        petdex.parse_petdex_manifest(data)


@pytest.mark.parametrize("version,scale", [(1, 1), (2, 1), (1, .5), (2, .5), (2, 1.5)])
def test_fetch_supports_versions_scaled_sheets_and_market_identity(routes, monkeypatch, version, scale):
    """下载素材决定版本，过时目录标签不阻断，跨市场同 slug 不碰撞"""
    routes["responses"][petdex.MANIFEST_URL] = _manifest()
    routes["responses"]["https://assets.petdex.dev/pets/boba/pack.zip"] = _archive(version, scale)
    material = petdex.PetdexMarket().fetch("boba")
    assert material.pack["codex_version"] == f"v{version}" and material.image == _image(version, scale)
    assert material.pack["id"].startswith("petdex-") and len(material.pack["id"]) <= 32
    assert routes["calls"][0][2]["redirect_hosts"] == {"assets.petdex.dev"}
    monkeypatch.setattr(CodexPetsMarket, "_read", lambda self, path, limit: _archive(version, scale))
    if scale == 1:
        assert material.pack["id"] != CodexPetsMarket().fetch("boba").pack["id"]
    else:
        with pytest.raises(MarketError):
            CodexPetsMarket().fetch("boba")


def test_json_image_branch_and_stable_store_copy(routes, tmp_path):
    """无 ZIP 时读取指定清单和图片，并复用真实存储处理同 ID 与副本"""
    routes["responses"].update({petdex.MANIFEST_URL: _manifest(None),
        "https://assets.petdex.dev/pets/boba/pet.json": {"displayName": "Boba", "spriteVersionNumber": 1},
        "https://assets.petdex.dev/pets/boba/sprite.png": _image(1)})
    data = {}
    store = PackStore(lambda key: deepcopy(data.get(key)),
                      lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    request = ImportMarketPackRequest(market_id="petdex", item_id="boba")
    first = plugin.api_import_market_pack(request)
    assert first.success and store.image_path(store.get(first.data["id"])).read_bytes() == _image(1)
    assert not plugin.api_import_market_pack(request).success
    assert plugin.api_import_market_pack(request.model_copy(update={"mode": "copy"})).success
    assert len(store.list()) == 2


def test_cached_manifest_refresh_failure_never_uses_expired_data(routes, monkeypatch):
    """缓存命中不联网，过期刷新失败不把旧目录当成功结果继续下载"""
    clock = [0]
    monkeypatch.setattr(petdex, "monotonic", lambda: clock[0])
    routes["responses"][petdex.MANIFEST_URL] = _manifest()
    market = petdex.PetdexMarket()
    original = market._manifest()
    clock[0] = 299
    assert market._manifest() is original and len(routes["calls"]) == 1
    clock[0] = 300
    routes["responses"][petdex.MANIFEST_URL] = MarketError("Unavailable")
    with pytest.raises(MarketError):
        market.fetch("boba")
    assert market._cache is original and len(routes["calls"]) == 2
    routes["responses"][petdex.MANIFEST_URL] = _manifest()
    assert market._manifest() is not original
    assert petdex.PetdexMarket()._cache is None


@pytest.mark.parametrize("slug", ["../secret", "https://evil.test", "boba?x", "UPPER", "x" * 64, ""])
def test_invalid_slug_does_not_request_manifest(routes, slug):
    """拒绝 URL、路径、超长与非规范 slug，不向上游发送请求"""
    with pytest.raises(MarketError):
        petdex.PetdexMarket().fetch(slug)
    assert routes["calls"] == []


def test_missing_pet_and_bad_zip_do_not_fallback_to_other_assets(routes):
    """坏 ZIP 不能通过切换下载分支绕过校验，缺失 slug 不读取资源"""
    routes["responses"][petdex.MANIFEST_URL] = _manifest()
    market = petdex.PetdexMarket()
    with pytest.raises(MarketError):
        market.fetch("missing")
    assert len(routes["calls"]) == 1
    routes["responses"]["https://assets.petdex.dev/pets/boba/pack.zip"] = b"invalid ZIP"
    with pytest.raises(MarketError):
        market.fetch("boba")
    assert len(routes["calls"]) == 2


def test_invalid_scale_or_manifest_version_cannot_be_imported():
    """比例与版本必须同时匹配，不能只用八列或清单标签猜布局"""
    with pytest.raises(PackError):
        build_codex_pack({"spriteVersionNumber": 1}, _image(2, .5), "pet", allow_scaled=True)
    output = BytesIO()
    Image.new("RGBA", (800, 900)).save(output, format="PNG")
    with pytest.raises(PackError):
        build_codex_pack({}, output.getvalue(), "pet", allow_scaled=True)


@pytest.fixture
def network(monkeypatch):
    """在宿主 HTTP 边界模拟跳转，保留每次安全检查与响应关闭证据"""
    import app.sdk.network as sdk

    state = {"responses": [], "calls": [], "guards": [], "closed": 0, "safe": True}

    class Response:
        """仅实现共享网络读取层使用的流响应接口"""

        def __init__(self, status, headers, content):
            """保存一次上游响应，不访问真实网络"""
            self.status_code, self.headers, self.content = status, headers, content

        def iter_content(self, chunk_size):
            """按测试数据返回一个受控响应块"""
            yield self.content

    class Client:
        """替代宿主客户端，记录 TLS 设置与显式跳转策略"""

        def __init__(self, **kwargs):
            """断言生产代码未关闭证书校验"""
            assert kwargs["verify"] is True

        @contextmanager
        def get_stream(self, url, **kwargs):
            """逐次提供响应，并在正常或异常退出时记录关闭"""
            state["calls"].append((url, kwargs))
            try:
                yield Response(*state["responses"].pop(0))
            finally:
                state["closed"] += 1

    def guard(url, allowed_domains, **kwargs):
        """记录每一跳的精确白名单与私网拦截要求"""
        state["guards"].append((url, allowed_domains, kwargs))
        return state["safe"]

    monkeypatch.setattr(sdk, "RequestUtils", Client)
    monkeypatch.setattr(sdk.SecurityUtils, "is_safe_url", guard)
    return state


def test_manifest_redirect_is_rechecked_and_both_responses_close(network):
    """仅 manifest 可跟随一次到指定 CDN 目录的 307，并重做 DNS 安全检查"""
    target = "https://assets.petdex.dev/manifests/petdex-v2.json"
    network["responses"] = [(307, {"Location": target}, b""), (200, {}, b"{}")]
    result = read_market_bytes(petdex.MANIFEST_URL, 100, market_name="Petdex", allowed_hosts={"petdex.dev"},
                               redirect_hosts={petdex.ASSET_HOST}, redirect_path_prefix="/manifests/")
    assert result == b"{}" and network["closed"] == 2
    assert [item[1] for item in network["guards"]] == [{"petdex.dev"}, {petdex.ASSET_HOST}]
    assert all(item[1]["allow_redirects"] is False for item in network["calls"])


@pytest.mark.parametrize("target", ["https://evil.test/manifests/x", "http://assets.petdex.dev/manifests/x",
    "https://assets.petdex.dev:443/manifests/x", "https://user@assets.petdex.dev/manifests/x",
    "https://assets.petdex.dev/pets/x", "http://127.0.0.1/private",
    "https://assets.petdex.dev/manifests/%2e%2e/private", "https://assets.petdex.dev/manifests/%5cprivate"])
def test_untrusted_manifest_redirect_is_not_followed(network, target):
    """拒绝旁路主机、降级、凭据、端口和非目录路径，不发起第二次请求"""
    network["responses"] = [(307, {"Location": target}, b"")]
    with pytest.raises(MarketError):
        read_market_bytes(petdex.MANIFEST_URL, 100, market_name="Petdex", allowed_hosts={"petdex.dev"},
                          redirect_hosts={petdex.ASSET_HOST}, redirect_path_prefix="/manifests/")
    assert len(network["calls"]) == 1 and network["closed"] == 1


def test_redirect_loops_and_private_asset_dns_are_blocked(network):
    """第二次跳转和 CDN 的非公网解析都不能绕过检查"""
    target = "https://assets.petdex.dev/manifests/petdex-v2.json"
    network["responses"] = [(307, {"Location": target}, b""), (307, {"Location": target}, b"")]
    with pytest.raises(MarketError):
        read_market_bytes(petdex.MANIFEST_URL, 100, market_name="Petdex", allowed_hosts={"petdex.dev"},
                          redirect_hosts={petdex.ASSET_HOST}, redirect_path_prefix="/manifests/")
    assert network["closed"] == 2
    network["safe"] = False
    before = len(network["calls"])
    with pytest.raises(MarketError, match="安全检查"):
        read_market_bytes(target, 100, market_name="Petdex", allowed_hosts={petdex.ASSET_HOST})
    assert len(network["calls"]) == before
