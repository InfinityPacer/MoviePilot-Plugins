"""
SubscribeAssistant P2 日志格式化与摘要工具单测。

格式化方法应压缩长文本并保留排查关键信息，避免泄漏完整大对象。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


def make_plugin() -> SubscribeAssistant:
    """构造绕过 __init__ 的插件实例。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.chain = MagicMock()
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造格式化订阅需要的最小对象。"""
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, doubanid=None, imdbid=None, tvdbid=None, bangumiid=None,
        backdrop=None, poster=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class FormattingTest:
    """日志摘要与订阅展示格式。"""

    def setup_method(self):
        self.plugin = make_plugin()

    def test_truncate_log_value_returns_empty_for_none(self):
        assert SubscribeAssistant._SubscribeAssistant__truncate_log_value(None) == ""

    def test_truncate_log_value_keeps_short_text(self):
        assert SubscribeAssistant._SubscribeAssistant__truncate_log_value("abc", 5) == "abc"

    def test_truncate_log_value_truncates_tail(self):
        assert SubscribeAssistant._SubscribeAssistant__truncate_log_value("abcdef", 5) == "ab..."

    def test_truncate_log_value_truncates_middle(self):
        result = SubscribeAssistant._SubscribeAssistant__truncate_log_value("abcdefghijklmnopqrstuvwxyz", 24, True)
        assert result.startswith("abcdefghij")
        assert "..." in result
        assert result.endswith("wxyz")

    def test_format_log_title_desc_joins_title_and_description(self):
        result = self.plugin._SubscribeAssistant__format_log_title_desc("标题", "描述")
        assert result == "标题｜描述"

    def test_format_log_title_desc_uses_single_available_value(self):
        assert self.plugin._SubscribeAssistant__format_log_title_desc("", "描述") == "描述"

    def test_summarize_fileitem_for_log_handles_dict(self):
        result = self.plugin._SubscribeAssistant__summarize_fileitem_for_log(
            {"name": "a.mkv", "type": "file", "storage": "local", "path": "/very/long/path/a.mkv"}
        )
        assert "name=a.mkv" in result
        assert "type=file" in result
        assert "storage=local" in result

    def test_summarize_fileitem_for_log_handles_object(self):
        result = self.plugin._SubscribeAssistant__summarize_fileitem_for_log(
            SimpleNamespace(name="a.mkv", type="file", storage="local", path="/media/a.mkv")
        )
        assert "path=/media/a.mkv" in result

    def test_summarize_torrent_info_for_log_handles_none(self):
        assert self.plugin._SubscribeAssistant__summarize_torrent_info_for_log(None) == ""

    def test_summarize_torrent_info_for_log_keeps_site_and_category(self):
        torrent = SimpleNamespace(title="标题", description="副标题", site_name="站点", site=1, category="TV")
        result = self.plugin._SubscribeAssistant__summarize_torrent_info_for_log(torrent)
        assert "标题｜副标题" in result
        assert "站点=站点" in result
        assert "分类=TV" in result

    def test_summarize_context_for_log_includes_recognition_flags(self):
        context = SimpleNamespace(
            torrent_info=SimpleNamespace(title="标题", description="", site_name="站点", site=1, category=None),
            resource_source="rss", match_source="title", candidate_recognized=True,
            media_info_is_target=False, media_info=SimpleNamespace(title_year="测试剧 (2024)", type=MediaType.TV),
        )
        result = self.plugin._SubscribeAssistant__summarize_context_for_log(context)
        assert "来源=rss" in result
        assert "候选识别=True" in result
        assert "媒体=测试剧 (2024)" in result

    def test_summarize_subscribe_dict_for_log_handles_empty(self):
        assert self.plugin._SubscribeAssistant__summarize_subscribe_dict_for_log({}) == ""

    def test_summarize_subscribe_dict_for_log_keeps_core_fields(self):
        result = self.plugin._SubscribeAssistant__summarize_subscribe_dict_for_log(
            {"id": 1, "name": "测试剧", "year": "2024", "season": 2, "type": TV, "best_version": 1}
        )
        assert "id=1" in result
        assert "season=2" in result
        assert "best_version=1" in result

    def test_summarize_mediainfo_dict_for_log_handles_alias_ids(self):
        result = self.plugin._SubscribeAssistant__summarize_mediainfo_dict_for_log(
            {"title_year": "测试剧 (2024)", "year": "2024", "type": TV, "tmdbid": 100, "doubanid": "db"}
        )
        assert "tmdbid=100" in result
        assert "doubanid=db" in result

    def test_summarize_resource_download_event_for_log_handles_event(self):
        event_data = SimpleNamespace(
            downloader="qb", episodes={1, 2}, origin="subscribe|1",
            context=SimpleNamespace(
                torrent_info=SimpleNamespace(title="标题", description="", site_name="站点", site=1, category=None),
                resource_source="rss", match_source="title", candidate_recognized=False,
                media_info_is_target=True, media_info=None,
            ),
        )
        result = self.plugin._SubscribeAssistant__summarize_resource_download_event_for_log(event_data)
        assert "downloader=qb" in result
        assert "episodes=[1, 2]" in result

    def test_summarize_transfer_intercept_event_for_log_handles_event(self):
        event_data = SimpleNamespace(
            mediainfo=SimpleNamespace(title_year="测试剧 (2024)", tmdb_id=100),
            target_path="/media/测试剧/S01E01.mkv",
            cancel=False,
        )
        result = self.plugin._SubscribeAssistant__summarize_transfer_intercept_event_for_log(event_data)
        assert "媒体=测试剧 (2024)" in result
        assert "tmdbid=100" in result

    def test_summarize_transfer_info_for_log_handles_fileitem(self):
        transfer_info = SimpleNamespace(
            fileitem=SimpleNamespace(name="a.mkv", type="file", storage="local", path="/media/a.mkv"),
            transfer_type="link",
        )
        result = self.plugin._SubscribeAssistant__summarize_transfer_info_for_log(transfer_info)
        assert "整理类型=link" in result
        assert "name=a.mkv" in result

    def test_format_subscribe_formats_tv_movie_and_unknown(self):
        assert self.plugin._SubscribeAssistant__format_subscribe(
            make_subscribe()) == "剧集: 测试剧 (2024) 季1 [1]"
        assert self.plugin._SubscribeAssistant__format_subscribe(
            make_subscribe(type=MOVIE, name="电影")) == "电影: 电影 (2024) [1]"
        assert "未知类型" in self.plugin._SubscribeAssistant__format_subscribe(
            make_subscribe(type="bad"))

    def test_format_subscribe_desc_uses_recognized_media(self):
        mediainfo = SimpleNamespace(type=MediaType.TV, title_year="测试剧 (2024)")
        with patch.object(self.plugin, "_SubscribeAssistant__recognize_media", return_value=mediainfo):
            result = self.plugin._SubscribeAssistant__format_subscribe_desc(make_subscribe(episode_group="grp"))
        assert "测试剧 (2024)" in result
        assert "剧集组grp" in result


