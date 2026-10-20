"""OpenPets 使用公开响应结构与生成素材测试，不访问真实市场"""

import json
import zipfile
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event, current_thread

import pytest
from PIL import Image

from app.plugins.agentpets.formats.archive import ZipPackageReader
from app.plugins.agentpets.formats.openpets import read_openpets_package
from app.plugins.agentpets.packs.constants import PackError
from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.markets.contracts import MarketError, MarketQuery
from app.plugins.agentpets.markets.providers import openpets
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import ImportMarketPackRequest


def _image(version=2):
    """生成标准 WebP 图集，测试不依赖第三方角色素材"""
    output = BytesIO()
    Image.new("RGBA", (1536, 2288 if version == 2 else 1872), (40, 170, 90, 255)).save(output, format="WEBP")
    return output.getvalue()


def _zip(entries):
    """构造任意成员的内存 ZIP，用于布局与路径检查"""
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries:
            archive.writestr(path, content)
    return output.getvalue()


def _package(version=2, prefix="", **changes):
    """构造符合 OpenPets 两文件契约的包，允许精确覆盖清单字段"""
    manifest = {"id": "pet", "displayName": "Pet", "description": "Test pet",
                "spritesheetPath": "spritesheet.webp", "spriteVersionNumber": version, **changes}
    return _zip([(prefix + "pet.json", json.dumps(manifest)), (prefix + "spritesheet.webp", _image(version))])


@pytest.mark.parametrize("version,prefix", [(1, ""), (2, ""), (1, "pet/"), (2, "pet/")])
def test_package_accepts_documented_layout_and_identity(version, prefix):
    """标准 v1/v2 图集可位于根目录或一个顶级目录，原图字节完整保留"""
    with ZipPackageReader(_package(version, prefix)) as package:
        manifest, image = read_openpets_package(package, expected_id="pet")
    assert manifest["spriteVersionNumber"] == version and image == _image(version)


@pytest.mark.parametrize("changes", [{"id": "other"}, {"spritesheetPath": "./spritesheet.webp"},
    {"spriteVersionNumber": None}, {"spriteVersionNumber": True}, {"spriteVersionNumber": 3}])
def test_package_rejects_wrong_identity_or_manifest_contract(changes):
    """清单必须精确对应目录身份和已声明的文件，不接受无效版本或别名路径"""
    with ZipPackageReader(_package(**changes)) as package:
        with pytest.raises(PackError):
            read_openpets_package(package, expected_id="pet")


@pytest.mark.parametrize("entries", [
    [("nested/deeper/pet.json", "{}"), ("nested/deeper/spritesheet.webp", b"image")],
    [("pet.json", "{}"), ("other/spritesheet.webp", b"image")],
    [("pet.json", "{}"), ("spritesheet.webp", b"image"), ("validation.json", "{}")],
    [("pet.json", "{}"), ("spritesheet.webp", b"image"), ("spritesheet.svg", "<svg/>")],
])
def test_package_rejects_mixed_deep_or_extra_layout(entries):
    """额外文件、混合根目录与嵌套布局均不能套用 OpenPets 规范导入"""
    with ZipPackageReader(_zip(entries)) as package:
        with pytest.raises(PackError):
            read_openpets_package(package, expected_id="pet")


def test_svg_package_reports_unsupported_format():
    """SVG 图集明确提示不支持，避免静默导入为无法渲染的位图素材"""
    with ZipPackageReader(_zip([("pet.json", "{}"), ("spritesheet.svg", "<svg/>")])) as package:
        with pytest.raises(PackError, match="SVG"):
            read_openpets_package(package, expected_id="pet")


def test_webp_filename_cannot_hide_other_image_format():
    """扩展名不能把 PNG 或任意数据伪装为 OpenPets WebP 图集"""
    output = BytesIO()
    Image.new("RGBA", (16, 16)).save(output, format="PNG")
    manifest = {"id": "pet", "spritesheetPath": "spritesheet.webp"}
    with ZipPackageReader(_zip([("pet.json", json.dumps(manifest)), ("spritesheet.webp", output.getvalue())])) as package:
        with pytest.raises(PackError, match="WebP"):
            read_openpets_package(package, expected_id="pet")


@pytest.fixture
def catalog(monkeypatch):
    """构造两页完整记录与轻量搜索映射，精确拦截所有 HTTP 资源请求"""
    root = {"version": 3, "generatedAt": "snapshot", "total": 2, "pageSize": 1,
            "search": openpets.BASE_URL + "/pets/catalog.v3/search.json",
            "pages": [openpets.BASE_URL + f"/pets/catalog.v3/page-{number:03d}.json" for number in range(2)]}
    search = {"version": 3, "generatedAt": "snapshot", "total": 2, "pageSize": 2,
              "pages": [openpets.BASE_URL + "/pets/catalog.v3/search-page-000.json"]}
    responses = {openpets.INDEX_URL: root, root["search"]: search}
    for number, (item_id, name, version) in enumerate((("pet", "Test Pet", 2), ("other", "Other Cat", 1))):
        record = {"id": item_id, "displayName": name, "description": "A companion", "spriteVersionNumber": version,
                  "thumbnail": f"https://openpets.dev/pets/{item_id}-slug/thumb.webp",
                  "spritesheet": f"https://openpets.dev/pets/{item_id}-slug/spritesheet.webp",
                  "zip": f"https://zip.openpets.dev/pets/{item_id}-slug/{item_id}.zip"}
        responses[root["pages"][number]] = {"version": 3, "page": number, "pageSize": 1, "pets": [record]}
        responses[record["zip"]] = _package(version, id=item_id)
    responses[search["pages"][0]] = {"version": 3, "page": 0, "pageSize": 2, "pets": [
        {"id": "pet", "displayName": "Test Pet", "searchText": "friendly pet companion", "catalogPage": 0},
        {"id": "other", "displayName": "Other Cat", "searchText": "calm cat companion", "catalogPage": 1},
    ]}
    state = {"responses": responses, "calls": [], "root": root, "search": search}

    def read(url, limit, **kwargs):
        """记录白名单与字节上限，未知地址或错误响应不触及真实网络"""
        state["calls"].append((url, limit, kwargs))
        value = state["responses"][url]
        if isinstance(value, Exception):
            raise value
        content = value if isinstance(value, bytes) else json.dumps(value).encode()
        assert len(content) <= limit
        return content

    monkeypatch.setattr(openpets, "read_market_bytes", read)
    return state


def test_browse_is_lazy_and_page_boundaries_are_independent(catalog):
    """统一页大小可跨越远程目录页，超出总量不会额外联网或返回重复记录"""
    market = openpets.OpenPetsMarket()
    first = market.search(MarketQuery(page_size=1))
    assert first.total == 2 and first.has_more and first.items[0].id == "pet"
    assert len(catalog["calls"]) == 2
    combined = market.search(MarketQuery(page_size=2))
    assert [item.id for item in combined.items] == ["pet", "other"] and not combined.has_more
    assert len(catalog["calls"]) == 3
    assert market.search(MarketQuery(page=4, page_size=1)).items == []
    assert len(catalog["calls"]) == 3


def test_search_uses_lightweight_index_and_preserves_unknown_license(catalog):
    """关键词匹配使用公开搜索文本，摘要保留未知许可并指向正确详情 slug"""
    market = openpets.OpenPetsMarket()
    page = market.search(MarketQuery(keyword="ＣＡＴ companion"))
    assert page.total == 1 and page.items[0].id == "other"
    assert page.items[0].author == page.items[0].license == ""
    assert str(page.items[0].source_url) == "https://openpets.dev/pets/other-slug"
    assert catalog["root"]["pages"][0] not in [call[0] for call in catalog["calls"]]
    before = len(catalog["calls"])
    assert market.search(MarketQuery(keyword="no match")).items == []
    assert len(catalog["calls"]) == before


@pytest.mark.parametrize("item_id,version", [("pet", "v2"), ("other", "v1")])
def test_fetch_without_prior_search_imports_through_store(catalog, tmp_path, item_id, version):
    """无需先浏览即可定位下载，新市场通过既有管理员导入链路保存真实图片"""
    data = {}
    store = PackStore(lambda key: deepcopy(data.get(key)),
                      lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    request = ImportMarketPackRequest(market_id="openpets", item_id=item_id)
    response = plugin.api_import_market_pack(request)
    assert response.success and response.data["id"].startswith("openpets-")
    assert len(response.data["id"]) <= 32
    record = store.get(response.data["id"])
    assert record["codex_version"] == version and store.image_path(record).is_file()
    assert not plugin.api_import_market_pack(request).success
    assert plugin.api_import_market_pack(request.model_copy(update={"mode": "copy"})).success
    zip_call = next(call for call in catalog["calls"] if call[0].startswith("https://zip.openpets.dev/"))
    assert zip_call[2]["allowed_hosts"] == {"zip.openpets.dev"} and "redirect_hosts" not in zip_call[2]


@pytest.mark.parametrize("fault", ["version", "total", "pages", "search", "unsafe"])
def test_invalid_root_index_is_not_cached(catalog, fault):
    """目录版本、数量和资源地址必须全部有效，失败不污染缓存"""
    root = catalog["root"]
    if fault == "version":
        root["version"] = 2
    elif fault == "total":
        root["total"] = True
    elif fault == "pages":
        root["pages"] = []
    elif fault == "search":
        root["search"] = "https://evil.test/search.json"
    else:
        root["pages"][0] = "http://127.0.0.1/private"
    market = openpets.OpenPetsMarket()
    with pytest.raises(MarketError):
        market.search(MarketQuery())
    assert market._index is None


@pytest.mark.parametrize("fault", ["snapshot", "duplicate", "mapping", "missing"])
def test_invalid_search_mapping_is_not_cached(catalog, fault):
    """搜索索引必须与目录快照一致，不接受重复 ID、越界或不存在的页内映射"""
    page = catalog["responses"][catalog["search"]["pages"][0]]
    if fault == "snapshot":
        catalog["search"]["generatedAt"] = "different"
    elif fault == "duplicate":
        page["pets"][1]["id"] = "pet"
    elif fault == "mapping":
        page["pets"][0]["catalogPage"] = 9
    else:
        page["pets"][0]["catalogPage"] = 1
    with pytest.raises(MarketError):
        openpets.OpenPetsMarket().search(MarketQuery(keyword="pet"))


def test_expired_index_refresh_failure_preserves_but_does_not_use_old_cache(catalog, monkeypatch):
    """缓存过期失败不使用旧目录；相同快照恢复后保留已经验证的分页。"""
    clock = [0]
    monkeypatch.setattr(openpets, "monotonic", lambda: clock[0])
    market = openpets.OpenPetsMarket()
    market.search(MarketQuery())
    old = market._index
    clock[0] = 300
    catalog["responses"][openpets.INDEX_URL] = MarketError("unavailable")
    with pytest.raises(MarketError):
        market.fetch("pet")
    assert market._index is old
    catalog["responses"][openpets.INDEX_URL] = catalog["root"]
    market.search(MarketQuery(page=3))
    assert market._index is old and len(market._pages) == 2
    assert openpets.OpenPetsMarket()._index is None


def test_unchanged_catalog_preserves_pages_and_search(catalog, monkeypatch):
    """Refreshing an unchanged validated root downloads only the root itself."""
    clock = [0]
    monkeypatch.setattr(openpets, "monotonic", lambda: clock[0])
    market = openpets.OpenPetsMarket()
    market.search(MarketQuery(keyword="pet"))
    pages, search = market._pages, market._search
    before = len(catalog["calls"])
    clock[0] = 300
    market.search(MarketQuery(keyword="pet"))
    assert market._pages is pages and market._search is search
    assert [call[0] for call in catalog["calls"][before:]] == [openpets.INDEX_URL]


def test_changed_catalog_invalidates_its_entire_snapshot(catalog, monkeypatch):
    """A changed root never reuses page or search data from the previous root."""
    clock = [0]
    monkeypatch.setattr(openpets, "monotonic", lambda: clock[0])
    market = openpets.OpenPetsMarket()
    market.search(MarketQuery(keyword="pet"))
    clock[0] = 300
    catalog["root"]["generatedAt"] = "next-snapshot"
    market.search(MarketQuery(page=3))
    assert market._pages == {} and market._search is None


@pytest.mark.parametrize("failed", [False, True])
def test_overlapping_catalog_refreshes_share_success_or_failure(catalog, monkeypatch, failed):
    """Waiters share one completed refresh, including errors, and a later call can retry."""
    market = openpets.OpenPetsMarket()
    entered, release, waiter_ready = Event(), Event(), Event()
    original_lock, read = market._lock, openpets._read_json
    calls = []

    class ObservedLock:
        """Observe the second caller leaving its initial cache check without sleeping."""

        def __enter__(self):
            """Keep the real cache lock and its serialization semantics."""
            return original_lock.__enter__()

        def __exit__(self, *args):
            """Signal only after the waiter has observed the in-flight refresh."""
            result = original_lock.__exit__(*args)
            if current_thread().name.endswith("_1"):
                waiter_ready.set()
            return result

    def blocked(url, *args):
        """Delay the owner until a concurrent caller has checked the same cold cache."""
        calls.append(url)
        entered.set()
        assert release.wait(5)
        if failed:
            raise MarketError("refresh unavailable")
        return read(url, *args)

    monkeypatch.setattr(market, "_lock", ObservedLock())
    monkeypatch.setattr(openpets, "_read_json", blocked)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="catalog-flight") as pool:
        owner = pool.submit(market._catalog)
        try:
            assert entered.wait(2)
            waiter = pool.submit(market._catalog)
            assert waiter_ready.wait(2)
        finally:
            release.set()
        for future in (owner, waiter):
            if failed:
                with pytest.raises(MarketError, match="refresh unavailable"):
                    future.result(timeout=2)
            else:
                assert future.result(timeout=2) == catalog["root"]
    assert calls == [openpets.INDEX_URL]
    monkeypatch.setattr(openpets, "_read_json", read)
    assert market._catalog() == catalog["root"]


def test_slow_search_does_not_block_cached_browse_and_is_shared(catalog, monkeypatch):
    """A blocked search holds no page-cache lock and concurrent searches join it."""
    market = openpets.OpenPetsMarket()
    market.search(MarketQuery(page_size=1))
    entered, release = Event(), Event()
    read = openpets._read_json
    calls = []

    def blocked(url, *args):
        """Block only the search root while allowing already cached catalog reads."""
        calls.append(url)
        if url == catalog["root"]["search"]:
            entered.set()
            assert release.wait(5)
        return read(url, *args)

    monkeypatch.setattr(openpets, "_read_json", blocked)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(market.search, MarketQuery(keyword="pet"))
        try:
            assert entered.wait(2)
            second = pool.submit(market.search, MarketQuery(keyword="pet"))
            cached = pool.submit(market.search, MarketQuery(page_size=1))
            assert cached.result(timeout=1).items[0].id == "pet"
        finally:
            release.set()
        assert first.result(timeout=2) == second.result(timeout=2)
    assert calls.count(catalog["root"]["search"]) == 1
    assert market._loading == {}


def test_late_page_cannot_pollute_a_new_snapshot(catalog, monkeypatch):
    """An in-flight old page fails after a refresh, then the new page can load."""
    clock = [0]
    monkeypatch.setattr(openpets, "monotonic", lambda: clock[0])
    market = openpets.OpenPetsMarket()
    market.search(MarketQuery(page_size=1))
    entered, release = Event(), Event()
    read = openpets._read_json

    def blocked(url, *args):
        """Capture old response bytes before the server publishes a new root."""
        result = read(url, *args)
        if url == catalog["root"]["pages"][1]:
            entered.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(openpets, "_read_json", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        late = pool.submit(market.search, MarketQuery(page=2, page_size=1))
        try:
            assert entered.wait(2)
            clock[0] = 300
            catalog["root"]["generatedAt"] = "new"
            assert market.search(MarketQuery(page=3, page_size=1)).items == []
        finally:
            release.set()
        with pytest.raises(MarketError, match="快照已更新"):
            late.result(timeout=2)
    assert market._pages == {} and market._loading == {}
    assert market.search(MarketQuery(page=2, page_size=1)).items[0].id == "other"


def test_failed_page_load_can_be_retried(catalog):
    """A failed owner always releases its in-flight slot and does not cache errors."""
    market = openpets.OpenPetsMarket()
    url = catalog["root"]["pages"][0]
    original = catalog["responses"][url]
    catalog["responses"][url] = MarketError("temporary")
    with pytest.raises(MarketError, match="temporary"):
        market.search(MarketQuery(page_size=1))
    assert market._loading == {} and market._pages == {}
    catalog["responses"][url] = original
    assert market.search(MarketQuery(page_size=1)).items[0].id == "pet"


@pytest.mark.parametrize("fault", ["host", "identity", "version", "page"])
def test_invalid_catalog_page_never_reaches_zip_download(catalog, fault):
    """完整目录页的身份、版本和地址异常必须在下载素材前拒绝"""
    page = catalog["responses"][catalog["root"]["pages"][0]]
    if fault == "host":
        page["pets"][0]["zip"] = "https://evil.test/pets/pet/pet.zip"
    elif fault == "identity":
        page["pets"][0]["zip"] = "https://zip.openpets.dev/pets/pet/wrong.zip"
    elif fault == "version":
        page["pets"][0]["spriteVersionNumber"] = None
    else:
        page["page"] = 1
    with pytest.raises(MarketError):
        openpets.OpenPetsMarket().fetch("pet")
    assert not any(call[0].startswith("https://zip.openpets.dev/") for call in catalog["calls"])


@pytest.mark.parametrize("item_id", ["../path", "https://evil.test", "builtin", "x" * 65, ""])
def test_invalid_identity_never_reads_index(catalog, item_id):
    """非法身份不应触发目录读取或任意 URL 下载"""
    with pytest.raises(MarketError):
        openpets.OpenPetsMarket().fetch(item_id)
    assert catalog["calls"] == []


@pytest.mark.parametrize("fault", ["identity", "version", "corrupt", "svg"])
def test_failed_download_never_writes_local_material(catalog, tmp_path, fault):
    """包身份、版本、容器或图集不支持时返回失败，不创建记录或本地图片"""
    url = "https://zip.openpets.dev/pets/pet-slug/pet.zip"
    if fault == "identity":
        content = _package(id="other")
    elif fault == "version":
        content = _package(version=1)
    elif fault == "corrupt":
        content = b"broken ZIP"
    else:
        content = _zip([("pet.json", "{}"), ("spritesheet.svg", "<svg/>")])
    catalog["responses"][url] = content
    data = {}
    store = PackStore(data.get, lambda key, value: data.__setitem__(key, value), tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    result = plugin.api_import_market_pack(ImportMarketPackRequest(market_id="openpets", item_id="pet"))
    assert not result.success and store.list() == [] and not store._dir.exists()
