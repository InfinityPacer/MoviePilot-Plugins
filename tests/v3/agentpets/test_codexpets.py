"""Codex Pets 适配器使用生成素材与录制结构，禁止真实网络访问"""

import json
import stat
import zipfile
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image

from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.formats.archive import MAX_ARCHIVE_BYTES
from app.plugins.agentpets.formats.codex import build_codex_pack
from app.plugins.agentpets.markets.contracts import MarketError, MarketQuery
from app.plugins.agentpets.markets.providers.codexpets import BASE_URL, CodexPetsMarket
from app.plugins.agentpets.packs.constants import LOOK_DIRECTIONS, MAX_IMAGE_BYTES, MAX_JSON_BYTES, PackError
from app.plugins.agentpets.packs.images import validate_sheet
from app.plugins.agentpets.packs.schema import codex_pet_version
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import ImportMarketPackRequest


def _image(height=2288, width=1536, image_format="PNG"):
    """生成指定尺寸和格式的纯色图片，避免测试读取外部素材"""
    output = BytesIO()
    Image.new("RGBA", (width, height), (40, 180, 80, 255)).save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize("height,version,rows", [(1872, "v1", 9), (2288, "v2", 11)])
def test_conversion_preserves_native_animation_layout(height, version, rows):
    """v1/v2 行序列、帧时长、动作别名和视线帧与原生 Codex 布局一致"""
    image = _image(height)
    pack = build_codex_pack({"displayName": "Test Pet", "description": "Description"}, image, "test-pet")
    assert pack["id"] == "test-pet"
    assert pack["name"] == "Test Pet" and pack["description"] == "Description"
    assert codex_pet_version(pack) == version
    assert pack["grid"] == {"cols": 8, "rows": rows}
    for action, expected in (("idle", range(6)), ("wave", range(24, 28)),
                             ("happy-jump", range(32, 37)), ("running-left", range(16, 24))):
        assert [pack["frames"][frame] for frame in pack["actions"][action]["frames"]] == list(expected)
    assert pack["actions"]["idle"]["frame_ms"] == 360 and pack["actions"]["idle"]["loop"]
    assert pack["actions"]["thinking"] == pack["actions"]["waiting"]
    assert pack["actions"]["speaking"] == pack["actions"]["running"]
    if version == "v2":
        assert [pack["frames"][f"look-{direction}"] for direction in LOOK_DIRECTIONS] == list(range(72, 88))
        assert len(pack["actions"]["scan"]["frames"]) == 17
    else:
        assert not any(frame.startswith("look-") for frame in pack["frames"])
        assert pack["actions"]["scan"]["frames"] == pack["actions"]["review"]["frames"]
    validate_sheet(image, pack)


def test_fetch_has_stable_noncolliding_local_ids_and_bounded_text(transport):
    """改名不改变本地 ID，不同远程 ID 不碰撞且文本遵守本地上限"""
    image = _image()
    transport["chunks"] = [_archive([
        ("pet.json", json.dumps({"displayName": "Name" * 30, "description": "Text" * 100,
                                 "spritesheetPath": "sprite.png"})), ("sprite.png", image),
    ])]
    market = CodexPetsMarket()
    first = market.fetch("same-prefix-first")
    transport["chunks"] = [_archive([
        ("pet.json", json.dumps({"displayName": "Renamed", "spritesheetPath": "sprite.png"})), ("sprite.png", image),
    ])]
    second = market.fetch("same-prefix-first")
    third = market.fetch("same-prefix-second")
    assert first.pack["id"] == second.pack["id"] != third.pack["id"]
    assert len(first.pack["id"]) <= 32
    assert len(first.pack["name"]) == 40 and len(first.pack["description"]) == 120


@pytest.mark.parametrize("image", [b"not an image", _image(height=100, width=100), _image(image_format="GIF")])
def test_conversion_rejects_unsupported_material(image):
    """不支持的图片内容、尺寸和类型不能进入素材转换结果"""
    with pytest.raises(PackError):
        build_codex_pack({}, image, "test-pet")


def test_conversion_rejects_invalid_manifest_metadata():
    """名称等清单字段不能通过数组等非法结构绕过文本校验"""
    with pytest.raises(PackError):
        build_codex_pack({"displayName": ["invalid"]}, _image(), "test-pet")


@pytest.mark.parametrize("declared", [1, 3, True, "2"])
def test_conversion_rejects_mismatched_declared_version(declared):
    """清单版本必须是与实际图片匹配的整数，布尔和字符串不能冒充版本"""
    with pytest.raises(PackError, match="版本"):
        build_codex_pack({"spriteVersionNumber": declared}, _image(), "pet")


def _archive(entries=None):
    """生成指定成员的内存 ZIP，默认包含唯一清单与对应图片"""
    if entries is None:
        entries = [
            ("pet.json", json.dumps({"displayName": "Test Pet", "spritesheetPath": "spritesheet.png"})),
            ("spritesheet.png", _image()),
        ]
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


@pytest.fixture
def transport(monkeypatch):
    """替换宿主 HTTP 与地址检查，记录请求和关闭行为并禁止真实联网"""
    import app.sdk.network as network
    from app.sdk.config import settings

    state = {"status": 200, "chunks": [], "headers": {}, "calls": [], "closed": False, "safe": True}

    class Response:
        """暴露状态、响应头和受控流内容的网络响应桩"""

        @property
        def status_code(self):
            """返回测试指定状态，便于复现限流、下架和重定向"""
            return state["status"]

        @property
        def headers(self):
            """提供可配置响应头，覆盖长度和跳转检查"""
            return state["headers"]

        def iter_content(self, chunk_size):
            """逐块产生测试数据或注入断流错误，不读取真实连接"""
            for chunk in state["chunks"]:
                if state.get("clock") is not None:
                    state["clock"][0] = 31
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk

    class Client:
        """记录生产请求参数并确认 TLS 与超时策略的客户端桩"""
        def __init__(self, **kwargs):
            """断言市场客户端显式启用证书校验并设置请求超时"""
            assert kwargs["verify"] is True and kwargs["timeout"] == 20

        @contextmanager
        def get_stream(self, url, **kwargs):
            """按测试状态返回响应或断连，退出时始终记录连接关闭"""
            state["calls"].append((url, kwargs))
            try:
                yield None if state.get("disconnected") else Response()
            finally:
                state["closed"] = True

    def check_url(url, allowed_domains, strict, block_private, allowed_private_ranges):
        """核对固定站点白名单与私网拦截开关，并返回可控安全结论"""
        assert url.startswith(BASE_URL + "/api/pets")
        assert allowed_domains == {"codex-pets.net"} and strict and block_private
        assert allowed_private_ranges == getattr(settings, "IMAGE_PROXY_ALLOWED_PRIVATE_RANGES", None)
        return state["safe"]

    monkeypatch.setattr(network, "RequestUtils", Client)
    monkeypatch.setattr(network.SecurityUtils, "is_safe_url", check_url)
    return state


def test_search_maps_live_response_structure_and_pagination(transport):
    """真实响应结构可转换为摘要，关键词和分页参数透传且未知许可为空"""
    transport["chunks"] = [json.dumps({
        "pets": [{"id": "pet-example", "displayName": "Example", "description": "A pet",
                  "ownerName": "Creator", "posterUrl": "/assets/pets/pet-example/poster.webp",
                  "downloadUrl": "http://localhost/ignored"}],
        "page": 2, "pageSize": 1, "total": 3, "totalPages": 3,
    }).encode()]
    page = CodexPetsMarket().search(MarketQuery(keyword="cat", page=2, page_size=1))
    assert page.total == 3 and page.has_more
    assert page.items[0].id == "pet-example" and page.items[0].author == "Creator"
    assert page.items[0].license == ""
    assert str(page.items[0].preview) == BASE_URL + "/assets/pets/pet-example/poster.webp"
    assert str(page.items[0].source_url) == BASE_URL + "/#/pets/pet-example"
    assert transport["calls"] == [(BASE_URL + "/api/pets", {
        "params": {"page": 2, "pageSize": 1, "q": "cat"}, "allow_redirects": False, "timeout": 20,
    })]
    assert transport["closed"]


def test_search_preserves_http_failure_instead_of_reporting_invalid_json(transport):
    """网络层限流错误保留原意，不能误报为目录 JSON 解析失败"""
    transport["status"] = 429
    with pytest.raises(MarketError, match="请求过于频繁"):
        CodexPetsMarket().search(MarketQuery())
    assert transport["closed"]


def test_search_preserves_security_rejection_without_sending_request(transport):
    """地址安全检查失败原样上报，既不联网也不伪装成数据格式错误"""
    transport["safe"] = False
    with pytest.raises(MarketError, match="安全检查"):
        CodexPetsMarket().search(MarketQuery())
    assert transport["calls"] == []


def test_empty_search_and_declared_license(transport):
    """空目录是合法状态，作者回退字段与上游明确许可得到保留"""
    transport["chunks"] = [json.dumps({"pets": [], "page": 1, "pageSize": 20, "total": 0}).encode()]
    result = CodexPetsMarket().search(MarketQuery())
    assert result.items == [] and not result.has_more
    transport["chunks"] = [json.dumps({"pets": [{
        "id": "pet", "displayName": "Pet", "license": "CC0-1.0", "ownerHandle": "creator",
        "posterUrl": "https://evil.test/preview.png",
    }], "page": 1, "pageSize": 20, "total": 1}).encode()]
    item = CodexPetsMarket().search(MarketQuery()).items[0]
    assert item.license == "CC0-1.0" and item.author == "creator" and item.preview is None


def test_malformed_preview_does_not_break_valid_catalog(transport):
    """损坏的可选预览链接不会阻断其他有效目录字段"""
    transport["chunks"] = [json.dumps({"pets": [{
        "id": "pet", "displayName": "Pet", "posterUrl": "https://[invalid",
    }], "page": 1, "pageSize": 20, "total": 1}).encode()]
    assert CodexPetsMarket().search(MarketQuery()).items[0].preview is None


def test_fetch_zip_reaches_existing_store_import_without_real_network(transport, tmp_path):
    """ZIP 下载转换后经插件导入真实临时存储，图片与运行模式完整保留"""
    transport["chunks"] = [_archive()]
    data = {}
    store = PackStore(lambda key: deepcopy(data.get(key)),
                      lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    response = plugin.api_import_market_pack(ImportMarketPackRequest(market_id="codex-pets", item_id="remote-pet"))
    assert response.success
    record = store.get(response.data["id"])
    assert codex_pet_version(record) == "v2"
    assert store.image_path(record).read_bytes() == _image()
    assert transport["calls"][0][0] == BASE_URL + "/api/pets/remote-pet/download"
    assert transport["closed"]


def test_zip_nested_manifest_resolves_relative_image(transport):
    """嵌套清单可相对访问仍处于 ZIP 内部的父目录图片"""
    transport["chunks"] = [_archive([
        ("pet/config/pet.json", json.dumps({"spritesheetPath": "../image.png"})), ("pet/image.png", _image(1872)),
    ])]
    assert CodexPetsMarket().fetch("remote-pet").pack["codex_version"] == "v1"


@pytest.mark.parametrize("item_id", ["../secret", "pet?query", "https://evil.test", "%2fpath", "pet/path", "x" * 129, ""])
def test_invalid_remote_ids_never_make_requests(transport, item_id):
    """URL、路径、编码分隔符和超长 ID 在联网前即被拒绝"""
    with pytest.raises(MarketError, match="标识无效"):
        CodexPetsMarket().fetch(item_id)
    assert transport["calls"] == []


@pytest.mark.parametrize("status", [301, 302, 307, 404, 429, 500])
def test_http_failures_and_redirects_are_closed_without_following(transport, status):
    """所有错误状态和跳转均返回市场错误并关闭响应，不跟随任意地址"""
    transport["status"] = status
    transport["headers"] = {"Location": "http://127.0.0.1/private"}
    with pytest.raises(MarketError):
        CodexPetsMarket().fetch("pet")
    assert transport["closed"] and transport["calls"][0][1]["allow_redirects"] is False


def test_private_dns_result_blocks_request(transport):
    """站点解析为非公网地址时，在发送 HTTP 前终止下载"""
    transport["safe"] = False
    with pytest.raises(MarketError, match="安全检查"):
        CodexPetsMarket().fetch("pet")
    assert transport["calls"] == []


@pytest.mark.parametrize("fault", ["header", "stream", "read", "disconnect", "deadline"])
def test_stream_limits_and_network_errors_release_response(transport, monkeypatch, fault):
    """长度、累计流量、读超时与断连受控失败，错误不泄露上游细节且连接释放"""
    if fault == "header":
        transport["headers"] = {"Content-Length": str(MAX_ARCHIVE_BYTES + 1)}
    elif fault == "stream":
        transport["chunks"] = [b"x" * MAX_ARCHIVE_BYTES, b"x"]
    elif fault == "read":
        transport["chunks"] = [OSError("private upstream response")]
    elif fault == "disconnect":
        transport["disconnected"] = True
    else:
        transport["clock"] = [0]
        transport["chunks"] = [b"x"]
        monkeypatch.setattr("app.plugins.agentpets.markets.http.monotonic", lambda: transport["clock"][0])
    with pytest.raises(MarketError) as error:
        CodexPetsMarket().fetch("pet")
    assert "private" not in str(error.value) and transport["closed"]


@pytest.mark.parametrize("payload", [b"invalid", b"[]", b'{"pets":[]}',
    json.dumps({"pets": [], "page": 2, "pageSize": 20, "total": 0}).encode(),
    json.dumps({"pets": [], "page": 1, "pageSize": 20, "total": True}).encode(),
    json.dumps({"pets": [{"id": "pet", "displayName": " "}], "page": 1, "pageSize": 20, "total": 1}).encode(),
    json.dumps({"pets": [{"id": "pet", "displayName": "Pet"}], "page": 1, "pageSize": 20, "total": 0}).encode(),
])
def test_invalid_catalog_is_rejected(transport, payload):
    """非法 JSON、结构、总量、空名称和不一致页码不产生有效搜索结果"""
    transport["chunks"] = [payload]
    with pytest.raises(MarketError):
        CodexPetsMarket().search(MarketQuery())


@pytest.mark.parametrize("entries", [
    [("image.png", b"missing manifest")],
    [("pet.json", "{}"), ("nested/pet.json", "{}")],
    [("pet.json", '{"spritesheetPath":"../../outside.png"}')],
    [("pet.json", '{"spritesheetPath":"https://evil.test/image.png"}')],
    [("pet.json", '{"spritesheetPath":"missing.png"}')],
    [("pet.json", "invalid JSON")],
    [("../pet.json", "{}")],
    [("pet.json", '{"spritesheetPath":"image.png"}'), ("image.png", b"bad image")],
    [("pet.json", "x" * (MAX_JSON_BYTES + 1))],
    [("pet.json", '{"spritesheetPath":"image.png"}'), ("image.png", b"x" * (MAX_IMAGE_BYTES + 1))],
    [("pet.json", '{"spritesheetPath":"image.png"}'), ("image.png", b""), ("./image.png", b"")],
    [(f"file-{index}", "") for index in range(257)],
])
def test_unsafe_or_invalid_archives_are_rejected(transport, entries):
    """不完整、过大、重复、越界或损坏 ZIP 都不能绕过素材导入检查"""
    transport["chunks"] = [_archive(entries)]
    with pytest.raises(MarketError):
        CodexPetsMarket().fetch("pet")


def test_symlink_archive_is_rejected(transport):
    """即使成员名合法，符号链接条目也不得作为清单读取"""
    link = zipfile.ZipInfo("pet.json")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    transport["chunks"] = [_archive([(link, "outside")])]
    with pytest.raises(MarketError, match="符号链接"):
        CodexPetsMarket().fetch("pet")


def test_corrupt_compressed_data_is_reported_as_market_error(transport):
    """损坏的压缩流统一转换为可展示市场错误，不泄露底层解压异常"""
    content = bytearray(_archive())
    with zipfile.ZipFile(BytesIO(content)) as archive:
        entry = archive.infolist()[0]
        offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
    content[offset] = 7
    transport["chunks"] = [bytes(content)]
    with pytest.raises(MarketError, match="损坏"):
        CodexPetsMarket().fetch("pet")
