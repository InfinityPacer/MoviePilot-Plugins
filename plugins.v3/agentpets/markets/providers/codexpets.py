"""Codex Pets 的目录和下载协议，不拥有通用素材校验或存储"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from pydantic import HttpUrl

from ...formats.archive import MAX_ARCHIVE_BYTES, ZipPackageReader
from ...formats.codex import build_codex_pack, read_codex_package
from ...packs.constants import PackError
from ..contracts import MarketAdapter, MarketError, MarketInfo, MarketItem, MarketPack, MarketPage, MarketQuery
from ..http import read_market_bytes
from ..registry import register_market

BASE_URL = "https://codex-pets.net"

MAX_CATALOG_BYTES = 1024 * 1024

_ITEM_ID = re.compile(r"[a-zA-Z0-9_-]{1,128}")


def _item_id(value: Any) -> str:
    """只接受站点规范的形象标识，不允许请求方注入路径或下载地址"""
    if not isinstance(value, str) or _ITEM_ID.fullmatch(value) is None:
        raise MarketError("Codex Pets 形象标识无效")
    return value


def _text(value: Any, limit: int, *, required: bool = False) -> str:
    """裁剪远程展示文本，必填名称不得为空，非字符串响应视为无效"""
    if not isinstance(value, str) or (required and not value.strip()):
        raise MarketError("Codex Pets 返回了无效的形象信息")
    return value.strip()[:limit]


def _preview(value: Any) -> HttpUrl | None:
    """仅保留固定站点素材目录下的 HTTPS 预览地址，非法可选链接忽略"""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    try:
        url = urljoin(BASE_URL + "/", value)
        parsed = urlsplit(url)
        if parsed.scheme == "https" and parsed.netloc == "codex-pets.net" and parsed.path.startswith("/assets/pets/"):
            return HttpUrl(url)
    except ValueError:
        return None
    return None


@register_market
class CodexPetsMarket(MarketAdapter):
    """访问 Codex Pets 的公开目录与下载接口，不需要站点账号或 API 密钥"""

    market_id = "codex-pets"

    @property
    def info(self) -> MarketInfo:
        """返回 Codex Pets 市场的稳定身份"""
        return MarketInfo(id=self.market_id, name="Codex Pets", homepage=HttpUrl(BASE_URL),
                          description="社区分享的 Codex Pet v1/v2 形象")

    def search(self, query: MarketQuery) -> MarketPage:
        """按上游 q/page/pageSize 查询，保留作者及明确声明的素材许可"""
        params: dict[str, Any] = {"page": query.page, "pageSize": query.page_size}
        if query.keyword:
            params["q"] = query.keyword
        content = self._read("/api/pets", MAX_CATALOG_BYTES, params)
        try:
            data = json.loads(content)
        except (ValueError, UnicodeError) as exc:
            raise MarketError("Codex Pets 目录响应无法解析") from exc
        if not isinstance(data, dict) or not isinstance(data.get("pets"), list):
            raise MarketError("Codex Pets 目录响应格式无效")
        total = data.get("total")
        if (type(total) is not int or total < len(data["pets"]) or data.get("page") != query.page
                or data.get("pageSize") != query.page_size or len(data["pets"]) > query.page_size):
            raise MarketError("Codex Pets 返回了无效的分页信息")
        items = []
        for record in data["pets"]:
            if not isinstance(record, dict):
                raise MarketError("Codex Pets 返回了无效的形象信息")
            item_id = _item_id(record.get("id"))
            items.append(MarketItem(
                id=item_id, name=_text(record.get("displayName"), 120, required=True),
                description=_text(record.get("description") or "", 2000),
                author=_text(record.get("ownerName") or record.get("ownerHandle") or "", 200),
                license=_text(record.get("license") or "", 200),
                preview=_preview(record.get("posterUrl")) or _preview(record.get("previewUrl")),
                source_url=HttpUrl(f"{BASE_URL}/#/pets/{item_id}"),
            ))
        return MarketPage(items=items, total=total, has_more=query.page * query.page_size < total)

    def fetch(self, item_id: str) -> MarketPack:
        """从固定站点下载 ZIP，安全读取清单和图片并转换为可导入素材"""
        item_id = _item_id(item_id)
        try:
            with ZipPackageReader(self._read(f"/api/pets/{item_id}/download", MAX_ARCHIVE_BYTES)) as package:
                manifest, image = read_codex_package(package)
            pack_id = "codex-" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:24]
            return MarketPack(pack=build_codex_pack(manifest, image, pack_id), image=image)
        except PackError as exc:
            raise MarketError(str(exc)) from exc

    def _read(self, path: str, limit: int, params: dict[str, Any] | None = None) -> bytes:
        """只读取固定站点路径，不允许自动跳转"""
        return read_market_bytes(BASE_URL + path, limit, market_name="Codex Pets",
                                 allowed_hosts={"codex-pets.net"}, params=params)
