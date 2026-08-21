from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.plugins.webdavbackup as webdavbackup


def _plugin(client=None) -> webdavbackup.WebDAVBackup:
    plugin = object.__new__(webdavbackup.WebDAVBackup)
    plugin._client = client or MagicMock()
    plugin._hostname = "https://dav.example/backup"
    plugin._max_count = 0
    plugin._notify = False
    plugin._enabled = True
    plugin._cron = None
    plugin._scheduler = None
    return plugin


def test_upload_uses_sqlite_backup_artifact_path_and_name(tmp_path, monkeypatch):
    source = tmp_path / "sqlite_20260820_120000.db"
    source.write_bytes(b"sqlite snapshot")
    artifact = SimpleNamespace(name=source.name, path=source)
    client = MagicMock()
    client.check.return_value = True
    plugin = _plugin(client)
    monkeypatch.setattr(webdavbackup, "create_backup", MagicMock(return_value=artifact))

    remote_path, success = plugin._WebDAVBackup__backup_files_to_webdav()

    assert success is True
    assert remote_path == "https://dav.example/backup/sqlite_20260820_120000.db"
    client.upload_sync.assert_called_once_with(
        remote_path=source.name,
        local_path=str(source),
    )
    client.check.assert_called_once_with(source.name)


def test_upload_supports_postgresql_dump_artifact(tmp_path, monkeypatch):
    source = tmp_path / "postgresql_20260820_120001.dump"
    source.write_bytes(b"postgresql snapshot")
    artifact = SimpleNamespace(name=source.name, path=source)
    client = MagicMock()
    client.check.return_value = True
    plugin = _plugin(client)
    monkeypatch.setattr(webdavbackup, "create_backup", MagicMock(return_value=artifact))

    _, success = plugin._WebDAVBackup__backup_files_to_webdav()

    assert success is True
    client.upload_sync.assert_called_once_with(
        remote_path=source.name,
        local_path=str(source),
    )


def test_upload_returns_failure_when_backup_creation_fails(monkeypatch):
    client = MagicMock()
    plugin = _plugin(client)
    monkeypatch.setattr(
        webdavbackup,
        "create_backup",
        MagicMock(side_effect=RuntimeError("database backup failed")),
    )

    remote_path, success = plugin._WebDAVBackup__backup_files_to_webdav()

    assert (remote_path, success) == ("", False)
    client.upload_sync.assert_not_called()


def test_upload_returns_failure_when_remote_check_fails(tmp_path, monkeypatch):
    source = tmp_path / "sqlite_20260820_120002.db"
    source.write_bytes(b"snapshot")
    artifact = SimpleNamespace(name=source.name, path=source)
    client = MagicMock()
    client.check.return_value = False
    plugin = _plugin(client)
    monkeypatch.setattr(webdavbackup, "create_backup", MagicMock(return_value=artifact))

    remote_path, success = plugin._WebDAVBackup__backup_files_to_webdav()

    assert remote_path.endswith(source.name)
    assert success is False


def test_v3_lifecycle_and_remote_retention_contract():
    plugin = _plugin()
    plugin._enabled = False

    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert plugin.get_service() == []

    assert webdavbackup.WebDAVBackup._WebDAVBackup__backup_created_at(
        "postgresql_20260820_120000.dump"
    ).strftime("%Y-%m-%d %H:%M:%S") == "2026-08-20 12:00:00"
