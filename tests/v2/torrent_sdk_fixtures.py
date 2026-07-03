"""下载器 SDK 字段测试夹具。"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from transmission_rpc import Torrent


def make_tr_v7_torrent(**overrides):
    """构造 transmission-rpc 7.x 的真实 Torrent 对象。"""
    fields = {
        "id": 1,
        "name": "TR.Test",
        "hashString": "tr_hash_1",
        "doneDate": 1000,
        "addedDate": 900,
        "activityDate": 1100,
        "totalSize": 4096000,
        "sizeWhenDone": 4096000,
        "percentDone": 1.0,
        "downloadedEver": 4096000,
        "uploadedEver": 8192000,
        "uploadRatio": 2.0,
        "secondsDownloading": 100,
        "secondsSeeding": 200,
        "rateUpload": 300,
        "status": 6,
        "labels": ["tag1"],
        "trackers": [{"announce": "https://tracker/announce"}],
        "trackerStats": [
            {"tier": 0, "lastAnnounceResult": "OK"},
            {"tier": -1, "lastAnnounceResult": "SKIP"},
        ],
    }
    fields.update(overrides)
    return Torrent(fields=fields)


def make_tr_legacy_torrent(**overrides):
    """构造旧 transmission-rpc 风格的 Torrent 替身。"""
    now = datetime.fromtimestamp(1000, timezone.utc)
    base = {
        "hashString": "tr_hash_1",
        "name": "TR.Test",
        "date_done": now,
        "date_added": datetime.fromtimestamp(900, timezone.utc),
        "date_active": datetime.fromtimestamp(1100, timezone.utc),
        "total_size": 4096000,
        "progress": 100,
        "ratio": 2.0,
        "status": "seeding",
        "labels": ["tag1"],
        "trackers": [SimpleNamespace(announce="https://tracker/announce")],
        "tracker_stats": [
            SimpleNamespace(tier=0, last_announce_result="OK"),
            SimpleNamespace(tier=-1, last_announce_result="SKIP"),
        ],
        "fields": {"size_when_done": 4096000},
    }
    base.update(overrides)
    torrent = SimpleNamespace(**base)
    torrent.get = lambda key, default=None: getattr(torrent, key, default)
    if not hasattr(torrent, "size_when_done"):
        torrent.size_when_done = torrent.fields.get("size_when_done", torrent.total_size)
    return torrent


def install_app_plugin_alias(plugin_id: str) -> None:
    """让插件内的 app.plugins.<plugin_id> 绝对导入指向本仓 plugins.v2。"""
    plugin_dir = Path(__file__).resolve().parents[2] / "plugins.v2" / plugin_id
    module_name = f"app.plugins.{plugin_id}"
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    module.__path__ = [str(plugin_dir)]


def force_transmission_plugin(plugin):
    """将绕过初始化的插件实例固定到 Transmission 分支。"""
    plugin.downloader_helper = MagicMock()
    plugin.downloader_helper.is_downloader.return_value = False
    return plugin
