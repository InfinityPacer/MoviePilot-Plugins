"""
SubscribeAssistant 下载任务处理与超时管理单测。

覆盖业务域：
- 下载任务处理：__process_download_task
- 超时动作判定：__check_download_timeout_action
- 超时参数获取：__get_download_timeout_progress_threshold / __get_download_timeout_retry_limit /
  __get_download_timeout_retry_window_seconds
- 超时范围键：__get_timeout_scope_key
- 超时状态管理：__get_download_timeout_state / __refresh_download_progress_baseline /
  __record_download_timeout_failure / __mark_download_timeout_manual_review /
  __clear_download_timeout_state / __handle_download_timeout_manual_review
- 种子任务清理：__clean_torrent_task_by_hash / __reset_subscribe_task_pending
- 删除后续：__handle_timeout_seed_deletion / __rollback_best_version_priority
- 删除记录清理：__process_delete_task
"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType

from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def make_plugin(**overrides) -> SubscribeAssistant:
    plugin = object.__new__(SubscribeAssistant)
    plugin.downloader_helper = MagicMock()
    plugin.subscribe_oper = MagicMock()
    plugin.downloadhistory_oper = MagicMock()
    plugin.transferhistory_oper = MagicMock()
    plugin.tmdb_chain = MagicMock()
    plugin._notify = False
    plugin._delete_exclude_tags = ""
    plugin._auto_download_delete = True
    plugin._manual_delete_listen = True
    plugin._tracker_response_listen = True
    plugin._auto_download_pending = True
    plugin._auto_search_when_delete = False
    plugin._download_timeout = 3
    plugin._download_timeout_progress_threshold = 5
    plugin._download_timeout_retry_limit = 3
    plugin._download_timeout_ignore_hours = 48
    plugin._tracker_responses = []
    plugin._timeout_history_cleanup = None
    plugin._skip_deletion = True
    plugin.get_data = MagicMock(return_value={})
    plugin.save_data = MagicMock()
    plugin.post_message = MagicMock()
    plugin.update_config = MagicMock()
    plugin._download_pending_hash_grace_seconds = 300
    for k, v in overrides.items():
        setattr(plugin, k, v)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=0, best_version_full=0, start_episode=1, total_episode=12,
        lack_episode=0, state="R", manual_total_episode=0,
        note=[], current_priority=0, episode_priority={},
        backdrop="", poster="", date="2024-01-01 00:00:00",
        last_update="2024-06-01 00:00:00", username="admin",
    )
    base.update(kwargs)
    ns = SimpleNamespace(**base)
    if not hasattr(ns, "to_dict"):
        ns.to_dict = lambda: {k: getattr(ns, k) for k in base}
    return ns


# ===========================================================================
# __get_download_timeout_progress_threshold
# ===========================================================================

class TestGetDownloadTimeoutProgressThreshold:

    def test_normal(self):
        plugin = make_plugin(_download_timeout_progress_threshold=10)
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 10

    def test_none_defaults_to_zero(self):
        plugin = make_plugin(_download_timeout_progress_threshold=None)
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 0

    def test_invalid_string(self):
        plugin = make_plugin(_download_timeout_progress_threshold="abc")
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 5

    def test_clamped_above_100(self):
        plugin = make_plugin(_download_timeout_progress_threshold=200)
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 100

    def test_clamped_below_zero(self):
        plugin = make_plugin(_download_timeout_progress_threshold=-10)
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 0


# ===========================================================================
# __get_download_timeout_retry_limit
# ===========================================================================

class TestGetDownloadTimeoutRetryLimit:

    def test_normal(self):
        plugin = make_plugin(_download_timeout_retry_limit=5)
        assert plugin._SubscribeAssistant__get_download_timeout_retry_limit() == 5

    def test_none_defaults_to_3(self):
        plugin = make_plugin(_download_timeout_retry_limit=None)
        assert plugin._SubscribeAssistant__get_download_timeout_retry_limit() == 3

    def test_invalid_string(self):
        plugin = make_plugin(_download_timeout_retry_limit="abc")
        assert plugin._SubscribeAssistant__get_download_timeout_retry_limit() == 3

    def test_zero_falls_back_to_default(self):
        """0 is falsy, so `0 or 3` gives 3, then max(3,1)=3."""
        plugin = make_plugin(_download_timeout_retry_limit=0)
        assert plugin._SubscribeAssistant__get_download_timeout_retry_limit() == 3

    def test_negative(self):
        """Negative values get clamped to 1 by max(val, 1), but -5 or 3 = -5, max(-5,1) = 1."""
        plugin = make_plugin(_download_timeout_retry_limit=-5)
        assert plugin._SubscribeAssistant__get_download_timeout_retry_limit() == 1


# ===========================================================================
# __get_download_timeout_retry_window_seconds
# ===========================================================================

class TestGetDownloadTimeoutRetryWindowSeconds:

    def test_normal(self):
        plugin = make_plugin(_download_timeout=3, _download_timeout_retry_limit=3)
        result = plugin._SubscribeAssistant__get_download_timeout_retry_window_seconds()
        # max(24, 3*3) = 24 hours = 86400 seconds
        assert result == 24 * 3600

    def test_large_timeout(self):
        plugin = make_plugin(_download_timeout=10, _download_timeout_retry_limit=5)
        result = plugin._SubscribeAssistant__get_download_timeout_retry_window_seconds()
        # max(24, 10*5) = 50 hours
        assert result == 50 * 3600


# ===========================================================================
# __get_timeout_scope_key
# ===========================================================================

class TestGetTimeoutScopeKey:

    def test_movie(self):
        plugin = make_plugin()
        sub = make_subscribe(type=MOVIE)
        task = {"episodes": []}
        result = plugin._SubscribeAssistant__get_timeout_scope_key(sub, task)
        assert result == "movie"

    def test_tv_with_episodes(self):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, season=2)
        task = {"episodes": [3, 1, 2]}
        result = plugin._SubscribeAssistant__get_timeout_scope_key(sub, task)
        assert result == "tv:2:1,2,3"

    def test_tv_no_episodes(self):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, season=1)
        task = {"episodes": []}
        result = plugin._SubscribeAssistant__get_timeout_scope_key(sub, task)
        assert result == "tv:1:unknown"

    def test_tv_none_season(self):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, season=None)
        task = {"episodes": [5]}
        result = plugin._SubscribeAssistant__get_timeout_scope_key(sub, task)
        assert result == "tv:unknown:5"

    def test_tv_single_episode_not_list(self):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, season=1)
        task = {"episodes": 7}
        result = plugin._SubscribeAssistant__get_timeout_scope_key(sub, task)
        assert result == "tv:1:7"


# ===========================================================================
# __get_download_timeout_state
# ===========================================================================

class TestGetDownloadTimeoutState:

    def _call(self, subscribe_task, scope_key):
        return SubscribeAssistant._SubscribeAssistant__get_download_timeout_state(subscribe_task, scope_key)

    def test_creates_nested_dicts(self):
        task = {}
        state = self._call(task, "movie")
        assert state == {}
        assert "timeout_states" in task
        assert "movie" in task["timeout_states"]

    def test_returns_existing(self):
        task = {"timeout_states": {"movie": {"fail_count": 2}}}
        state = self._call(task, "movie")
        assert state["fail_count"] == 2


# ===========================================================================
# __refresh_download_progress_baseline
# ===========================================================================

class TestRefreshDownloadProgressBaseline:

    def _call(self, torrent_task, progress_percent, current_time):
        return SubscribeAssistant._SubscribeAssistant__refresh_download_progress_baseline(
            torrent_task, progress_percent, current_time)

    def test_sets_fields(self):
        task = {}
        self._call(task, 42.5, 1000.0)
        assert task["last_progress_percent"] == 42.5
        assert task["last_progress_check_time"] == 1000.0


# ===========================================================================
# __record_download_timeout_failure
# ===========================================================================

class TestRecordDownloadTimeoutFailure:

    def test_first_failure(self):
        plugin = make_plugin(_download_timeout=3, _download_timeout_retry_limit=3)
        state = {}
        now = time.time()
        result = plugin._SubscribeAssistant__record_download_timeout_failure(
            state, {"hash": "h1"}, 1.5, now)
        assert result["fail_count"] == 1
        assert result["last_torrent_hash"] == "h1"
        assert result["window_start"] == now

    def test_increment_failure(self):
        plugin = make_plugin(_download_timeout=3, _download_timeout_retry_limit=3)
        now = time.time()
        state = {"fail_count": 1, "window_start": now - 100}
        result = plugin._SubscribeAssistant__record_download_timeout_failure(
            state, {"hash": "h2"}, 0.5, now)
        assert result["fail_count"] == 2
        assert result["last_torrent_hash"] == "h2"

    def test_window_expired_resets(self):
        plugin = make_plugin(_download_timeout=1, _download_timeout_retry_limit=1)
        now = time.time()
        # retry window = max(24, 1*1)=24h = 86400s; expired if window_start + 86400 < now
        state = {"fail_count": 5, "window_start": now - 100000}
        result = plugin._SubscribeAssistant__record_download_timeout_failure(
            state, {"hash": "h3"}, 0.1, now)
        assert result["fail_count"] == 1  # reset and counted

    def test_invalid_window_start_uses_current_time(self):
        plugin = make_plugin(_download_timeout=3, _download_timeout_retry_limit=3)
        now = time.time()
        state = {"fail_count": 1, "window_start": "bad"}
        result = plugin._SubscribeAssistant__record_download_timeout_failure(
            state, {"hash": "h4"}, 0.1, now)
        assert result["window_start"] == now
        assert result["fail_count"] == 2


# ===========================================================================
# __mark_download_timeout_manual_review
# ===========================================================================

class TestMarkDownloadTimeoutManualReview:

    def test_sets_fields(self):
        plugin = make_plugin(_download_timeout_ignore_hours=24)
        state = {}
        now = time.time()
        plugin._SubscribeAssistant__mark_download_timeout_manual_review(state, {"hash": "h1"}, now)
        assert state["ignore_until"] == now + 24 * 3600
        assert state["last_torrent_hash"] == "h1"
        assert state["notified_at"] == now


# ===========================================================================
# __clear_download_timeout_state
# ===========================================================================

class TestClearDownloadTimeoutState:

    def test_clears_state(self):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, season=1)
        task = {"timeout_states": {"tv:1:1,2": {"fail_count": 3}}}
        torrent_task = {"episodes": [1, 2]}
        plugin._SubscribeAssistant__clear_download_timeout_state(task, sub, torrent_task)
        assert "tv:1:1,2" not in task["timeout_states"]

    def test_no_subscribe_task(self):
        plugin = make_plugin()
        sub = make_subscribe()
        plugin._SubscribeAssistant__clear_download_timeout_state(None, sub, {})

    def test_no_timeout_states(self):
        plugin = make_plugin()
        sub = make_subscribe()
        task = {}
        plugin._SubscribeAssistant__clear_download_timeout_state(task, sub, {})

    def test_empty_timeout_states_noop(self):
        plugin = make_plugin()
        sub = make_subscribe()
        task = {"timeout_states": {}}
        plugin._SubscribeAssistant__clear_download_timeout_state(task, sub, {})
        assert task["timeout_states"] == {}


# ===========================================================================
# __handle_download_timeout_manual_review
# ===========================================================================

class TestHandleDownloadTimeoutManualReview:

    def test_no_notify(self):
        plugin = make_plugin(_notify=False)
        sub = make_subscribe()
        plugin._SubscribeAssistant__handle_download_timeout_manual_review(
            sub, {"hash": "h1", "title": "T", "description": "D"}, "reason")
        plugin.post_message.assert_not_called()

    def test_with_notify(self):
        plugin = make_plugin(_notify=True, _download_timeout_ignore_hours=48)
        sub = make_subscribe()
        plugin._SubscribeAssistant__handle_download_timeout_manual_review(
            sub, {"hash": "h1", "title": "T", "description": "D"}, "timeout reason")
        plugin.post_message.assert_called_once()
        call_kwargs = plugin.post_message.call_args[1]
        assert "手动处理" in call_kwargs["title"]


# ===========================================================================
# __check_download_timeout_action
# ===========================================================================

class TestCheckDownloadTimeoutAction:

    def _make_context(self, plugin, **task_overrides):
        sub = make_subscribe(type=TV, season=1)
        sub_task = {"timeout_states": {}}
        torrent_task = {
            "hash": "h1", "timeout_check": True, "episodes": [1],
            "last_progress_check_time": None, "last_progress_percent": None,
        }
        torrent_task.update(task_overrides)
        torrent_info = {
            "downloaded": 500, "target_size": 1000, "total_size": 1000,
            "dltime": 14400,
        }
        return sub, sub_task, torrent_task, torrent_info

    def test_timeout_check_disabled(self):
        plugin = make_plugin()
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        torrent_task["timeout_check"] = False
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "wait"
        assert reason is None

    def test_auto_download_delete_disabled(self):
        plugin = make_plugin(_auto_download_delete=False)
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "wait"

    def test_first_check_initializes_baseline(self):
        plugin = make_plugin()
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "wait"
        assert "last_progress_percent" in torrent_task
        assert torrent_task["last_progress_percent"] is not None

    def test_within_timeout_window(self):
        """在超时窗口内返回 wait。"""
        plugin = make_plugin(_download_timeout=10)  # 10 hours
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        now = time.time()
        torrent_task["last_progress_check_time"] = now - 100  # 100s ago, far from 10h
        torrent_task["last_progress_percent"] = 45.0
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "wait"

    def test_progress_above_threshold_refreshes(self):
        """超时窗口过后但进度增长超过阈值，刷新基线。"""
        plugin = make_plugin(_download_timeout=1, _download_timeout_progress_threshold=5)
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        now = time.time()
        torrent_task["last_progress_check_time"] = now - 7200  # 2h ago
        torrent_task["last_progress_percent"] = 40.0
        # current progress = 500/1000 = 50%, delta = 10% > 5%
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "wait"
        assert torrent_task["last_progress_percent"] == 50.0

    def test_timeout_triggers_delete(self):
        """超时窗口过后进度不足，首次返回 delete。"""
        plugin = make_plugin(_download_timeout=1, _download_timeout_progress_threshold=5,
                             _download_timeout_retry_limit=3)
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        now = time.time()
        torrent_task["last_progress_check_time"] = now - 7200
        torrent_task["last_progress_percent"] = 49.0  # delta = 50-49 = 1% < 5%
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "delete"
        assert reason is not None

    def test_timeout_triggers_manual_review(self):
        """连续超时达到上限返回 manual_review。"""
        plugin = make_plugin(_download_timeout=1, _download_timeout_progress_threshold=5,
                             _download_timeout_retry_limit=1, _download_timeout_ignore_hours=48)
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        now = time.time()
        torrent_task["last_progress_check_time"] = now - 7200
        torrent_task["last_progress_percent"] = 49.5
        # Pre-set fail_count to hit limit
        scope_key = plugin._SubscribeAssistant__get_timeout_scope_key(sub, torrent_task)
        sub_task.setdefault("timeout_states", {})[scope_key] = {
            "fail_count": 0, "window_start": now - 100
        }
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "manual_review"

    def test_ignore_period_active(self):
        """保护期内返回 ignore。"""
        plugin = make_plugin(_download_timeout=1, _download_timeout_ignore_hours=48)
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        now = time.time()
        scope_key = plugin._SubscribeAssistant__get_timeout_scope_key(sub, torrent_task)
        sub_task.setdefault("timeout_states", {})[scope_key] = {
            "last_torrent_hash": "h1",
            "ignore_until": now + 86400,
        }
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "ignore"

    def test_invalid_baseline_refreshes(self):
        """基线值无法解析时刷新并返回 wait。"""
        plugin = make_plugin(_download_timeout=1)
        sub, sub_task, torrent_task, torrent_info = self._make_context(plugin)
        torrent_task["last_progress_check_time"] = "invalid"
        torrent_task["last_progress_percent"] = "bad"
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            sub, sub_task, torrent_task, torrent_info, 14400)
        assert action == "wait"


# ===========================================================================
# __reset_subscribe_task_pending
# ===========================================================================

class TestResetSubscribeTaskPending:

    def test_empty_tasks(self):
        plugin = make_plugin()
        plugin._SubscribeAssistant__reset_subscribe_task_pending({})

    def test_none_tasks(self):
        plugin = make_plugin()
        plugin._SubscribeAssistant__reset_subscribe_task_pending(None)

    def test_subscribe_not_found(self):
        plugin = make_plugin()
        plugin.subscribe_oper.get.return_value = None
        tasks = {"1": {"id": 1, "torrent_tasks": []}}
        plugin._SubscribeAssistant__reset_subscribe_task_pending(tasks)
        plugin.subscribe_oper.update.assert_not_called()

    def test_state_p_no_pending_resets_to_r(self):
        plugin = make_plugin()
        sub = make_subscribe(state="P")
        plugin.subscribe_oper.get.return_value = sub
        tasks = {
            "1": {
                "id": 1, "name": "测试剧", "year": "2024", "type": TV, "season": 1,
                "episode_group": None, "tmdbid": 100, "doubanid": None,
                "torrent_tasks": [],
            }
        }
        plugin._SubscribeAssistant__reset_subscribe_task_pending(tasks)
        plugin.subscribe_oper.update.assert_called_once_with(1, {"state": "R"})


# ===========================================================================
# __handle_timeout_seed_deletion
# ===========================================================================

class TestHandleTimeoutSeedDeletion:

    def test_none_subscribe(self):
        plugin = make_plugin()
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=None, subscribe_task={}, torrent_task={},
            triggered_subscribe_ids=set(), reason="test")
        plugin.subscribe_oper.update.assert_not_called()

    def test_unknown_type(self):
        plugin = make_plugin()
        sub = make_subscribe(type="invalid")
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task={},
            triggered_subscribe_ids=set(), reason="test")
        plugin.subscribe_oper.update.assert_not_called()

    def test_tv_updates_note_and_lack(self):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, note=[1, 2, 3], total_episode=12, start_episode=1)
        torrent_task = {"episodes": [2, 3], "title": "T", "description": "D"}
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task=torrent_task,
            triggered_subscribe_ids=set(), reason="超时")
        update_args = plugin.subscribe_oper.update.call_args
        payload = update_args[1] if update_args[1] else update_args[0][1]
        assert set(payload["note"]) == {1}
        assert payload["lack_episode"] == 11  # 12 - 0 - 1 = 11

    def test_movie_clears_note(self):
        plugin = make_plugin()
        sub = make_subscribe(type=MOVIE)
        torrent_task = {"episodes": [], "title": "T", "description": "D"}
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task=torrent_task,
            triggered_subscribe_ids=set(), reason="超时")
        update_args = plugin.subscribe_oper.update.call_args
        payload = update_args[1] if update_args[1] else update_args[0][1]
        assert payload["note"] == []

    @patch("subscribeassistant.threading.Timer")
    def test_auto_search_when_delete(self, mock_timer_cls):
        plugin = make_plugin(_auto_search_when_delete=True)
        sub = make_subscribe(type=MOVIE)
        torrent_task = {"episodes": [], "title": "T", "description": "D"}
        triggered = set()
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task=torrent_task,
            triggered_subscribe_ids=triggered, reason="超时")
        assert sub.id in triggered
        mock_timer_cls.assert_called_once()

    @patch("subscribeassistant.threading.Timer")
    def test_no_duplicate_search(self, mock_timer_cls):
        plugin = make_plugin(_auto_search_when_delete=True)
        sub = make_subscribe(type=MOVIE)
        torrent_task = {"episodes": [], "title": "T", "description": "D"}
        triggered = {sub.id}
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task=torrent_task,
            triggered_subscribe_ids=triggered, reason="超时")
        mock_timer_cls.assert_not_called()

    def test_notify_on(self):
        plugin = make_plugin(_notify=True)
        sub = make_subscribe(type=MOVIE)
        torrent_task = {"episodes": [], "title": "T", "description": "D"}
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task=torrent_task,
            triggered_subscribe_ids=set(), reason="超时")
        plugin.post_message.assert_called_once()

    def test_best_version_rollback(self):
        plugin = make_plugin()
        sub = make_subscribe(type=MOVIE, best_version=1, current_priority=80)
        sub_torrent_task = {"contributed_priority": 80, "current_priority_baseline": 50}
        torrent_task = {"episodes": [], "title": "T", "description": "D"}
        plugin._SubscribeAssistant__handle_timeout_seed_deletion(
            subscribe=sub, subscribe_task={}, torrent_task=torrent_task,
            subscribe_torrent_task=sub_torrent_task,
            triggered_subscribe_ids=set(), reason="超时")
        update_args = plugin.subscribe_oper.update.call_args
        payload = update_args[1] if update_args[1] else update_args[0][1]
        assert payload["current_priority"] == 50


# ===========================================================================
# __rollback_best_version_priority
# ===========================================================================

class TestRollbackBestVersionPriority:

    def test_no_baseline_task(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1)
        update = {}
        plugin._SubscribeAssistant__rollback_best_version_priority(sub, None, update)
        assert "current_priority" not in update

    def test_movie_rollback(self):
        plugin = make_plugin()
        sub = make_subscribe(type=MOVIE, best_version=1, current_priority=80)
        baseline = {"contributed_priority": 80, "current_priority_baseline": 50}
        update = {}
        plugin._SubscribeAssistant__rollback_best_version_priority(sub, baseline, update)
        assert update["current_priority"] == 50

    def test_movie_no_rollback_if_overwritten(self):
        """当前优先级已被更高存活种子覆盖，不回滚。"""
        plugin = make_plugin()
        sub = make_subscribe(type=MOVIE, best_version=1, current_priority=90)
        baseline = {"contributed_priority": 80, "current_priority_baseline": 50}
        update = {}
        plugin._SubscribeAssistant__rollback_best_version_priority(sub, baseline, update)
        assert "current_priority" not in update

    @patch("subscribeassistant.SubscribeChain")
    def test_episode_rollback(self, mock_chain_cls):
        plugin = make_plugin()
        mock_chain = MagicMock()
        mock_chain.get_best_version_current_priority.return_value = 60
        mock_chain_cls.return_value = mock_chain
        sub = make_subscribe(type=TV, best_version=1, episode_priority={"1": 80, "2": 80, "3": 50})
        baseline = {
            "contributed_priority": 80,
            "episode_priority_baseline": {"1": 50, "2": 0},
        }
        update = {}
        plugin._SubscribeAssistant__rollback_best_version_priority(sub, baseline, update)
        ep = update["episode_priority"]
        assert ep["1"] == 50
        assert "2" not in ep  # old=0 -> popped
        assert ep.get("3") == 50  # untouched


# ===========================================================================
# __process_delete_task
# ===========================================================================

class TestProcessDeleteTask:

    def test_empty_tasks(self):
        plugin = make_plugin(_timeout_history_cleanup=24)
        tasks = {}
        plugin._SubscribeAssistant__process_delete_task(tasks)
        assert tasks == {}

    def test_none_tasks(self):
        plugin = make_plugin(_timeout_history_cleanup=24)
        plugin._SubscribeAssistant__process_delete_task(None)

    def test_cleanup_disabled(self):
        plugin = make_plugin(_timeout_history_cleanup=None)
        tasks = {"h1": {"delete_time": 100}}
        plugin._SubscribeAssistant__process_delete_task(tasks)
        assert "h1" in tasks

    def test_cleanup_zero(self):
        plugin = make_plugin(_timeout_history_cleanup=0)
        tasks = {"h1": {"delete_time": 100}}
        plugin._SubscribeAssistant__process_delete_task(tasks)
        assert "h1" in tasks

    def test_expired_removed(self):
        plugin = make_plugin(_timeout_history_cleanup=1)  # 1 hour
        now = time.time()
        tasks = {
            "h1": {"delete_time": now - 7200},  # 2h ago, expired
            "h2": {"delete_time": now - 100},   # recent, keep
        }
        plugin._SubscribeAssistant__process_delete_task(tasks)
        assert "h1" not in tasks
        assert "h2" in tasks

    def test_no_delete_time_removed(self):
        plugin = make_plugin(_timeout_history_cleanup=1)
        tasks = {"h1": {}}
        plugin._SubscribeAssistant__process_delete_task(tasks)
        assert "h1" not in tasks


# ===========================================================================
# __clean_torrent_task_by_hash
# ===========================================================================

class TestCleanTorrentTaskByHash:

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__handle_timeout_seed_deletion")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__with_lock_and_update_delete_tasks")
    def test_removes_hash_and_calls_downstream(self, mock_lock, mock_deletion):
        plugin = make_plugin()
        sub = make_subscribe()
        sub_task = {"torrent_tasks": [{"hash": "h1"}, {"hash": "h2"}]}
        torrent_tasks = {"h1": {"subscribe_id": 1}, "h2": {"subscribe_id": 1}}
        triggered = set()

        plugin._SubscribeAssistant__clean_torrent_task_by_hash(
            subscribe=sub, subscribe_task=sub_task,
            subscribe_torrent_tasks=sub_task["torrent_tasks"],
            triggered_subscribe_ids=triggered,
            torrent_hash="h1", torrent_task=torrent_tasks["h1"],
            torrent_tasks=torrent_tasks, reason="超时", reason_type="timeout")

        assert "h1" not in torrent_tasks
        assert len(sub_task["torrent_tasks"]) == 1
        mock_lock.assert_called_once()
        mock_deletion.assert_called_once()
