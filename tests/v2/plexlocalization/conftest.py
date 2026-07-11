"""Plex 中文本地化测试隔离。"""

import sys

import pytest


@pytest.fixture(autouse=True)
def reset_plugin_stop_event():
    """避免类级停止事件在测试模块和用例之间传播。"""
    module = sys.modules.get("plexlocalization")
    if module:
        module.PlexLocalization._event.clear()
    yield
    module = sys.modules.get("plexlocalization")
    if module:
        module.PlexLocalization._event.clear()
