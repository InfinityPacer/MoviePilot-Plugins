"""命名模板的路径边界、时区及唯一性。"""

import pytest
from app.plugins.archivemanager.naming import batch_relative_directory, frozen_names, validate_template


@pytest.mark.parametrize(
    ("layout", "group", "expected"),
    [
        ("directory", "Camera/sub | 20260128", "Camera/sub/20260911_0001"),
        ("flat", "Camera/sub | 20260128", "Camera_sub_20260911_0001"),
        ("directory", ". | 20260128", "20260911_0001"),
    ],
)
def test_batch_layout_preserves_group_and_human_batch_name(layout, group, expected):
    batch = {"task": {"archive_layout": layout}, "group": group, "batch_name": "20260911_0001"}
    assert batch_relative_directory(batch).as_posix() == expected


def test_date_only_group_does_not_become_source_directory():
    batch = {"task": {"grouping": "date"}, "group": "20260128", "batch_name": "20260911_0001"}
    assert batch_relative_directory(batch).as_posix() == "20260911_0001"


def test_names_use_frozen_creation_time_without_forced_identity_suffix():
    task = {
        "name": "报告/资料",
        "timezone": "Asia/Shanghai",
        "format": "7z",
        "batch_name_template": "{task_name}_{date}",
        "archive_name_template": "备份_{date}",
    }
    names = frozen_names(task, "abc123", "2026-09-10T20:00:00+00:00")
    assert names["batch_name"] == "报告_资料_20260911"
    assert names["archive_name"] == "备份_20260911.7z"
    task["archive_name_template"] = "{id}"
    assert (
        frozen_names(task, "abc123", "2026-09-10T20:00:00+00:00")["archive_name"]
        == "abc123.7z"
    )


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
        "",
        "a\nb",
    ],
)
def test_invalid_templates_are_rejected(template):
    with pytest.raises(ValueError):
        validate_template(template)
