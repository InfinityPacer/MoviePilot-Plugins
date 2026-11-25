"""删除指纹存储，对用户表现为“近期删除资源”。

记录因超时、Tracker 命中或手动删除而移除的种子，供 ResourceSelection 与 ResourceSubmit 防止立即重选。
匹配语义按精确身份逐层判断：真实 info_hash、主程序规范化资源身份（站点 + 稳定种子 ID），
以及历史累计的 enclosure/page_url 链接，不按标题泛匹配，避免误挡同站同名的不同资源。
"""
import time
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit

from app.sdk.media import TorrentInfo, torrent_resource_identity


def _dedupe_strings(values: Iterable[Optional[str]]) -> list[str]:
    """按首次出现顺序去重非空字符串，保留历史链接与身份集合。"""
    seen = set()
    result = []
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _url_host(url: Optional[str]) -> str:
    """提取 http/https 链接的小写主机名，用于旧记录缺 site 时的同站身份对齐。"""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return ""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


class DeletesStore:
    """已删除种子指纹的读写、匹配与老化。"""

    def __init__(
        self,
        task_data_read: Callable,
        task_data_update: Callable,
        identity_resolver: Optional[Callable[[object], Optional[tuple[str, str]]]] = None,
    ):
        """初始化删除指纹存储；可注入资源身份解析器便于单测隔离。"""
        self._read = task_data_read
        self._update = task_data_update
        self._identity_resolver = identity_resolver or self._default_identity_resolver

    @staticmethod
    def _default_identity_resolver(torrent_info) -> Optional[tuple[str, str]]:
        """委托主程序 SDK 解析稳定资源身份；协议端口未装配（如隔离单测）时安全退回 None。"""
        try:
            return torrent_resource_identity(torrent_info)
        except RuntimeError:
            return None

    def resolve_identities(
        self,
        torrent_info=None,
        *,
        enclosure: Optional[str] = None,
        page_url: Optional[str] = None,
        site=None,
        site_name: Optional[str] = None,
    ) -> list[str]:
        """提取候选或已删任务的规范化资源身份键集合（兼容站点 ID 与主机名两种口径）。"""
        target = torrent_info
        if target is None and (enclosure or page_url):
            target = TorrentInfo(
                site=site,
                site_name=site_name,
                enclosure=enclosure,
                page_url=page_url,
            )
        if target is None:
            return []
        identity = self._identity_resolver(target)
        if not identity or len(identity) != 2 or not identity[1]:
            return []
        site_part, resource_part = str(identity[0] or "").strip(), str(identity[1]).strip()
        keys = []
        if site_part:
            keys.append(f"site:{site_part}|{resource_part}")
        resolved_page = page_url if page_url is not None else getattr(target, "page_url", None)
        resolved_enc = enclosure if enclosure is not None else getattr(target, "enclosure", None)
        for url in (resolved_page, resolved_enc):
            host = _url_host(url)
            if host:
                keys.append(f"host:{host}|{resource_part}")
        return _dedupe_strings(keys)

    def _entry_identities(self, entry: dict) -> list[str]:
        """读取记录已保存的资源身份，并为缺该字段的旧记录现场补算一次。"""
        stored = list(entry.get("resource_identities") or [])
        computed = self.resolve_identities(
            enclosure=entry.get("enclosure"),
            page_url=entry.get("page_url"),
            site=entry.get("site"),
            site_name=entry.get("site_name"),
        )
        for url in entry.get("enclosures") or []:
            computed.extend(
                self.resolve_identities(
                    enclosure=url,
                    site=entry.get("site"),
                    site_name=entry.get("site_name"),
                )
            )
        for url in entry.get("page_urls") or []:
            computed.extend(
                self.resolve_identities(
                    page_url=url,
                    site=entry.get("site"),
                    site_name=entry.get("site_name"),
                )
            )
        return _dedupe_strings([*stored, *computed])

    def save(self, torrent_task: dict, reason: str = "timeout"):
        """按 hash 归档并合并删除指纹，累加历史链接与规范化资源身份避免跨渠道覆盖。"""
        if not torrent_task:
            return
        torrent_hash = torrent_task.get("hash")
        if not torrent_hash:
            return
        normalized_hash = str(torrent_hash).strip().lower()

        def updater(data: dict) -> dict:
            existing_key = next(
                (key for key in data if str(key).strip().lower() == normalized_hash),
                None,
            )
            previous = data.pop(existing_key, {}) if existing_key is not None else {}
            if not isinstance(previous, dict):
                previous = {}
            entry = dict(previous)
            entry.update(torrent_task)
            enclosures = _dedupe_strings([
                *(previous.get("enclosures") or []),
                previous.get("enclosure"),
                *(torrent_task.get("enclosures") or []),
                torrent_task.get("enclosure"),
            ])
            page_urls = _dedupe_strings([
                *(previous.get("page_urls") or []),
                previous.get("page_url"),
                *(torrent_task.get("page_urls") or []),
                torrent_task.get("page_url"),
            ])
            identities = _dedupe_strings([
                *(previous.get("resource_identities") or []),
                *(torrent_task.get("resource_identities") or []),
                *self.resolve_identities(
                    enclosure=previous.get("enclosure"),
                    page_url=previous.get("page_url"),
                    site=previous.get("site"),
                    site_name=previous.get("site_name"),
                ),
                *self.resolve_identities(
                    enclosure=torrent_task.get("enclosure"),
                    page_url=torrent_task.get("page_url"),
                    site=torrent_task.get("site"),
                    site_name=torrent_task.get("site_name"),
                ),
            ])
            if enclosures:
                entry["enclosures"] = enclosures
            if page_urls:
                entry["page_urls"] = page_urls
            if identities:
                entry["resource_identities"] = identities
            entry["delete_time"] = time.time()
            entry["delete_type"] = reason
            data[torrent_hash] = entry
            return data

        self._update("deletes", updater)

    def match(
        self,
        enclosure: Optional[str] = None,
        page_url: Optional[str] = None,
        partial: bool = True,
        *,
        hashes: Optional[Iterable[str]] = None,
        torrent_info=None,
        site=None,
        site_name: Optional[str] = None,
    ) -> bool:
        """判断资源是否命中删除指纹：依次检查真实 hash、规范化资源身份与历史 URL 集合。"""
        if torrent_info is not None:
            if enclosure is None:
                enclosure = getattr(torrent_info, "enclosure", None)
            if page_url is None:
                page_url = getattr(torrent_info, "page_url", None)
            if site is None:
                site = getattr(torrent_info, "site", None)
            if site_name is None:
                site_name = getattr(torrent_info, "site_name", None)

        def is_match(field1, field2) -> bool:
            if partial:
                # 双向子串匹配：兼容种子 URL 带/不带 passkey 等细微差异
                return bool(field1 and field2 and (field1 in field2 or field2 in field1))
            return field1 == field2

        deletes = self._read("deletes") or {}
        if not deletes:
            return False

        candidate_hashes = {str(item).strip().lower() for item in (hashes or []) if item}
        if candidate_hashes:
            for key, entry in deletes.items():
                stored_hash = str(key).strip().lower()
                if stored_hash in candidate_hashes:
                    return True
                entry_hash = entry.get("hash") if isinstance(entry, dict) else None
                if entry_hash and str(entry_hash).strip().lower() in candidate_hashes:
                    return True

        candidate_identities = set(
            self.resolve_identities(
                torrent_info=torrent_info,
                enclosure=enclosure,
                page_url=page_url,
                site=site,
                site_name=site_name,
            )
        )
        for entry in deletes.values():
            if not isinstance(entry, dict):
                continue
            if candidate_identities and (candidate_identities & set(self._entry_identities(entry))):
                return True
            stored_enclosures = _dedupe_strings([*(entry.get("enclosures") or []), entry.get("enclosure")])
            if any(is_match(enclosure, item) for item in stored_enclosures):
                return True
            stored_pages = _dedupe_strings([*(entry.get("page_urls") or []), entry.get("page_url")])
            if any(is_match(page_url, item) for item in stored_pages):
                return True
        return False

    def cleanup_expired(self, retention_hours: int = 24, now: Optional[float] = None) -> int:
        """清理超过保留期的删除指纹，返回移除条数。

        指纹只增不减会长期挡住同源资源重选；按 delete_time 老化，保留期内保留、过期移除。
        now 可注入便于测试；缺 delete_time 的旧条目保守保留（不老化）。
        """
        now = time.time() if now is None else now
        cutoff = now - retention_hours * 3600
        removed = 0

        def updater(data: dict) -> dict:
            nonlocal removed
            kept = {}
            for key, entry in (data or {}).items():
                delete_time = entry.get("delete_time", 0)
                if delete_time and delete_time < cutoff:
                    removed += 1
                    continue
                kept[key] = entry
            return kept

        self._update("deletes", updater)
        return removed
