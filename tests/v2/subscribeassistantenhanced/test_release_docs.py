"""增强版发布文档中的有效配置边界测试。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_removed_best_version_boolean_fields_are_not_documented():
    """README 不再暴露已由枚举字段覆盖的洗版布尔配置。"""
    readme = (ROOT / "plugins.v2/subscribeassistantenhanced/README.md").read_text(encoding="utf-8")

    for key in ("best_version_enabled", "auto_best_version_on_complete",
                "best_version_clear_history_enabled"):
        assert key not in readme
