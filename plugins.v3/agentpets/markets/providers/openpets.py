"""OpenPets v3 静态目录与官方 ZIP 供应商，不使用旧目录或网站私有接口"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from concurrent.futures import Future
from threading import RLock
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from pydantic import HttpUrl

from ...formats.archive import MAX_ARCHIVE_BYTES, ZipPackageReader
from ...formats.codex import build_codex_pack
from ...formats.openpets import read_openpets_package
from ...packs.constants import PackError
from ..contracts import MarketAdapter, MarketError, MarketInfo, MarketItem, MarketPack, MarketPage, MarketQuery
from ..http import read_market_bytes, validate_resource_url
from ..registry import register_market

BASE_URL = "https://openpets.dev"
ZIP_HOST = "zip.openpets.dev"
INDEX_URL = BASE_URL + "/pets/catalog.v3.json"
CACHE_TTL = 300
MAX_ITEMS = 20000
MAX_PAGES = 200
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def _identity(value: Any) -> str:
    """只接受 OpenPets 规范身份，不允许路径、地址或内置保留 ID"""
    if not isinstance(value, str) or _ID.fullmatch(value) is None or value == "builtin":
        raise MarketError("OpenPets 形象标识无效")
    return value


def _text(value: Any, limit: int, *, required: bool = False) -> str:
    """约束远程文本类型和展示长度，必填名称不得为空"""
    if not isinstance(value, str) or (required and not value.strip()):
        raise MarketError("OpenPets 返回了无效的文本字段")
    return value.strip()[:limit]


def _version(record: dict[str, Any]) -> int:
    """未标记素材按 v1 处理，仅接受上游约定的整数版本"""
    value = record.get("spriteVersionNumber", 1)
    if type(value) is not int or value not in (1, 2):
        raise MarketError("OpenPets 素材版本无效")
    return value


def _resource(value: Any, host: str) -> str:
    """所有目录引用都必须是精确官方主机下的公开宠物资源"""
    if not isinstance(value, str):
        raise MarketError("OpenPets 资源地址无效")
    return validate_resource_url(value, {host}, path_prefix="/pets/")


def _normalize(value: str) -> str:
    """统一关键词宽度和大小写，按搜索索引的词项执行本地匹配"""
    return unicodedata.normalize("NFKC", value).casefold()


def _read_json(url: str, limit: int = 2 * 1024 * 1024) -> dict[str, Any]:
    """有界读取官方目录 JSON，不跟随跳转或返回上游正文作为错误"""
    content = read_market_bytes(url, limit, market_name="OpenPets", allowed_hosts={"openpets.dev"})
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise MarketError("OpenPets 目录响应无法解析") from exc
    if not isinstance(data, dict):
        raise MarketError("OpenPets 目录响应必须是对象")
    return data


def _validate_index(data: dict[str, Any], *, search: bool = False) -> None:
    """验证 v3 页索引的总量、页大小和全部规范分页地址"""
    total, size, pages = data.get("total"), data.get("pageSize"), data.get("pages")
    if (type(data.get("version")) is not int or data["version"] != 3
            or type(total) is not int or not 0 <= total <= MAX_ITEMS
            or type(size) is not int or not 1 <= size <= 1000
            or not isinstance(pages, list) or len(pages) > MAX_PAGES
            or len(pages) != (total + size - 1) // size
            or not isinstance(data.get("generatedAt"), str) or not data["generatedAt"]):
        raise MarketError("OpenPets v3 索引格式或数量无效")
    prefix = "search-page" if search else "page"
    for number, url in enumerate(pages):
        if _resource(url, "openpets.dev") != f"{BASE_URL}/pets/catalog.v3/{prefix}-{number:03d}.json":
            raise MarketError("OpenPets 分页地址不符合目录协议")
    if not search and data.get("search") != BASE_URL + "/pets/catalog.v3/search.json":
        raise MarketError("OpenPets 搜索索引地址无效")


def _records(data: dict[str, Any], index: dict[str, Any], number: int) -> list[dict[str, Any]]:
    """分页结果须与所属索引的页码、页大小及预期数量一致"""
    records = data.get("pets")
    expected = min(index["pageSize"], index["total"] - number * index["pageSize"])
    if (type(data.get("version")) is not int or data["version"] != 3
            or type(data.get("page")) is not int or data["page"] != number
            or data.get("pageSize") != index["pageSize"]
            or not isinstance(records, list) or len(records) != expected
            or any(not isinstance(record, dict) for record in records)):
        raise MarketError("OpenPets 分页内容与索引不一致")
    return records


@register_market
class OpenPetsMarket(MarketAdapter):
    """OpenPets 公开 v3 目录；每个插件实例独立缓存成功的元数据"""

    market_id = "openpets"

    def __init__(self) -> None:
        """初始化有界目录缓存与并发锁，不在构造或注册阶段联网"""
        self._index: dict[str, Any] | None = None
        self._loaded_at = 0.0
        self._pages: dict[int, tuple[dict[str, Any], ...]] = {}
        self._search: tuple[tuple[str, int, str], ...] | None = None
        self._lock = RLock()
        self._refresh_lock = RLock()
        self._loading: dict[tuple, Future] = {}

    @property
    def info(self) -> MarketInfo:
        """返回稳定市场身份，初始化列表不读取远程目录"""
        return MarketInfo(id=self.market_id, name="OpenPets", homepage=HttpUrl(BASE_URL),
                          description="OpenPets 官方 v3 形象目录，支持 WebP 图集")

    def _catalog(self) -> dict[str, Any]:
        """成功索引缓存五分钟；刷新失败不清空旧值，也不继续使用过期结果"""
        with self._lock:
            if self._index is not None and monotonic() - self._loaded_at < CACHE_TTL:
                return self._index
        with self._refresh_lock:
            with self._lock:
                if self._index is not None and monotonic() - self._loaded_at < CACHE_TTL:
                    return self._index
            data = _read_json(INDEX_URL, 128 * 1024)
            _validate_index(data)
            with self._lock:
                if data != self._index:
                    self._index = data
                    self._pages, self._search = {}, None
                self._loaded_at = monotonic()
                return self._index

    def _cached(self, index: dict[str, Any], number: int | None, load):
        """Join one snapshot-specific load without holding the cache lock over I/O."""
        key = (id(index), number)
        with self._lock:
            self._require_snapshot(index)
            cached = self._search if number is None else self._pages.get(number)
            if cached is not None:
                return cached
            future = self._loading.get(key)
            owner = future is None
            if owner:
                future = self._loading[key] = Future()
        if not owner:
            return future.result()
        try:
            result = load()
            with self._lock:
                self._require_snapshot(index)
                if number is None:
                    self._search = result
                else:
                    self._pages[number] = result
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._loading.pop(key, None)

    def _require_snapshot(self, index: dict[str, Any]) -> None:
        """Late page/search responses must not populate a newer catalog snapshot."""
        if index is not self._index:
            raise MarketError("OpenPets 目录快照已更新，请重试")

    def _page(self, index: dict[str, Any], number: int) -> tuple[dict[str, Any], ...]:
        """按需读取完整目录页，仅缓存整体通过字段和 URL 验证的页面"""
        return self._cached(index, number, lambda: self._read_page(index, number))

    @staticmethod
    def _read_page(index: dict[str, Any], number: int) -> tuple[dict[str, Any], ...]:
        """Validate a complete page before making it available to any waiter."""
        records = _records(_read_json(index["pages"][number]), index, number)
        identities = set()
        for record in records:
            item_id = _identity(record.get("id"))
            if item_id in identities:
                raise MarketError("OpenPets 目录包含重复形象标识")
            identities.add(item_id)
            _text(record.get("displayName"), 120, required=True)
            _text(record.get("description", ""), 2000)
            _version(record)
            _resource(record.get("thumbnail"), "openpets.dev")
            _resource(record.get("spritesheet"), "openpets.dev")
            zip_url = _resource(record.get("zip"), ZIP_HOST)
            parts = urlsplit(zip_url).path.split("/")
            if len(parts) != 4 or parts[-1] != item_id + ".zip":
                raise MarketError("OpenPets ZIP 地址与形象身份不一致")
        return tuple(records)

    def _search_index(self, index: dict[str, Any]) -> tuple[tuple[str, int, str], ...]:
        """读取轻量搜索分片并核对快照，总量或页映射不一致时不缓存失败结果"""
        return self._cached(index, None, lambda: self._read_search(index))

    @staticmethod
    def _read_search(index: dict[str, Any]) -> tuple[tuple[str, int, str], ...]:
        """Build a complete immutable search index outside the cache lock."""
        search = _read_json(index["search"], 128 * 1024)
        _validate_index(search, search=True)
        if search["total"] != index["total"] or search["generatedAt"] != index["generatedAt"]:
            raise MarketError("OpenPets 搜索索引与目录快照不一致，请稍后重试")
        entries = []
        identities = set()
        for number, url in enumerate(search["pages"]):
            for record in _records(_read_json(url), search, number):
                item_id = _identity(record.get("id"))
                page = record.get("catalogPage")
                if item_id in identities or type(page) is not int or not 0 <= page < len(index["pages"]):
                    raise MarketError("OpenPets 搜索索引包含重复或无效映射")
                identities.add(item_id)
                name = _text(record.get("displayName"), 120, required=True)
                text = _text(record.get("searchText"), 20000)
                _version(record)
                entries.append((item_id, page, _normalize(f"{item_id} {name} {text}")))
        return tuple(entries)

    def _find(self, index: dict[str, Any], item_id: str, page: int) -> dict[str, Any]:
        """按搜索映射读取完整记录，拒绝 ID 在目录页内缺失的过期或损坏索引"""
        for record in self._page(index, page):
            if record["id"] == item_id:
                return record
        raise MarketError("OpenPets 搜索映射与目录记录不一致，请稍后重试")

    @staticmethod
    def _summary(record: dict[str, Any]) -> MarketItem:
        """生成统一摘要，未知作者与许可保持为空，来源链接使用官方详情页"""
        slug = urlsplit(record["zip"]).path.split("/")[2]
        return MarketItem(id=record["id"], name=_text(record["displayName"], 120, required=True),
                          description=_text(record.get("description", ""), 2000),
                          author=_text(record.get("author", ""), 200), license=_text(record.get("license", ""), 200),
                          preview=HttpUrl(record["thumbnail"]), source_url=HttpUrl(f"{BASE_URL}/pets/{slug}"))

    def search(self, query: MarketQuery) -> MarketPage:
        """无关键词按原目录顺序分页，有关键词按搜索词项匹配并按需补全摘要"""
        index = self._catalog()
        offset = (query.page - 1) * query.page_size
        if query.keyword:
            terms = _normalize(query.keyword).split()
            matches = [(item_id, page) for item_id, page, text in self._search_index(index)
                       if all(term in text for term in terms)]
            total = len(matches)
            records = [self._find(index, item_id, page) for item_id, page in matches[offset:offset + query.page_size]]
        else:
            total = index["total"]
            records = [self._page(index, position // index["pageSize"])[position % index["pageSize"]]
                       for position in range(offset, min(offset + query.page_size, total))]
        return MarketPage(items=[self._summary(record) for record in records], total=total,
                          has_more=offset + query.page_size < total)

    def fetch(self, item_id: str) -> MarketPack:
        """独立定位目录记录后下载官方 ZIP，检查包身份与版本并返回规范素材"""
        item_id = _identity(item_id)
        index = self._catalog()
        match = next(((identity, page) for identity, page, _ in self._search_index(index) if identity == item_id), None)
        if match is None:
            raise MarketError("OpenPets 形象不存在或已下架")
        record = self._find(index, *match)
        try:
            content = read_market_bytes(record["zip"], MAX_ARCHIVE_BYTES, market_name="OpenPets", allowed_hosts={ZIP_HOST})
            with ZipPackageReader(content) as package:
                manifest, image = read_openpets_package(package, expected_id=item_id)
            if _version(record) != _version(manifest):
                raise PackError("OpenPets 素材包版本与目录记录不一致")
            pack_id = "openpets-" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:23]
            pack = build_codex_pack({**manifest, "spriteVersionNumber": _version(manifest)}, image, pack_id)
            return MarketPack(pack=pack, image=image)
        except PackError as exc:
            raise MarketError(str(exc)) from exc
