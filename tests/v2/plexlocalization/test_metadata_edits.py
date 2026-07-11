"""Plex 中文本地化元数据原子编辑测试。"""

from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from app.testing import stub_modules


_pypinyin = ModuleType("pypinyin")
_pypinyin.Style = SimpleNamespace(FIRST_LETTER="first_letter")
_pypinyin.lazy_pinyin = lambda *args, **kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    from plexlocalization import PlexLocalization


class _Response:
    """提供插件 HTTP 调用所需的最小响应契约。"""

    def __init__(self, *, status_code=200, metadata=None):
        self.status_code = status_code
        self._metadata = metadata or []

    def json(self):
        """返回 Plex JSON API 的元数据包装结构。"""
        return {"MediaContainer": {"Metadata": self._metadata}}

    def __bool__(self):
        """模拟 requests.Response 对错误状态码的布尔语义。"""
        return self.status_code < 400


class _FakePlex:
    """记录 Plex 写入请求，并为最终回读提供指定元数据。"""

    def __init__(self, final_item, status_code=200):
        self.final_item = final_item
        self.status_code = status_code
        self.put_calls = []
        self.get_calls = []

    def put_data(self, *, endpoint, params, timeout):
        """记录一次元数据编辑请求。"""
        self.put_calls.append({"endpoint": endpoint, "params": params, "timeout": timeout})
        return _Response(status_code=self.status_code)

    def get_data(self, *, endpoint, timeout):
        """返回写入完成后的条目状态。"""
        self.get_calls.append({"endpoint": endpoint, "timeout": timeout})
        return _Response(metadata=[self.final_item])


def _plugin(sort_title="TSXK"):
    plugin = object.__new__(PlexLocalization)
    plugin._lock = False
    plugin._timeout = 10
    plugin._tags = {
        "Action": "动作",
        "Adventure": "冒险",
        "Sci-Fi & Fantasy": "科幻与奇幻",
    }
    plugin._PlexLocalization__convert_to_pinyin = lambda title: sort_title
    return plugin


def _source_item():
    return {
        "ratingKey": "98824",
        "librarySectionID": 42,
        "type": "show",
        "title": "吞噬星空",
        "titleSort": "吞噬星空",
        "Field": [],
        "Genre": [
            {"tag": "Action"},
            {"tag": "Adventure"},
            {"tag": "Sci-Fi & Fantasy"},
            {"tag": "Unmapped"},
        ],
        "Style": [],
        "Mood": [],
    }


def _final_item(title_sort="TSXK"):
    return {
        **_source_item(),
        "titleSort": title_sort,
        "Genre": [
            {"tag": "动作"},
            {"tag": "冒险"},
            {"tag": "科幻与奇幻"},
            {"tag": "Unmapped"},
        ],
    }


def test_process_item_submits_sort_title_and_all_tags_in_one_request():
    """同一条目的排序标题与标签应通过一次 PUT 原子提交。"""
    plugin = _plugin()
    plex = _FakePlex(final_item=_final_item())

    result = plugin._PlexLocalization__process_item(plex=plex, item=_source_item())

    assert result is True
    assert len(plex.put_calls) == 1
    assert len(plex.get_calls) == 1
    call = plex.put_calls[0]
    assert call["endpoint"] == "/library/sections/42/all"
    assert call["params"] == {
        "type": 2,
        "id": "98824",
        "includeExternalMedia": 1,
        "titleSort.value": "TSXK",
        "titleSort.locked": 0,
        "genre.locked": 0,
        "genre[0].tag.tag": "动作",
        "genre[1].tag.tag": "冒险",
        "genre[2].tag.tag": "科幻与奇幻",
        "genre[3].tag.tag": "Unmapped",
        "genre[].tag.tag-": "Action,Adventure,Sci-Fi%20%26%20Fantasy",
    }


def test_process_item_reports_failure_when_final_sort_title_differs():
    """最终回读不一致时不得把中间写入状态记录为成功。"""
    plugin = _plugin()
    plex = _FakePlex(final_item=_final_item(title_sort=None))

    with patch("plexlocalization.logger.info") as info, patch("plexlocalization.logger.warning") as warning:
        result = plugin._PlexLocalization__process_item(plex=plex, item=_source_item())

    assert result is False
    assert len(plex.put_calls) == 1
    assert len(plex.get_calls) == 1
    assert any("更新元数据未完全生效" in str(call.args[0]) for call in warning.call_args_list)
    assert not any("吞噬星空 < TSXK >" in str(call.args[0]) for call in info.call_args_list)


def test_process_item_treats_null_sort_title_as_unset():
    """Plex 返回 null 排序标题时仍应生成并写入拼音。"""
    plugin = _plugin()
    plex = _FakePlex(final_item=_final_item())
    item = {
        **_source_item(),
        "titleSort": None,
        "Genre": [],
    }

    result = plugin._PlexLocalization__process_item(plex=plex, item=item)

    assert result is True
    assert len(plex.put_calls) == 1
    assert plex.put_calls[0]["params"]["titleSort.value"] == "TSXK"


def test_process_item_skips_write_when_relevant_fields_are_locked():
    """排序标题和标签均已锁定时不应发送编辑请求。"""
    plugin = _plugin()
    plex = _FakePlex(final_item=_final_item())
    item = {
        **_source_item(),
        "Field": [
            {"name": "titleSort", "locked": True},
            {"name": "genre", "locked": True},
        ],
    }

    result = plugin._PlexLocalization__process_item(plex=plex, item=item)

    assert result is None
    assert plex.put_calls == []
    assert plex.get_calls == []


def test_process_item_preserves_existing_sort_title_during_tag_only_update():
    """仅更新标签时应携带并校验已有的未锁定排序标题。"""
    plugin = _plugin()
    plex = _FakePlex(final_item=_final_item())
    item = {
        **_source_item(),
        "titleSort": "TSXK",
    }

    result = plugin._PlexLocalization__process_item(plex=plex, item=item)

    assert result is True
    assert plex.put_calls[0]["params"]["titleSort.value"] == "TSXK"
    assert plex.put_calls[0]["params"]["titleSort.locked"] == 0


def test_process_item_skips_redundant_sort_title_equal_to_title():
    """生成排序与原标题一致时无需写入 Plex。"""
    plugin = _plugin(sort_title="2012")
    plex = _FakePlex(final_item={})
    item = {
        **_source_item(),
        "title": "2012",
        "titleSort": None,
        "Genre": [],
    }

    result = plugin._PlexLocalization__process_item(plex=plex, item=item)

    assert result is None
    assert plex.put_calls == []
    assert plex.get_calls == []


def test_process_item_logs_noop_skip_at_debug_level():
    """无需更新的有效条目应在 debug 日志中标明标题和 ratingKey。"""
    plugin = _plugin()
    plex = _FakePlex(final_item={})
    item = {
        **_source_item(),
        "titleSort": "TSXK",
        "Genre": [{"tag": "动画"}],
    }

    with patch("plexlocalization.logger.debug") as debug:
        result = plugin._PlexLocalization__process_item(plex=plex, item=item)

    assert result is None
    assert plex.put_calls == []
    assert any(
        "吞噬星空（ratingKey=98824）无需更新，跳过" in str(call.args[0])
        for call in debug.call_args_list
    )


def test_process_item_logs_http_error_status_code():
    """Plex 返回错误响应时日志应保留真实 HTTP 状态码。"""
    plugin = _plugin()
    plex = _FakePlex(final_item=_final_item(), status_code=500)

    with patch("plexlocalization.logger.warning") as warning:
        result = plugin._PlexLocalization__process_item(plex=plex, item=_source_item())

    assert result is False
    assert plex.get_calls == []
    assert any("状态码：500" in str(call.args[0]) for call in warning.call_args_list)


def test_positive_int_config_falls_back_only_for_invalid_values():
    """线程数与批大小保持可配置，但零、负数和非法值应回退默认值。"""
    parse = PlexLocalization._PlexLocalization__positive_int

    assert parse("8", default=5) == 8
    assert parse(0, default=5) == 5
    assert parse(-2, default=100) == 100
    assert parse(None, default=5) == 5
    assert parse("invalid", default=100) == 100


def test_positive_int_config_supports_new_thread_default():
    """线程配置缺失时应使用新的安全默认值。"""
    parse = PlexLocalization._PlexLocalization__positive_int

    assert parse(None, default=3) == 3
    assert parse("8", default=3) == 8


def test_form_defaults_to_three_threads():
    """表单默认线程数应限制 Plex 的初始并发压力。"""
    plugin = object.__new__(PlexLocalization)

    with patch.object(plugin, "_PlexLocalization__get_service_library_options", return_value=[]):
        _, defaults = plugin.get_form()

    assert defaults["thread_count"] == 3


def test_init_plugin_defaults_thread_count_to_three():
    """缺省配置初始化时应实际写入三线程默认值。"""
    plugin = object.__new__(PlexLocalization)
    plugin._scheduler = None

    with patch("plexlocalization.MediaServerHelper"), \
            patch.object(plugin, "_PlexLocalization__get_tags", return_value={"Action": "动作"}), \
            patch.object(plugin, "stop_service"), \
            patch("plexlocalization.BackgroundScheduler"), \
            patch.object(plugin, "update_config"):
        plugin.init_plugin({"tags_json": "{}"})

    assert plugin._thread_count == 3


def test_stop_service_sets_event_without_private_scheduler():
    """主程序停止插件时不应依赖入库任务的私有 scheduler。"""
    plugin = _plugin()
    plugin._scheduler = None
    plugin._event.clear()

    plugin.stop_service()

    assert plugin._event.is_set()


def test_process_items_batch_aggregates_chunk_outcomes():
    """业务批次应合并多个 HTTP 子块的四项结果。"""
    plugin = _plugin()
    plex = _FakePlex(final_item={})
    rating_keys = [str(index) for index in range(150)]
    with patch.object(
        plugin,
        "_PlexLocalization__process_items_chunk",
        side_effect=[
            {"updated": 10, "failed": 20, "skipped": 70, "unprocessed": 0},
            {"updated": 5, "failed": 5, "skipped": 30, "unprocessed": 10},
        ],
    ):
        result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=rating_keys)

    assert result == {"updated": 15, "failed": 25, "skipped": 100, "unprocessed": 10}


def test_process_items_batch_isolates_item_exceptions():
    """单条异常应计为失败并继续处理同批后续条目。"""
    plugin = _plugin()
    plex = _FakePlex(final_item={})
    items = [{"ratingKey": "1"}, {"ratingKey": "2"}, {"ratingKey": "3"}]

    with patch.object(plugin, "_PlexLocalization__fetch_all_items", return_value=items), \
            patch.object(
                plugin,
                "_PlexLocalization__prepare_item_edit",
                side_effect=[None, RuntimeError("broken item"), None]
            ) as prepare_item, patch("plexlocalization.logger.error") as error:
        result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=["1", "2", "3"])

    assert result == {"updated": 0, "failed": 1, "skipped": 2, "unprocessed": 0}
    assert prepare_item.call_count == 3
    assert any("ratingKey=2" in str(call.args[0]) for call in error.call_args_list)


def test_process_items_batch_counts_missing_response_items_as_failed():
    """批量读取缺失的请求条目应进入失败统计并保留其余结果。"""
    plugin = _plugin()
    plex = _FakePlex(final_item={})
    items = [{"ratingKey": "1"}, {"ratingKey": "3"}]

    with patch.object(plugin, "_PlexLocalization__fetch_all_items", return_value=items), \
            patch.object(plugin, "_PlexLocalization__prepare_item_edit", return_value=None), \
            patch("plexlocalization.logger.warning") as warning:
        result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=["1", "2", "3"])

    assert result == {"updated": 0, "failed": 1, "skipped": 2, "unprocessed": 0}
    assert any("ratingKey=2" in str(call.args[0]) for call in warning.call_args_list)
