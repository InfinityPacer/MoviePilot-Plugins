"""HitAndRun V3 的公开边界、索引和配置模型合同测试。"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from app.plugins.hitandrun import HitAndRun
from app.plugins.hitandrun.helper import TorrentHelper


REPO_ROOT = Path(__file__).parents[3]
PLUGIN_SOURCE = REPO_ROOT / "plugins.v3/hitandrun/__init__.py"


def test_v3_source_uses_public_boundaries_and_relative_modules():
    """V3 实现不依赖旧兼容路径或插件包的宿主内部导入。"""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PLUGIN_SOURCE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.sdk.config",
        "app.sdk.events",
        "app.sdk.logging",
        "app.sdk.media",
        "app.sdk.network",
        "app.sdk.plugins",
        "app.sdk.services",
        "app.sdk.utilities",
    } <= imported_modules
    assert "app.db.oper.site" in imported_modules
    assert not any(
        module.startswith(("app.compat", "app.core", "app.helper", "app.log", "app.utils", "app.db.models"))
        for module in imported_modules
    )
    assert "app.plugins.hitandrun" not in source


def test_v3_metadata_and_empty_capabilities_are_explicit():
    """V3 版本索引与插件元数据一致，空能力直接返回空列表。"""
    package_v3 = json.loads((REPO_ROOT / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))

    assert HitAndRun.plugin_version == "2.0.1"
    assert package_v3["HitAndRun"]["version"] == HitAndRun.plugin_version
    assert package_v3["HitAndRun"]["system_version"] == ">=3.0.0"
    assert package_v2["HitAndRun"]["v3"] is False
    assert HitAndRun.get_command() == []
    assert HitAndRun().get_api() == []


def test_v3_supports_pydantic_v2_model_serialization():
    """配置模型可在 Pydantic V2 下完成 JSON 序列化。"""
    from app.plugins.hitandrun.hnrconfig import HNRConfig

    config = HNRConfig()

    assert config.model_dump()
    assert config.model_dump_json()


def test_transmission_hash_prefers_current_rpc_field():
    """Transmission 新字段优先读取，避免 V3 运行时触发旧属性告警。"""
    torrent = SimpleNamespace(hash_string="new-hash", hashString="legacy-hash")

    assert TorrentHelper._get_transmission_hash(torrent) == "new-hash"


class _FakeDownloader:
    """最小下载器替身，仅提供属性绑定判断所需的成员。"""

    def __init__(self):
        self.qbc = object()

    def is_inactive(self) -> bool:
        return False

    def get_torrents(self, ids=None):
        return [], None


def _patch_service(plugin: HitAndRun, state: dict):
    """把下载器服务查询替换为可控替身，便于模拟下载器就绪/重连。"""
    plugin._hnr_config = SimpleNamespace(downloader="QB", enabled=True)
    plugin.downloader_helper = SimpleNamespace(get_service=lambda **_kwargs: state["service"])


def test_torrent_helper_binds_and_rebinds_to_current_downloader():
    """加载时下载器未就绪不应固化空引用；下载器重连后 helper 自动重新绑定。"""
    plugin = HitAndRun()
    state = {"service": None}
    _patch_service(plugin, state)

    # 插件加载阶段下载器尚未就绪
    assert plugin.torrent_helper is None

    first = _FakeDownloader()
    state["service"] = SimpleNamespace(name="QB", instance=first)
    helper = plugin.torrent_helper
    assert helper is not None
    assert helper.downloader is first
    assert helper.dl_type == "qbittorrent"

    # 同一实例继续复用，不重复创建
    assert plugin.torrent_helper is helper

    # 下载器重连后被替换为新实例，helper 需跟随
    second = _FakeDownloader()
    state["service"] = SimpleNamespace(name="QB", instance=second)
    assert plugin.torrent_helper is not helper
    assert plugin.torrent_helper.downloader is second


def test_torrent_helper_keeps_cache_when_downloader_goes_offline():
    """下载器掉线时返回缓存 helper，由调用方判空决定是否跳过本轮。"""
    plugin = HitAndRun()
    state = {"service": None}
    _patch_service(plugin, state)

    downloader = _FakeDownloader()
    state["service"] = SimpleNamespace(name="QB", instance=downloader)
    helper = plugin.torrent_helper

    # 服务查询失败（下载器未连接）时 service_info 为 None
    state["service"] = None
    assert plugin.torrent_helper is helper


def test_torrent_helper_get_torrents_without_downloader_returns_none():
    """下载器缺失时 get_torrents 安静返回 None，不再抛 AttributeError。"""
    assert TorrentHelper(None).get_torrents() is None
