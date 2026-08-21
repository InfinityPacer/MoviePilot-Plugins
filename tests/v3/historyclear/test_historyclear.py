from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.plugins.historyclear as historyclear


def _plugin() -> historyclear.HistoryClear:
    plugin = object.__new__(historyclear.HistoryClear)
    plugin._history_oper = MagicMock()
    plugin._clear_history = True
    plugin.systemmessage = MagicMock()
    return plugin


def test_clear_uses_v3_backup_artifact_before_truncate(tmp_path, monkeypatch):
    source = tmp_path / "postgresql_20260820_120000.dump"
    source.write_bytes(b"validated dump")
    artifact = SimpleNamespace(name=source.name, path=source)
    plugin = _plugin()
    config_path = tmp_path / "config"

    monkeypatch.setattr(historyclear, "create_backup", MagicMock(return_value=artifact))
    monkeypatch.setattr(historyclear, "settings", SimpleNamespace(CONFIG_PATH=config_path))

    plugin._HistoryClear__clear()

    destination = config_path / "plugins" / "HistoryClear" / "Backup" / source.name
    assert destination.read_bytes() == b"validated dump"
    plugin._history_oper.truncate.assert_called_once_with()


def test_clear_does_not_truncate_when_v3_backup_fails(monkeypatch):
    plugin = _plugin()
    monkeypatch.setattr(
        historyclear,
        "create_backup",
        MagicMock(side_effect=RuntimeError("backup failed")),
    )

    plugin._HistoryClear__clear()

    plugin._history_oper.truncate.assert_not_called()
    plugin.systemmessage.put.assert_called_once()


def test_v3_lifecycle_and_form_contract():
    plugin = _plugin()

    assert plugin.get_state() is True
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    _, defaults = plugin.get_form()
    assert defaults == {"clear_history": False}


def test_v3_plugin_entry_initializes_history_operator(monkeypatch):
    history_oper = MagicMock()
    transfer_history_oper = MagicMock(return_value=history_oper)
    monkeypatch.setattr(historyclear, "TransferHistoryOper", transfer_history_oper)

    plugin = historyclear.HistoryClear()
    plugin.init_plugin({})

    transfer_history_oper.assert_called_once_with()
    assert plugin._history_oper is history_oper
    assert plugin.get_state() is False


def test_v3_plugin_metadata():
    assert historyclear.HistoryClear.plugin_name == "历史记录清理"
    assert historyclear.HistoryClear.plugin_desc == "一键清理历史记录。"
    assert historyclear.HistoryClear.plugin_version == "2.0"
    assert historyclear.HistoryClear.plugin_author == "InfinityPacer"
    assert historyclear.HistoryClear.plugin_config_prefix == "historyclear_"
    assert historyclear.HistoryClear.plugin_order == 61
    assert historyclear.HistoryClear.auth_level == 1
