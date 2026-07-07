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


def test_readme_documents_site_evidence_boundaries():
    """README 应说明站点集数探测与站点完结信号的开关和完成边界。"""
    readme = README_PATH.read_text(encoding="utf-8")

    assert "站点集数探测" in readme
    assert "用站点缓存资源辅助发现目标集数不足" in readme
    assert "仅普通剧集和分集洗版；不请求站点" in readme
    assert "站点完结信号" in readme
    assert "站点完结信号默认开启" in readme
    assert "| 站点完结信号 | `site_completion_evidence_enabled` | bool | `true` |" in readme
    assert "使用站点资源标题佐证完结信号" in readme
    assert "不会主动完成订阅" in readme
    assert "主程序发起完成检查" in readme
    assert "提前完结" in readme
    assert "默认只开启「站点完结信号」时，站点更高集数只记录诊断，不扩展目标、不否决完成" in readme
    assert "只有开启「站点集数探测」、证据严格匹配且未命中高置信 E 信号" in readme
    assert "只读取主程序已有 RSS / spider 缓存" in readme
    assert "通用巡检只读取主程序已有 RSS / spider 缓存并保存 24 小时站点证据" in readme
    assert "默认 30 分钟" in readme
