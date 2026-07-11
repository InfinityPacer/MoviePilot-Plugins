"""Plex 中文本地化全量扫描管线测试。"""

import concurrent.futures
import threading
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from app.testing import stub_modules


_pypinyin = ModuleType("pypinyin")
_pypinyin.Style = SimpleNamespace(FIRST_LETTER="first_letter")
_pypinyin.lazy_pinyin = lambda *args, **kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    from plexlocalization import PlexLocalization


class _Response:
    """提供分页 API 所需的最小响应。"""

    def __init__(self, container, status_code=200):
        self.status_code = status_code
        self._container = container

    def json(self):
        """返回 Plex JSON 包装结构。"""
        return {"MediaContainer": self._container}


class _MalformedResponse(_Response):
    """模拟状态码成功但响应体无法解析。"""

    def __init__(self):
        super().__init__({})

    def json(self):
        """模拟 Plex 返回非 JSON 响应。"""
        raise ValueError("invalid json")


class _MissingContainerResponse(_Response):
    """模拟缺失 Plex 顶层包装字段的响应。"""

    def __init__(self):
        super().__init__({})

    def json(self):
        """返回缺失 MediaContainer 的对象。"""
        return {}


class _PagingPlex:
    """按 endpoint 和 offset 返回测试页并记录请求。"""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    @property
    def starts(self):
        """返回所有分页请求的起始位置。"""
        return [call[1] for call in self.calls]

    def get_data(self, *, endpoint, headers=None, timeout):
        """调用页处理器，None 表示请求失败。"""
        headers = headers or {}
        start = int(headers.get("X-Plex-Container-Start", 0))
        size = int(headers.get("X-Plex-Container-Size", 0))
        self.calls.append((endpoint, start, size, timeout))
        result = self._handler(endpoint, start)
        if result is None:
            return None
        if isinstance(result, _Response):
            return result
        return _Response(result)


class _MetadataPlex:
    """模拟详情读取、原子 PUT 和批量验证。"""

    def __init__(self, source_items, final_items=None):
        self.source_items = source_items
        self.final_items = final_items or source_items
        self.put_calls = []
        self.written_keys = set()
        self.detail_request_sizes = []
        self.verify_request_sizes = []
        self.fail_verification = False
        self.raise_on_detail_call = None
        self.raise_on_put_key = None
        self.on_first_put = None

    def get_data(self, *, endpoint, timeout):
        """写入前返回源状态，写入后返回最终状态。"""
        keys = endpoint.rsplit("/", 1)[-1].split(",")
        is_verification = bool(keys) and all(key in self.written_keys for key in keys)
        if is_verification:
            self.verify_request_sizes.append(len(keys))
            if self.fail_verification:
                return None
            items = [self.final_items[key] for key in keys if key in self.final_items]
        else:
            self.detail_request_sizes.append(len(keys))
            if self.raise_on_detail_call == len(self.detail_request_sizes):
                raise RuntimeError("detail request failed")
            items = [self.source_items[key] for key in keys if key in self.source_items]
        return _Response({"Metadata": items})

    def put_data(self, *, endpoint, params, timeout):
        """记录单条写入并允许测试在首个 PUT 后触发停止。"""
        if str(params["id"]) == self.raise_on_put_key:
            raise RuntimeError("put failed")
        self.put_calls.append({"endpoint": endpoint, "params": params, "timeout": timeout})
        self.written_keys.add(str(params["id"]))
        if len(self.put_calls) == 1 and self.on_first_put:
            self.on_first_put()
        return _Response({}, status_code=200)


class _ConcurrentPlex:
    """通过 barrier 记录真实同时请求数。"""

    def __init__(self, worker_count):
        self._barrier = threading.Barrier(worker_count)
        self._lock = threading.Lock()
        self.active_requests = 0
        self.max_active_requests = 0

    def get_data(self, *, endpoint, timeout):
        """让首轮详情请求同时进入，验证线程上限。"""
        keys = endpoint.rsplit("/", 1)[-1].split(",")
        with self._lock:
            self.active_requests += 1
            self.max_active_requests = max(self.max_active_requests, self.active_requests)
        try:
            self._barrier.wait(timeout=2)
            time.sleep(0.01)
            items = [_media_item(key) for key in keys]
            return _Response({"Metadata": items})
        finally:
            with self._lock:
                self.active_requests -= 1


def _plugin():
    plugin = object.__new__(PlexLocalization)
    plugin._timeout = 10
    plugin._event.clear()
    return plugin


def _edit_plugin():
    plugin = _plugin()
    plugin._lock = False
    plugin._tags = {"Action": "动作"}
    plugin._PlexLocalization__convert_to_pinyin = lambda _title: "PX"
    return plugin


def _library(*, key=1, title="Movies", library_type="movie"):
    return SimpleNamespace(key=key, title=title, type=library_type)


def _metadata(start, count):
    return [{"ratingKey": str(index)} for index in range(start, start + count)]


def _media_item(rating_key, *, needs_update=False, final=False):
    title = f"标题{rating_key}"
    return {
        "ratingKey": str(rating_key),
        "librarySectionID": 1,
        "type": "movie",
        "title": title,
        "titleSort": "PX" if final or not needs_update else title,
        "Field": [],
        "Genre": [],
        "Style": [],
        "Mood": [],
    }


def test_list_rating_keys_pages_until_total_size():
    """完整库应按 500 条分页直到 totalSize。"""
    def handler(_endpoint, start):
        count = 500 if start == 0 else 2
        return {
            "offset": start,
            "totalSize": 502,
            "Metadata": _metadata(start, count),
        }

    plugin = _plugin()
    plex = _PagingPlex(handler)

    keys, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "complete"
    assert len(keys) == 502
    assert plex.starts == [0, 500]
    assert all(call[2] == 500 for call in plex.calls)


def test_list_rating_keys_without_total_size_stops_on_short_page():
    """缺少 totalSize 时短页应作为结束条件。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, start: {
        "offset": start,
        "Metadata": _metadata(start, 2),
    })

    keys, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "complete"
    assert keys == ["0", "1"]
    assert plex.starts == [0]


def test_list_rating_keys_without_total_size_stops_on_empty_page():
    """缺少 totalSize 时完整页后的空页应结束枚举。"""
    def handler(_endpoint, start):
        return {
            "offset": start,
            "Metadata": _metadata(0, 500) if start == 0 else [],
        }

    plugin = _plugin()
    plex = _PagingPlex(handler)

    keys, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "complete"
    assert len(keys) == 500
    assert plex.starts == [0, 500]


def test_list_rating_keys_with_total_size_continues_after_short_page():
    """totalSize 尚未达到时，短页不能被误判为完整枚举。"""
    def handler(_endpoint, start):
        count = 400 if start == 0 else 200
        return {
            "offset": start,
            "totalSize": 600,
            "Metadata": _metadata(start, count),
        }

    plugin = _plugin()
    plex = _PagingPlex(handler)

    keys, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "complete"
    assert len(keys) == 600
    assert plex.starts == [0, 400]


def test_list_rating_keys_advances_by_raw_metadata_count():
    """缺少 ratingKey 的条目仍占用 Plex 分页位置。"""
    def handler(_endpoint, start):
        if start == 0:
            metadata = _metadata(0, 500)
            metadata[10] = {"title": "missing key"}
        else:
            metadata = [{"ratingKey": "last"}]
        return {
            "offset": start,
            "totalSize": 501,
            "Metadata": metadata,
        }

    plugin = _plugin()
    plex = _PagingPlex(handler)

    keys, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "complete"
    assert len(keys) == 500
    assert keys[-1] == "last"
    assert plex.starts == [0, 500]


def test_list_rating_keys_fails_when_total_size_has_unexpected_empty_page():
    """totalSize 尚未达到却返回空页时，枚举结果不可信。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, start: {
        "offset": start,
        "totalSize": 600,
        "Metadata": _metadata(0, 500) if start == 0 else [],
    })

    _, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "failed"
    assert plex.starts == [0, 500]


def test_list_rating_keys_rejects_mismatched_response_offset():
    """响应 offset 与请求不一致时不能继续产生不可信结果。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, _start: {
        "offset": 7,
        "totalSize": 1,
        "Metadata": _metadata(0, 1),
    })

    _, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "failed"


def test_list_rating_keys_rejects_repeated_nonempty_page():
    """Plex 忽略分页起点并重复首个完整页时应停止。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, start: {
        "offset": start,
        "Metadata": _metadata(0, 500),
    })

    _, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "failed"
    assert plex.starts == [0, 500]


def test_list_rating_keys_returns_failed_when_second_page_fails():
    """第二页失败时不得把首个页面当成完整媒体库。"""
    def handler(_endpoint, start):
        if start == 500:
            return None
        return {"offset": 0, "totalSize": 600, "Metadata": _metadata(0, 500)}

    plugin = _plugin()
    plex = _PagingPlex(handler)

    _, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "failed"


def test_list_rating_keys_returns_failed_for_malformed_payload():
    """状态码成功但响应体结构异常时应转为服务级失败。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, _start: {"Metadata": None})

    _, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "failed"


def test_list_rating_keys_returns_failed_without_media_container():
    """缺失 MediaContainer 不能被误判为空库。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, _start: _MissingContainerResponse())

    _, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert status == "failed"


def test_generate_keys_fetches_collections_once_for_artist_library():
    """artist 的三个 type 不应重复请求同一个合集端点。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda endpoint, start: {
        "offset": start,
        "Metadata": [{"ratingKey": endpoint.split("type=")[-1]}]
        if "type=" in endpoint else [{"ratingKey": "collection"}],
    })

    keys, status = plugin._PlexLocalization__generate_all_rating_keys(
        plex=plex,
        libraries={7: _library(key=7, title="Music", library_type="artist")},
        with_collection=True,
    )

    collection_calls = [call for call in plex.calls if call[0].endswith("/collections")]
    assert status == "complete"
    assert keys == ["8", "9", "10", "collection"]
    assert len(collection_calls) == 1


def test_generate_keys_deduplicates_across_types_and_collections():
    """同一 ratingKey 跨普通端点和合集出现时只处理一次。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda endpoint, start: {
        "offset": start,
        "Metadata": [{"ratingKey": "same"}, {"ratingKey": "unique"}]
        if "type=" in endpoint else [{"ratingKey": "same"}],
    })

    keys, status = plugin._PlexLocalization__generate_all_rating_keys(
        plex=plex,
        libraries={1: _library()},
        with_collection=True,
    )

    assert status == "complete"
    assert keys == ["same", "unique"]


def test_list_rating_keys_stops_before_request_when_event_is_set():
    """主程序停止插件后不应发起新的分页请求。"""
    plugin = _plugin()
    plex = _PagingPlex(lambda _endpoint, _start: {"Metadata": []})
    plugin._event.set()

    keys, status = plugin._PlexLocalization__list_rating_keys(
        plex=plex, library=_library(), type_id=1
    )

    assert keys == []
    assert status == "stopped"
    assert plex.calls == []


def test_batch_size_250_uses_100_100_50_detail_chunks():
    """业务批次增大时 HTTP 详情读取仍应限制为 100 个 key。"""
    source_items = {str(index): _media_item(index) for index in range(250)}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source_items)

    result = plugin._PlexLocalization__process_items_batch(
        plex=plex, rating_keys=list(source_items)
    )

    assert plex.detail_request_sizes == [100, 100, 50]
    assert result == {"updated": 0, "failed": 0, "skipped": 250, "unprocessed": 0}


def test_successful_puts_use_one_bulk_verification_get():
    """同一子块中的成功 PUT 应合并回读。"""
    source_items = {str(index): _media_item(index, needs_update=True) for index in range(3)}
    final_items = {str(index): _media_item(index, needs_update=True, final=True) for index in range(3)}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source_items, final_items)

    result = plugin._PlexLocalization__process_items_batch(
        plex=plex, rating_keys=list(source_items)
    )

    assert len(plex.put_calls) == 3
    assert plex.verify_request_sizes == [3]
    assert result == {"updated": 3, "failed": 0, "skipped": 0, "unprocessed": 0}


def test_201_successful_puts_use_100_100_1_verification_gets():
    """跨多个子块的验证请求不得超过 100 个 key。"""
    source_items = {str(index): _media_item(index, needs_update=True) for index in range(201)}
    final_items = {
        str(index): _media_item(index, needs_update=True, final=True)
        for index in range(201)
    }
    plugin = _edit_plugin()
    plex = _MetadataPlex(source_items, final_items)

    result = plugin._PlexLocalization__process_items_batch(
        plex=plex, rating_keys=list(source_items)
    )

    assert plex.verify_request_sizes == [100, 100, 1]
    assert result["updated"] == 201


def test_bulk_verification_marks_mismatched_item_failed():
    """回读字段不一致的条目不能计为更新成功。"""
    source = {"1": _media_item("1", needs_update=True)}
    final = {"1": {**_media_item("1", needs_update=True, final=True), "titleSort": "wrong"}}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source, final)

    result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=["1"])

    assert result == {"updated": 0, "failed": 1, "skipped": 0, "unprocessed": 0}


def test_bulk_verification_marks_missing_item_failed():
    """Plex 批量回读缺失的条目应计失败。"""
    source = {"1": _media_item("1", needs_update=True)}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source, final_items={})
    plex.final_items = {}

    result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=["1"])

    assert result == {"updated": 0, "failed": 1, "skipped": 0, "unprocessed": 0}


def test_bulk_verification_request_failure_marks_pending_items_failed():
    """整次验证读取失败时所有待验证写入均应计失败。"""
    source = {"1": _media_item("1", needs_update=True), "2": _media_item("2", needs_update=True)}
    final = {key: _media_item(key, needs_update=True, final=True) for key in source}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source, final)
    plex.fail_verification = True

    result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=["1", "2"])

    assert result == {"updated": 0, "failed": 2, "skipped": 0, "unprocessed": 0}


def test_put_exception_only_fails_current_item():
    """单条 PUT 异常不得覆盖同一子块内其他条目的结果。"""
    source = {str(index): _media_item(index, needs_update=True) for index in range(1, 4)}
    final = {
        key: _media_item(key, needs_update=True, final=True)
        for key in source
    }
    plugin = _edit_plugin()
    plex = _MetadataPlex(source, final)
    plex.raise_on_put_key = "2"

    result = plugin._PlexLocalization__process_items_batch(
        plex=plex, rating_keys=["1", "2", "3"]
    )

    assert plex.verify_request_sizes == [2]
    assert result == {"updated": 2, "failed": 1, "skipped": 0, "unprocessed": 0}


def test_verification_exception_only_fails_current_item():
    """单条差异比较异常不得覆盖同一子块内其他条目的结果。"""
    source = {str(index): _media_item(index, needs_update=True) for index in range(1, 4)}
    final = {
        key: _media_item(key, needs_update=True, final=True)
        for key in source
    }
    plugin = _edit_plugin()
    plex = _MetadataPlex(source, final)

    def differences(item, expected_sort_title, expected_tags):
        if item["ratingKey"] == "2":
            raise RuntimeError("verification failed")
        return []

    with patch.object(
        plugin,
        "_PlexLocalization__metadata_differences",
        side_effect=differences,
    ):
        result = plugin._PlexLocalization__process_items_batch(
            plex=plex, rating_keys=["1", "2", "3"]
        )

    assert result == {"updated": 2, "failed": 1, "skipped": 0, "unprocessed": 0}


def test_second_chunk_exception_keeps_first_chunk_results():
    """后一子块异常不得覆盖前一子块已终结结果。"""
    source_items = {str(index): _media_item(index) for index in range(150)}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source_items)
    plex.raise_on_detail_call = 2

    result = plugin._PlexLocalization__process_items_batch(
        plex=plex, rating_keys=list(source_items)
    )

    assert result == {"updated": 0, "failed": 50, "skipped": 100, "unprocessed": 0}


def test_stop_after_put_marks_unverified_write_failed():
    """停止发生在 PUT 后时不得继续验证或误报成功。"""
    source = {"1": _media_item("1", needs_update=True), "2": _media_item("2", needs_update=True)}
    final = {key: _media_item(key, needs_update=True, final=True) for key in source}
    plugin = _edit_plugin()
    plex = _MetadataPlex(source, final)
    plex.on_first_put = plugin._event.set

    result = plugin._PlexLocalization__process_items_batch(plex=plex, rating_keys=["1", "2"])

    assert result == {"updated": 0, "failed": 1, "skipped": 0, "unprocessed": 1}
    assert plex.verify_request_sizes == []


def test_pending_futures_never_exceed_twice_thread_count():
    """数万级条目不能让 Future 数随总批次数增长。"""
    plugin = _edit_plugin()
    plex = SimpleNamespace()
    observed_pending = []
    real_wait = concurrent.futures.wait

    def recording_wait(futures, *args, **kwargs):
        observed_pending.append(len(futures))
        return real_wait(futures, *args, **kwargs)

    def skip_batch(_plex, batch_keys):
        return {
            "updated": 0,
            "failed": 0,
            "skipped": len(batch_keys),
            "unprocessed": 0,
        }

    with patch("plexlocalization.concurrent.futures.wait", side_effect=recording_wait), \
            patch.object(plugin, "_PlexLocalization__process_items_batch", side_effect=skip_batch):
        result = plugin._PlexLocalization__process_rating_keys_in_batches(
            plex=plex,
            rating_keys=[str(index) for index in range(10_000)],
            thread_count=3,
            batch_size=100,
        )

    assert observed_pending
    assert max(observed_pending) <= 6
    assert result == {"updated": 0, "failed": 0, "skipped": 10_000, "unprocessed": 0}


def test_second_page_failure_skips_all_puts_and_continues_next_service():
    """一个服务枚举失败不应写入，也不应阻止独立服务继续。"""
    plugin = _edit_plugin()
    plugin._batch_size = 100
    plugin._notify = False
    first_plex = SimpleNamespace(put_calls=[])
    second_plex = SimpleNamespace(put_calls=[])
    services = {
        "first": SimpleNamespace(name="First Plex", instance=first_plex),
        "second": SimpleNamespace(name="Second Plex", instance=second_plex),
    }
    library = _library()
    completed = {"updated": 0, "failed": 0, "skipped": 1, "unprocessed": 0}

    with patch.object(plugin, "service_info", side_effect=lambda name: services[name]), \
            patch.object(
                plugin,
                "_PlexLocalization__generate_all_rating_keys",
                side_effect=[([], "failed"), (["1"], "complete")],
            ), patch.object(
                plugin,
                "_PlexLocalization__process_rating_keys_in_batches",
                return_value=completed,
            ) as process_batches, patch("plexlocalization.logger.warning") as warning:
        plugin._PlexLocalization__loop_all(
            service_libraries={"first": {1: library}, "second": {1: library}},
            thread_count=3,
        )

    assert first_plex.put_calls == []
    assert process_batches.call_count == 1
    assert process_batches.call_args.kwargs["plex"] is second_plex
    assert any("枚举不完整" in str(call.args[0]) for call in warning.call_args_list)


def test_malformed_page_skips_service_and_continues_next_service():
    """单个服务解析失败不得终止后续独立 Plex 服务。"""
    plugin = _edit_plugin()
    plugin._batch_size = 100
    plugin._notify = False
    first_plex = _PagingPlex(lambda _endpoint, _start: _MalformedResponse())
    second_plex = _PagingPlex(lambda endpoint, start: {
        "offset": start,
        "Metadata": [] if endpoint.endswith("/collections") else [{"ratingKey": "1"}],
    })
    services = {
        "first": SimpleNamespace(name="First Plex", instance=first_plex),
        "second": SimpleNamespace(name="Second Plex", instance=second_plex),
    }
    completed = {"updated": 0, "failed": 0, "skipped": 1, "unprocessed": 0}

    with patch.object(plugin, "service_info", side_effect=lambda name: services[name]), \
            patch.object(
                plugin,
                "_PlexLocalization__process_rating_keys_in_batches",
                return_value=completed,
            ) as process_batches:
        plugin._PlexLocalization__loop_all(
            service_libraries={"first": {1: _library()}, "second": {1: _library()}},
            thread_count=3,
        )

    assert process_batches.call_count == 1
    assert process_batches.call_args.kwargs["plex"] is second_plex


def test_loop_defaults_to_three_threads():
    """内部调用未显式传线程数时也应使用新默认值。"""
    plugin = _edit_plugin()
    plugin._batch_size = 100
    plugin._notify = False
    plex = SimpleNamespace()
    service = SimpleNamespace(name="Plex", instance=plex)
    library = _library()

    with patch.object(plugin, "service_info", return_value=service), \
            patch.object(
                plugin,
                "_PlexLocalization__generate_all_rating_keys",
                return_value=(["1"], "complete"),
            ), patch.object(
                plugin,
                "_PlexLocalization__process_rating_keys_in_batches",
                return_value={"updated": 0, "failed": 0, "skipped": 1, "unprocessed": 0},
            ) as process_batches:
        plugin._PlexLocalization__loop_all(
            service_libraries={"plex": {1: library}}, thread_count=None
        )

    assert process_batches.call_args.kwargs["thread_count"] == 3


def test_loop_final_log_includes_service_and_discovered_counts():
    """最终日志应能核对完整服务的发现数与四项处理统计。"""
    plugin = _edit_plugin()
    plugin._batch_size = 100
    plugin._notify = False
    services = {
        "first": SimpleNamespace(name="First Plex", instance=SimpleNamespace()),
        "second": SimpleNamespace(name="Second Plex", instance=SimpleNamespace()),
    }

    def process_batches(*, rating_keys, **_kwargs):
        return {"updated": 0, "failed": 0, "skipped": len(rating_keys), "unprocessed": 0}

    with patch.object(plugin, "service_info", side_effect=lambda name: services[name]), \
            patch.object(
                plugin,
                "_PlexLocalization__generate_all_rating_keys",
                side_effect=[(["1", "2"], "complete"), (["3"], "complete")],
            ), patch.object(
                plugin,
                "_PlexLocalization__process_rating_keys_in_batches",
                side_effect=process_batches,
            ), patch("plexlocalization.logger.info") as info:
        plugin._PlexLocalization__loop_all(
            service_libraries={"first": {1: _library()}, "second": {1: _library()}},
            thread_count=3,
        )

    final_log = str(info.call_args_list[-1].args[0])
    assert "完整服务 2" in final_log
    assert "发现 3" in final_log
    assert "跳过 3" in final_log


def test_stopped_log_preserves_previous_failed_service_count():
    """先失败后停止时，最终日志仍应保留失败服务数。"""
    plugin = _edit_plugin()
    plugin._batch_size = 100
    plugin._notify = False
    services = {
        "first": SimpleNamespace(name="First Plex", instance=SimpleNamespace()),
        "second": SimpleNamespace(name="Second Plex", instance=SimpleNamespace()),
    }

    with patch.object(plugin, "service_info", side_effect=lambda name: services[name]), \
            patch.object(
                plugin,
                "_PlexLocalization__generate_all_rating_keys",
                side_effect=[([], "failed"), ([], "stopped")],
            ), patch("plexlocalization.logger.warning") as warning:
        plugin._PlexLocalization__loop_all(
            service_libraries={"first": {1: _library()}, "second": {1: _library()}},
            thread_count=3,
        )

    final_log = str(warning.call_args_list[-1].args[0])
    assert "失败服务 1" in final_log


def test_stop_cancels_pending_batches_and_counts_unprocessed():
    """停止后未运行的批次必须进入未处理统计。"""
    plugin = _edit_plugin()
    plex = SimpleNamespace()
    total_keys = 1_000

    def stop_after_first_batch(_plex, batch_keys):
        plugin._event.set()
        return {
            "updated": 0,
            "failed": 0,
            "skipped": len(batch_keys),
            "unprocessed": 0,
        }

    with patch.object(
        plugin,
        "_PlexLocalization__process_items_batch",
        side_effect=stop_after_first_batch,
    ):
        result = plugin._PlexLocalization__process_rating_keys_in_batches(
            plex=plex,
            rating_keys=[str(index) for index in range(total_keys)],
            thread_count=3,
            batch_size=100,
        )

    assert sum(result.values()) == total_keys
    assert result["unprocessed"] > 0


def test_processing_http_concurrency_respects_configured_thread_count():
    """实际详情请求并发应由用户线程配置控制。"""
    for thread_count in (3, 2):
        plugin = _edit_plugin()
        plex = _ConcurrentPlex(worker_count=thread_count)
        item_count = thread_count * 100

        result = plugin._PlexLocalization__process_rating_keys_in_batches(
            plex=plex,
            rating_keys=[str(index) for index in range(item_count)],
            thread_count=thread_count,
            batch_size=100,
        )

        assert plex.max_active_requests == thread_count
        assert result["skipped"] == item_count
