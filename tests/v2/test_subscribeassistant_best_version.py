"""
SubscribeAssistant 洗版相关核心逻辑单测。

覆盖洗版核心纯逻辑：下载前优先级快照采集、删除后按集/标量回滚、按集待定集合收集。
依赖 MoviePilot 后端（app.*）与插件包：根 conftest 会先隔离 CONFIG_DIR 并注入后端、
plugins.v2 到 sys.path；用例用 object.__new__ 绕过插件重初始化，仅验证逻辑方法。
"""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.types import MediaType  # noqa: E402
from subscribeassistant import SubscribeAssistant  # noqa: E402

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


def make_plugin() -> SubscribeAssistant:
    """构造一个绕过 __init__ 的插件实例，仅设置逻辑方法用到的属性。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin._download_pending_hash_grace_seconds = 600
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造逻辑方法所需的最小订阅对象，字段默认值对齐洗版剧集订阅。"""
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=1, best_version_full=0, start_episode=1, total_episode=3,
        episode_priority={}, current_priority=0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_torrent_info(pri_order=80, enclosure="http://x/1.torrent") -> SimpleNamespace:
    """构造资源种子信息，覆盖匹配与采集所需字段。"""
    return SimpleNamespace(
        site=1, site_name="站点", title="测试剧 S01", description="",
        enclosure=enclosure, page_url="http://x/page", pri_order=pri_order,
    )


class CollectPendingEpisodesTest(unittest.TestCase):
    """__collect_pending_episodes：按集待定集合与未知标记。"""

    def setUp(self):
        self.plugin = make_plugin()

    def _call(self, subscribe_task):
        return self.plugin._SubscribeAssistant__collect_pending_episodes(subscribe_task)

    def test_only_alive_pending_counted(self):
        """仅统计待定存活种子，非待定种子不计入。"""
        task = {"torrent_tasks": [
            {"hash": "h1", "pending": True, "episodes": [1]},
            {"hash": "h2", "pending": True, "episodes": [2, 3]},
            {"hash": "h3", "pending": False, "episodes": [4]},
        ]}
        episodes, has_unknown = self._call(task)
        self.assertEqual(episodes, {1, 2, 3})
        self.assertFalse(has_unknown)

    def test_empty_episodes_marks_unknown(self):
        """待定种子集数为空时标记 has_unknown，供调用方保守整体串行。"""
        task = {"torrent_tasks": [
            {"hash": "h1", "pending": True, "episodes": []},
        ]}
        episodes, has_unknown = self._call(task)
        self.assertEqual(episodes, set())
        self.assertTrue(has_unknown)

    def test_expired_hashless_pending_excluded(self):
        """无 hash 待定种子超过宽限期视为失效，不计入待定集。"""
        task = {"torrent_tasks": [
            {"hash": None, "pending": True, "pending_time": time.time() - 10_000, "episodes": [5]},
            {"hash": None, "pending": True, "pending_time": time.time(), "episodes": [6]},
        ]}
        episodes, has_unknown = self._call(task)
        self.assertEqual(episodes, {6})
        self.assertFalse(has_unknown)


class RollbackPriorityTest(unittest.TestCase):
    """__rollback_best_version_priority：按集/标量回滚与归属守卫。"""

    def setUp(self):
        self.plugin = make_plugin()
        # current_priority 标量重算委托新建的 SubscribeChain（其实例化会连 systemconfig 表），
        # 按集回滚用例桩掉整个协作方，仅隔离验证回滚字典与归属守卫，不触碰真实库
        patcher = patch("subscribeassistant.SubscribeChain")
        self.mock_chain_cls = patcher.start()
        self.mock_chain_cls.return_value.get_best_version_current_priority.return_value = 42
        self.addCleanup(patcher.stop)

    def _call(self, subscribe, baseline_task):
        update_data = {}
        self.plugin._SubscribeAssistant__rollback_best_version_priority(
            subscribe=subscribe, baseline_task=baseline_task, update_data=update_data)
        return update_data

    def test_episode_rollback_with_guard(self):
        """剧集洗版按集回滚：本种贡献的集回退旧档，被更高档覆盖的集不动。"""
        # ep1 当前 80（本种贡献，回退到旧档 50），ep2 当前 90（被更高档覆盖，跳过）
        subscribe = make_subscribe(episode_priority={"1": 80, "2": 90}, total_episode=2)
        baseline_task = {
            "contributed_priority": 80,
            "episode_priority_baseline": {"1": 50, "2": 60},
        }
        update_data = self._call(subscribe, baseline_task)
        self.assertEqual(update_data["episode_priority"]["1"], 50)
        self.assertEqual(update_data["episode_priority"]["2"], 90)
        # 标量重算被桩，验证回滚后据回滚结果（仅含归属匹配集）刷新派生量 current_priority
        self.assertEqual(update_data["current_priority"], 42)
        self.mock_chain_cls.return_value.get_best_version_current_priority.assert_called_once_with(
            subscribe, {"1": 50, "2": 90})

    def test_episode_rollback_removes_none_baseline(self):
        """旧档为 None 的集回滚后应删除键，使其可被重新洗回。"""
        subscribe = make_subscribe(episode_priority={"1": 80}, total_episode=1)
        baseline_task = {
            "contributed_priority": 80,
            "episode_priority_baseline": {"1": None},
        }
        update_data = self._call(subscribe, baseline_task)
        self.assertNotIn("1", update_data["episode_priority"])

    def test_movie_scalar_rollback(self):
        """电影洗版标量回滚：当前档由本种贡献时回退旧标量。"""
        subscribe = make_subscribe(type=MOVIE, current_priority=80, best_version_full=0)
        baseline_task = {"contributed_priority": 80, "current_priority_baseline": 30}
        update_data = self._call(subscribe, baseline_task)
        self.assertEqual(update_data["current_priority"], 30)

    def test_movie_scalar_guard_skips_when_superseded(self):
        """电影洗版当前档高于本种贡献（被更高档覆盖）时不回滚。"""
        subscribe = make_subscribe(type=MOVIE, current_priority=90, best_version_full=0)
        baseline_task = {"contributed_priority": 80, "current_priority_baseline": 30}
        update_data = self._call(subscribe, baseline_task)
        self.assertNotIn("current_priority", update_data)

    def test_no_baseline_no_change(self):
        """无下载前快照时不回滚，避免误删按集档位。"""
        subscribe = make_subscribe(episode_priority={"1": 80})
        update_data = self._call(subscribe, {})
        self.assertEqual(update_data, {})


class CaptureBaselineTest(unittest.TestCase):
    """__capture_best_version_priority_baseline：下载前快照采集。"""

    def setUp(self):
        self.plugin = make_plugin()

    def _capture(self, subscribe, torrent_info, episodes):
        subscribe_tasks = {}
        self.plugin._SubscribeAssistant__capture_best_version_priority_baseline(
            subscribe_tasks=subscribe_tasks, subscribe=subscribe,
            torrent_info=torrent_info, episodes=episodes)
        return subscribe_tasks[str(subscribe.id)]["torrent_tasks"][0]

    def test_episode_capture_records_per_episode_baseline(self):
        """分集洗版记录覆盖集的旧 episode_priority 与本种贡献档。"""
        subscribe = make_subscribe(episode_priority={"1": 50}, total_episode=3)
        target = self._capture(subscribe, make_torrent_info(pri_order=80), episodes=[1, 2])
        self.assertEqual(target["contributed_priority"], 80)
        self.assertEqual(target["current_priority_baseline"], 0)
        self.assertEqual(target["episode_priority_baseline"], {"1": 50, "2": None})

    def test_episode_capture_empty_episodes_falls_back_to_target_range(self):
        """整季包 episodes 为空时按目标集范围回填，对齐主程序。"""
        subscribe = make_subscribe(episode_priority={}, start_episode=1, total_episode=3)
        target = self._capture(subscribe, make_torrent_info(), episodes=[])
        self.assertEqual(set(target["episode_priority_baseline"].keys()), {"1", "2", "3"})

    def test_movie_capture_scalar_only(self):
        """电影洗版只记录标量基线，不写按集快照。"""
        subscribe = make_subscribe(type=MOVIE, current_priority=30, total_episode=0)
        target = self._capture(subscribe, make_torrent_info(pri_order=70), episodes=[])
        self.assertEqual(target["current_priority_baseline"], 30)
        self.assertNotIn("episode_priority_baseline", target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
