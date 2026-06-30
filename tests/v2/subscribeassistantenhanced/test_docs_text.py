"""README 与表单 hint 的关键行为文案回归。"""
from pathlib import Path


README_PATH = Path(__file__).resolve().parents[3] / "plugins.v2" / "subscribeassistantenhanced" / "README.md"


def test_readme_documents_completion_guard_and_download_check_boundaries():
    """README 不应保留旧洗版 F-only 说法，并应说明下载待定可独立注册下载检查。"""
    readme = README_PATH.read_text(encoding="utf-8")

    assert "洗版订阅只检查 F" not in readme
    assert "洗版订阅 F 不稳定" not in readme
    assert "全集洗版和电影洗版不由完结守卫裁决" in readme
    assert "只开启「自动待定下载中订阅」时也会注册「下载任务检查」" in readme
