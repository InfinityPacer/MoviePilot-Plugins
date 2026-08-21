"""SAE V3 宿主 SDK 导入契约。"""
import ast
from pathlib import Path

from app.runtime.events import eventmanager as canonical_eventmanager
from app.runtime.log import logger as canonical_logger
from app.application.downloader import DownloaderHelper as CanonicalDownloaderHelper
from app.domain.metainfo import MetaInfo as CanonicalMetaInfo
from app.sdk.events import eventmanager as sdk_eventmanager
from app.sdk.logging import logger as sdk_logger
from app.sdk.media import MetaInfo as SdkMetaInfo
from app.sdk.services import DownloaderHelper as SdkDownloaderHelper

import app.plugins.subscribeassistantenhanced as plugin_module
from app.plugins.subscribeassistantenhanced.cleanup.subscription import StringUtils


PLUGIN_DIR = Path(__file__).parents[3] / "plugins.v3" / "subscribeassistantenhanced"
LEGACY_MODULE_PREFIXES = (
    "app.core",
    "app.helper",
    "app.log",
    "app.utils",
)
LEGACY_DB_MODULES = {
    "app.db.downloadhistory_oper",
    "app.db.subscribe_oper",
    "app.db.transferhistory_oper",
}


def _module_imports(path: Path):
    """返回 Python 文件中的绝对导入模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_v3_source_uses_stable_sdk_and_canonical_database_paths():
    """SAE V3 不应继续依赖宿主旧兼容导入或旧数据库别名。"""
    violations = []
    for path in sorted(PLUGIN_DIR.rglob("*.py")):
        for module in _module_imports(path):
            is_legacy_sdk = any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in LEGACY_MODULE_PREFIXES
            )
            if is_legacy_sdk or module in LEGACY_DB_MODULES:
                violations.append(f"{path.relative_to(PLUGIN_DIR)}: {module}")

    assert violations == []


def test_plugin_imports_resolve_to_canonical_sdk_objects():
    """插件导入的 SDK 符号必须与宿主 canonical 单例或实现保持同一对象。"""
    assert sdk_eventmanager is canonical_eventmanager is plugin_module.eventmanager
    assert sdk_logger is canonical_logger is plugin_module.logger
    assert SdkMetaInfo is CanonicalMetaInfo is plugin_module.MetaInfo
    assert SdkDownloaderHelper is CanonicalDownloaderHelper is plugin_module.DownloaderHelper
    assert StringUtils.__module__ == "app.sdk.string"
