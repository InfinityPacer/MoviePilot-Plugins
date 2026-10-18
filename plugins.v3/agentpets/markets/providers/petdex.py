"""Petdex 公开搜索与素材目录适配，不调用带安装计数副作用的接口"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import urljoin

from pydantic import HttpUrl

from ...formats.archive import MAX_ARCHIVE_BYTES, ZipPackageReader
from ...formats.codex import build_codex_pack, read_codex_package
from ...packs.constants import MAX_IMAGE_BYTES, MAX_JSON_BYTES, PackError
from ..contracts import MarketAdapter, MarketError, MarketInfo, MarketItem, MarketPack, MarketPage, MarketQuery
from ..http import read_market_bytes, validate_resource_url
from ..registry import register_market

BASE_URL = "https://petdex.dev"
ASSET_HOST = "assets.petdex.dev"
MANIFEST_URL = BASE_URL + "/api/manifest/v2"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_ITEMS = 20000
MANIFEST_TTL = 300
_FIELDS = ["slug", "displayName", "kind", "submittedBy", "spritesheet", "petJson", "zip", "spriteVersionNumber"]
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


@dataclass(frozen=True)
class PetdexAsset:
    """成功解析的素材定位信息；目录版本标签不代替下载清单或实际图片判版"""

    slug: str
    image_url: str
    manifest_url: str
    zip_url: str | None


def _slug(value: Any) -> str:
    """只接受 Petdex 的短 slug，不将任意地址或路径作为形象标识"""
    if not isinstance(value, str) or _SLUG.fullmatch(value) is None:
        raise MarketError("Petdex 形象标识无效")
    return value


def _text(value: Any, limit: int, *, required: bool = False) -> str:
    """规范展示文本，拒绝非字符串和缺失的必填名称"""
    if not isinstance(value, str) or (required and not value.strip()):
        raise MarketError("Petdex 返回了无效的形象信息")
    return value.strip()[:limit]


def _json(content: bytes) -> dict[str, Any]:
    """解析受限响应，错误中不包含上游正文"""
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise MarketError("Petdex JSON 响应无法解析") from exc
    if not isinstance(data, dict):
        raise MarketError("Petdex JSON 顶层必须是对象")
    return data


def _asset_url(value: str, base: str) -> str:
    """将目录相对资源解析为精确白名单内的 HTTPS 素材地址"""
    try:
        url = urljoin(base.rstrip("/") + "/", value)
    except ValueError as exc:
        raise MarketError("Petdex 素材地址无效") from exc
    return validate_resource_url(url, {ASSET_HOST})


def parse_petdex_manifest(data: dict[str, Any]) -> dict[str, PetdexAsset]:
    """严格解码 v2 紧凑目录，在缓存前验证全部记录，拒绝重复 slug 和不可信资源"""
    pets = data.get("pets")
    total = data.get("total")
    if (type(data.get("v")) is not int or data["v"] != 2 or data.get("fields") != _FIELDS
            or not isinstance(pets, list) or len(pets) > MAX_MANIFEST_ITEMS
            or type(total) is not int or total != len(pets)):
        raise MarketError("Petdex 素材目录版本、字段或数量无效")
    base = data.get("assetBase")
    if not isinstance(base, str) or not base:
        raise MarketError("Petdex 素材目录缺少资源根地址")
    validate_resource_url(base, {ASSET_HOST})
    result = {}
    for row in pets:
        if (not isinstance(row, list) or len(row) != len(_FIELDS)
                or any(not isinstance(row[index], str) for index in (0, 1, 2, 4, 5))
                or (row[3] is not None and not isinstance(row[3], str))
                or (row[6] is not None and not isinstance(row[6], str))
                or type(row[7]) is not int or row[7] not in (1, 2)
                or not row[1].strip() or not row[4] or not row[5]):
            raise MarketError("Petdex 素材目录记录无效")
        slug = _slug(row[0])
        if slug in result:
            raise MarketError("Petdex 素材目录包含重复形象标识")
        result[slug] = PetdexAsset(
            slug=slug, image_url=_asset_url(row[4], base), manifest_url=_asset_url(row[5], base),
            zip_url=_asset_url(row[6], base) if row[6] else None,
        )
    return result


@register_market
class PetdexMarket(MarketAdapter):
    """Petdex 市场；每个实例独立缓存已验证的资源目录，不缓存用户素材或图片"""

    market_id = "petdex"

    def __init__(self) -> None:
        """初始化元数据缓存和刷新锁，构造过程不联网"""
        self._cache: dict[str, PetdexAsset] | None = None
        self._cache_time = 0.0
        self._cache_lock = Lock()

    @property
    def info(self) -> MarketInfo:
        """返回稳定市场身份和公开主页"""
        return MarketInfo(id=self.market_id, name="Petdex", homepage=HttpUrl(BASE_URL),
                          description="兼容 Codex Pet v1/v2 的社区形象市场")

    def search(self, query: MarketQuery) -> MarketPage:
        """把统一页码映射为 offset，使用稳定字母排序并保留上游搜索语义"""
        offset = (query.page - 1) * query.page_size
        params: dict[str, Any] = {"cursor": offset, "limit": query.page_size, "sort": "alpha", "includeMeta": 1}
        if query.keyword:
            params["q"] = query.keyword
        data = _json(read_market_bytes(BASE_URL + "/api/pets/search", 1024 * 1024,
                                      market_name="Petdex", allowed_hosts={"petdex.dev"}, params=params))
        records = data.get("pets")
        total = data.get("total")
        next_cursor = data.get("nextCursor")
        if (not isinstance(records, list) or len(records) > query.page_size or "nextCursor" not in data
                or (total is not None and (type(total) is not int or total < len(records)))
                or (next_cursor is not None and (type(next_cursor) is not int or next_cursor <= offset
                                                or next_cursor != offset + len(records)))):
            raise MarketError("Petdex 返回了无效的分页信息")
        items = []
        for record in records:
            if not isinstance(record, dict):
                raise MarketError("Petdex 返回了无效的形象信息")
            slug = _slug(record.get("slug"))
            author = record.get("submittedBy")
            if author is not None and not isinstance(author, dict):
                raise MarketError("Petdex 返回了无效的作者信息")
            preview = record.get("spritesheetPath")
            try:
                preview = validate_resource_url(preview, {ASSET_HOST}) if isinstance(preview, str) else None
            except MarketError:
                preview = None
            items.append(MarketItem(
                id=slug, name=_text(record.get("displayName"), 120, required=True),
                description=_text(record.get("description") or "", 2000),
                author=_text((author or {}).get("name") or "", 200),
                license=_text(record.get("license") or "", 200), preview=HttpUrl(preview) if preview is not None else None,
                source_url=HttpUrl(f"{BASE_URL}/pets/{slug}"),
            ))
        return MarketPage(items=items, total=total, has_more=next_cursor is not None)

    def _manifest(self) -> dict[str, PetdexAsset]:
        """按需刷新目录，成功后缓存五分钟；失败保留旧值但不把过期目录用于导入"""
        with self._cache_lock:
            if self._cache is not None and monotonic() - self._cache_time < MANIFEST_TTL:
                return self._cache
            content = read_market_bytes(
                MANIFEST_URL, MAX_MANIFEST_BYTES, market_name="Petdex", allowed_hosts={"petdex.dev"},
                redirect_hosts={ASSET_HOST}, redirect_path_prefix="/manifests/",
            )
            parsed = parse_petdex_manifest(_json(content))
            self._cache, self._cache_time = parsed, monotonic()
            return parsed

    def _read_asset(self, url: str, limit: int) -> bytes:
        """仅读取已验证的 CDN 资源，禁止资源自动跳转"""
        return read_market_bytes(url, limit, market_name="Petdex", allowed_hosts={ASSET_HOST})

    def fetch(self, item_id: str) -> MarketPack:
        """按目录精确定位 ZIP 或分离清单和图片，格式失败时不绕过校验尝试其他资源"""
        slug = _slug(item_id)
        asset = self._manifest().get(slug)
        if asset is None:
            raise MarketError("Petdex 形象不存在或已下架")
        try:
            if asset.zip_url:
                with ZipPackageReader(self._read_asset(asset.zip_url, MAX_ARCHIVE_BYTES)) as package:
                    manifest, image = read_codex_package(package)
            else:
                manifest = _json(self._read_asset(asset.manifest_url, MAX_JSON_BYTES))
                image = self._read_asset(asset.image_url, MAX_IMAGE_BYTES)
            pack_id = "petdex-" + hashlib.sha256(slug.encode("utf-8")).hexdigest()[:24]
            return MarketPack(pack=build_codex_pack(manifest, image, pack_id, allow_scaled=True), image=image)
        except PackError as exc:
            raise MarketError(str(exc)) from exc
