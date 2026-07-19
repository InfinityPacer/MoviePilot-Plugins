"""best_version/orchestrator.py 洗版编排单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.types import MediaType

from subscribeassistantenhanced.best_version.orchestrator import BestVersionOrchestrator
from subscribeassistantenhanced.best_version.priority import PriorityManager


def _mediainfo():
    """构造洗版通知需要的媒体信息替身。"""
    return SimpleNamespace(
        vote_average=8.8,
        get_message_image=lambda: "poster.jpg",
        to_dict=lambda: {"title": "测试剧"},
    )


def _sub(ep_priority=None, episode_group=None, **kwargs):
    defaults = dict(
        id=1, name="测试剧", tmdbid=100, season=1,
        episode_priority=ep_priority or {}, current_priority=0,
        episode_group=episode_group,
        save_path="/media", sites="site1", filter="rule1", filter_groups=["group1"],
        best_version=1, best_version_full=1, type="电视剧",
        start_episode=1, total_episode=12, lack_episode=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestBuildPayload:

    def test_preserves_episode_group(self):
        """payload 保留 episode_group。"""
        orch = BestVersionOrchestrator(priority_manager=MagicMock(spec=PriorityManager))
        payload = orch.build_payload(_sub(episode_group="eg-abc"))
        assert payload["episode_group"] == "eg-abc"
        assert payload["best_version"] == 1
        assert payload["manual_total_episode"] == 0

    def test_includes_subscribe_fields(self):
        orch = BestVersionOrchestrator(priority_manager=MagicMock(spec=PriorityManager))
        payload = orch.build_payload(_sub())
        assert "name" in payload
        assert "tmdbid" in payload
        assert "season" in payload
        assert "save_path" in payload
        assert payload["filter"] == "rule1"
        assert payload["filter_groups"] == ["group1"]

    def test_no_episode_group(self):
        orch = BestVersionOrchestrator(priority_manager=MagicMock(spec=PriorityManager))
        payload = orch.build_payload(_sub(episode_group=None))
        assert "episode_group" not in payload or payload.get("episode_group") is None


class TestModeLabel:
    """洗版模式标签只描述真实洗版订阅。"""

    def test_non_best_version_returns_empty_label(self):
        """普通订阅不是洗版形态，标签应为空避免日志误标。"""
        assert BestVersionOrchestrator._mode_label(_sub(best_version=0)) == ""

    def test_episode_and_full_best_version_labels(self):
        """真正洗版和分集洗版使用不同标签。"""
        assert BestVersionOrchestrator._mode_label(_sub(best_version=1, best_version_full=0)) == "分集洗版"
        assert BestVersionOrchestrator._mode_label(_sub(best_version=1, best_version_full=1)) == "洗版"

    def test_movie_best_version_uses_wash_label(self):
        """电影洗版使用真正洗版标签，不使用剧集分集洗版标签。"""
        assert BestVersionOrchestrator._mode_label(
            _sub(type=MediaType.MOVIE, best_version=1, best_version_full=0)
        ) == "洗版"


class TestStartBestVersion:
    """订阅完成后按洗版类型自动创建洗版订阅。"""

    def _orch(self, oper, best_version_type="all", related_downloads_fn=None):
        """构造带自动洗版类型范围的编排器。"""
        return BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            subscribe_oper=oper, best_version_type=best_version_type,
            related_downloads_fn=related_downloads_fn)

    def test_creates_best_version_when_type_enabled(self):
        """创建洗版订阅成功时应发 SubscribeAdded 事件并发送订阅通知。"""
        oper = MagicMock()
        oper.add.return_value = (5, "")
        send_event = MagicMock()
        notify = MagicMock()
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            subscribe_oper=oper,
            best_version_type="all",
            send_subscribe_added_fn=send_event,
            notify_fn=notify,
        )
        sub = _sub(best_version=0, season=1, save_path="/m", sites="s",
                   filter="r", filter_groups=["g1"], episode_group=None)
        sid = orch.start_best_version(sub, mediainfo=_mediainfo())

        assert sid == 5
        send_event.assert_called_once()
        assert send_event.call_args.args[0] == 5
        notify.assert_called_once()
        assert notify.call_args.args[0].endswith("已添加洗版订阅")
        assert "reason" not in notify.call_args.kwargs
        assert "user" not in notify.call_args.kwargs
        _args, kwargs = oper.add.call_args
        assert kwargs["best_version"] == 1 and kwargs["season"] == 1
        assert kwargs["best_version_full"] == 1
        assert kwargs["manual_total_episode"] == 0
        assert kwargs["filter"] == "r"
        assert kwargs["filter_groups"] == ["g1"]

    def test_create_failure_notifies_error_and_image(self):
        """自动创建洗版订阅失败时应推送主程序返回的错误原因。"""
        oper = MagicMock()
        oper.add.return_value = (None, "订阅已存在")
        notify = MagicMock()
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            subscribe_oper=oper,
            best_version_type="all",
            notify_fn=notify,
        )
        sub = _sub(best_version=0)

        sid = orch.start_best_version(sub, mediainfo=_mediainfo())

        assert sid is None
        notify.assert_called_once()
        assert notify.call_args.args[0].endswith("添加洗版订阅失败")
        assert notify.call_args.kwargs["reason"] == "订阅已存在"
        assert "action" not in notify.call_args.kwargs
        assert notify.call_args.kwargs["follow_up"] == "请检查订阅创建错误"
        assert notify.call_args.kwargs["diagnostic"] is True
        assert notify.call_args.kwargs["image"] == "poster.jpg"
        assert "user" not in notify.call_args.kwargs

    def test_skips_when_already_best_version(self):
        oper = MagicMock()
        self._orch(oper).start_best_version(_sub(best_version=1), object())
        oper.add.assert_not_called()

    def test_skips_without_mediainfo(self):
        oper = MagicMock()
        self._orch(oper).start_best_version(_sub(best_version=0), None)
        oper.add.assert_not_called()

    def test_tv_type_skips_movie_subscription(self):
        """剧集洗版范围不应为电影订阅创建洗版。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电影")

        sid = self._orch(oper, best_version_type="tv").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_movie_type_creates_movie_subscription(self):
        """电影洗版范围应为电影订阅创建洗版。"""
        oper = MagicMock()
        oper.add.return_value = (6, "")
        sub = _sub(best_version=0, type=MediaType.MOVIE)

        sid = self._orch(oper, best_version_type="movie").start_best_version(sub, object())

        assert sid == 6
        oper.add.assert_called_once()
        _args, kwargs = oper.add.call_args
        assert "best_version_full" not in kwargs

    def test_movie_best_version_inherits_movie_current_priority(self):
        """电影自动洗版应继承普通订阅本次完成资源的优先级。"""
        oper = MagicMock()
        oper.add.return_value = (6, "")
        sub = _sub(best_version=0, type=MediaType.MOVIE, current_priority=95)

        sid = self._orch(oper, best_version_type="movie").start_best_version(sub, object())

        assert sid == 6
        _args, kwargs = oper.add.call_args
        assert kwargs["current_priority"] == 95

    def test_movie_best_version_invalid_current_priority_defaults_to_zero(self):
        """电影完成快照里的异常优先级按未建立质量基线处理。"""
        oper = MagicMock()
        oper.add.return_value = (6, "")
        sub = _sub(best_version=0, type=MediaType.MOVIE, current_priority="invalid")

        sid = self._orch(oper, best_version_type="movie").start_best_version(sub, object())

        assert sid == 6
        _args, kwargs = oper.add.call_args
        assert kwargs["current_priority"] == 0

    def test_movie_best_version_skips_when_movie_current_priority_is_top(self):
        """电影普通订阅已达顶档时不应再创建洗版订阅，并推送提示。"""
        oper = MagicMock()
        notify = MagicMock()
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            subscribe_oper=oper,
            best_version_type="movie",
            notify_fn=notify,
        )
        sub = _sub(best_version=0, type=MediaType.MOVIE, current_priority=100)

        sid = orch.start_best_version(sub, mediainfo=_mediainfo())

        assert sid is None
        oper.add.assert_not_called()
        notify.assert_called_once()
        assert notify.call_args.args[0].endswith("已达顶档，跳过洗版订阅")
        assert "reason" not in notify.call_args.kwargs
        assert "follow_up" not in notify.call_args.kwargs
        assert notify.call_args.kwargs["image"] == "poster.jpg"

    def test_unknown_media_type_skips_all_scope(self):
        """未知媒体类型不能被 all 范围误当成剧集创建洗版。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type=MediaType.UNKNOWN)

        sid = self._orch(oper, best_version_type="all").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_no_type_skips_all_subscriptions(self):
        """关闭洗版类型范围时不应创建任何洗版订阅。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电影")

        sid = self._orch(oper, best_version_type="no").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_tv_episode_skips_without_related_episode_downloads(self):
        """分集洗版：没有关联分集下载历史时不自动创建洗版订阅。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电视剧")
        related = MagicMock(return_value=[])

        sid = self._orch(
            oper,
            best_version_type="tv_episode",
            related_downloads_fn=related,
        ).start_best_version(sub, object())

        assert sid is None
        related.assert_called_once_with(sub)
        oper.add.assert_not_called()

    def test_tv_episode_skips_single_related_episode_download(self):
        """分集洗版：只有 1 条关联下载历史视为合集/单次下载，不自动洗版。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电视剧")

        sid = self._orch(
            oper,
            best_version_type="tv_episode",
            related_downloads_fn=MagicMock(return_value=[object()]),
        ).start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_tv_episode_creates_when_multiple_related_episode_downloads(self):
        """分集洗版：存在多条关联分集下载历史时创建洗版订阅。"""
        oper = MagicMock()
        oper.add.return_value = (7, "")
        sub = _sub(best_version=0, type="电视剧")

        sid = self._orch(
            oper,
            best_version_type="tv_episode",
            related_downloads_fn=MagicMock(return_value=[object(), object()]),
        ).start_best_version(sub, object())

        assert sid == 7
        oper.add.assert_called_once()
        _args, kwargs = oper.add.call_args
        assert kwargs["best_version_full"] == 1
