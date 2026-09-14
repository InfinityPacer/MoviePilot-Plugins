"""命名模板的路径边界、时区及唯一性。"""

from datetime import datetime, timezone

import pytest
from app.plugins.archivemanager.naming import batch_relative_directory, frozen_names, validate_template


@pytest.mark.parametrize(
    ("layout", "group", "expected"),
    [
        ("directory", "Camera/sub | 20260128", "Camera/sub/20260911_000001"),
        ("flat", "Camera/sub | 20260128", "Camera_sub_20260911_000001"),
        ("directory", ". | 20260128", "20260911_000001"),
    ],
)
def test_batch_layout_preserves_group_and_human_batch_name(layout, group, expected):
    batch = {"task": {"archive_layout": layout}, "group": group, "batch_name": "20260911_000001"}
    assert batch_relative_directory(batch).as_posix() == expected


def test_date_only_group_does_not_become_source_directory():
    batch = {"task": {"grouping": "date"}, "group": "20260128", "batch_name": "20260911_000001"}
    assert batch_relative_directory(batch).as_posix() == "20260911_000001"


def test_names_use_frozen_creation_time_without_forced_identity_suffix():
    task = {
        "name": "报告/资料",
        "format": "7z",
        "batch_name_template": "{task_name}_{date}",
        "archive_name_template": "备份_{date}",
    }
    created_at = "2026-09-10T20:00:00+00:00"
    local_date = datetime.fromisoformat(created_at).astimezone().strftime("%Y%m%d")
    names = frozen_names(task, "abc123", created_at)
    assert names["batch_name"] == f"报告_资料_{local_date}"
    assert names["archive_name"] == f"备份_{local_date}.7z"
    task["archive_name_template"] = "{id}"
    assert frozen_names(task, "abc123", created_at)["archive_name"] == "abc123.7z"


def test_sequence_values_are_six_digits_and_global_sequence_is_supported():
    task = {
        "name": "camera",
        "format": "7z",
        "batch_name_template": "{sequence}_{global_sequence}",
        "archive_name_template": "{global_sequence}",
    }
    names = frozen_names(task, "abc123", "2026-09-10T20:00:00+00:00", sequence=12, global_sequence=345)
    assert names["batch_name"] == "000012_000345"
    assert names["archive_name"] == "000345.7z"


def test_file_mtime_uses_earliest_batch_file_and_supports_strftime():
    first = datetime(2026, 1, 28, 6, 19, 30, tzinfo=timezone.utc)
    second = datetime(2026, 1, 29, 7, 20, 40, tzinfo=timezone.utc)
    expected = first.astimezone()
    entries = [
        {"mtime_ns": int(second.timestamp() * 1_000_000_000)},
        {"mtime_ns": int(first.timestamp() * 1_000_000_000)},
    ]
    task = {
        "name": "camera",
        "format": "7z",
        "batch_name_template": "{file_mtime}",
        "archive_name_template": "camera_{file_mtime:%Y-%m-%d_%H-%M-%S}",
    }

    names = frozen_names(task, "abc123", "2026-09-13T00:00:00+00:00", entries=entries)

    assert names["batch_name"] == expected.strftime("%Y%m%d_%H%M%S")
    assert names["archive_name"] == f"camera_{expected.strftime('%Y-%m-%d_%H-%M-%S')}.7z"


def test_file_mtime_requires_a_batch_file():
    task = {"name": "backup", "format": "zip", "archive_name_template": "{file_mtime}"}

    with pytest.raises(ValueError, match="至少包含一个文件"):
        frozen_names(task, "abc123", "2026-09-13T00:00:00+00:00")


def test_escaped_id_is_literal_when_requested():
    task = {"name": "backup", "timezone": "UTC", "format": "zip", "archive_name_template": "backup_{{id}}"}
    assert frozen_names(task, "abc123", "2026-09-10T20:00:00+00:00")["archive_name"] == "backup_{id}.zip"


@pytest.mark.parametrize(
    "template",
    [
        "../{id}",
        "{task_name.__class__}",
        "{date:>30}",
        "{id!r}",
        "{unknown}",
        "bad:name",
        "{file_mtime:%Y:%m}",
        "{file_mtime:{id}}",
        "",
        "a\nb",
    ],
)
def test_invalid_templates_are_rejected(template):
    with pytest.raises(ValueError):
        validate_template(template)
