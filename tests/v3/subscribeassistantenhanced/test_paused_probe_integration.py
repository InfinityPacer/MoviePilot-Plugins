"""暂停补搜跨插件 Timer、宿主持久队列和下载命中恢复的回归测试。"""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.application.chain.context import get_chain_runtime_context
from app.application.subscription.contract import subscribe_media_key
from app.application.subscription.execution import SubscriptionExecutionAdmission
from app.application.subscription.mutation import SubscriptionMutation
from app.chain.download import DownloadChain
from app.chain.media import MediaChain
from app.chain.search.facade import SearchChain
from app.chain.subscribe.facade import SubscribeChain
from app.db.adapters.subscription import TransactionalSubscriptionRepository
from app.db.adapters.subscriptionsearch import TransactionalSubscriptionSearchRepository
from app.db.base import Base
from app.db.models.subscribe import Subscribe
from app.db.models.subscriptionsearch import SubscriptionSearchTask
from app.db.oper.subscribe import SubscribeOper
from app.domain.context import Context, MediaInfo, TorrentInfo
from app.domain.metainfo import MetaInfo
from app.plugins.subscribeassistantenhanced.engine.types import PauseRecord
from app.plugins.subscribeassistantenhanced.events import EventProxy
from app.plugins.subscribeassistantenhanced.lifecycle import SubscribeLifecycleCoordinator
from app.plugins.subscribeassistantenhanced.pause.manager import PauseManager
from app.plugins.subscribeassistantenhanced.pause.probe import (
    PROBE_LAST_SCHEDULED_AT,
    PROBE_REASON,
    PROBE_SCHEDULED_RUN_AT,
    PausedProbeCoordinator,
)
from app.schemas.mediaserver import NotExistMediaInfo
from app.schemas.types import MediaType


class _Timer:
    """由测试触发真实协调器回调，避免随机等待和后台线程。"""

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.started = False

    def fire(self):
        assert self.started
        self.callback()


@pytest.fixture
def probe_runtime(tmp_path, monkeypatch):
    """装配真实 Chain 和 SQLite，隔离外部服务与非搜索状态通知。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'paused-probe.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        session.add(Subscribe(
            id=440, name="暂停补搜剧", year="2026", type=MediaType.TV.value,
            media_source="themoviedb", media_id="440", season=1, state="S",
            total_episode=12, start_episode=1, lack_episode=12, note=[],
            best_version=0, best_version_full=0, current_priority=0,
            episode_priority={}, sites=[1],
        ))
        session.commit()

    repository = TransactionalSubscriptionRepository(sessions, None)
    queue = TransactionalSubscriptionSearchRepository(sessions)

    def update(subscribe_id, payload):
        """插件兼容写库入口显式提交，随后由真实查询适配器投影快照。"""
        with sessions() as session:
            SubscribeOper(session).update(subscribe_id, payload)
            session.commit()
        return repository.get(subscribe_id)

    def mutate(subscribe_id, payload, _actor, *, existing, scene):
        """省略修改事件通知，仅保留搜索 owner 所需的真实写库与快照契约。"""
        snapshot = update(subscribe_id, payload)
        return SubscriptionMutation(
            snapshot=snapshot, old=existing.to_dict(), new=snapshot.to_dict(),
        )

    @contextmanager
    def mutation_scope():
        yield SimpleNamespace(update=mutate)

    context = replace(
        get_chain_runtime_context(),
        subscription_repository=repository,
        subscription_search_repository=queue,
        sync_subscription_mutation_scope=mutation_scope,
    )
    chain = SubscribeChain(runtime_context=context)
    chain._subscription_execution_admission = SubscriptionExecutionAdmission()
    oper = SimpleNamespace(get=repository.get, list=repository.list, update=update)
    now = 2_000_000.0
    monkeypatch.setattr(
        "app.plugins.subscribeassistantenhanced.pause.manager.time", SimpleNamespace(time=lambda: now),
    )
    store = {"subscribes": {"440": {
        "pause_reason": "no_download", "pause_since": now - 15 * 86400,
        "pause_detail": "长期无下载",
    }}}

    def task_update(key, updater):
        store[key] = updater(store.get(key, {}))
        return store[key]

    config = SimpleNamespace(
        pause_enhanced_enabled=True, paused_probe_reasons=["no_download"],
        paused_probe_min_pause_days=14, paused_probe_interval_hours=72,
    )
    pause = PauseManager(lambda key: store.get(key, {}), task_update, oper)
    lifecycle = SubscribeLifecycleCoordinator(
        config=config, subscribe_oper=oper, pause_manager=pause,
        pending_judge=None, pending_state=None,
    )
    events = EventProxy(
        subscribe_oper=oper, lifecycle=lifecycle,
        pending_download_enabled=False, download_monitor_enabled=False,
    )
    timers = []

    def make_timer(delay, callback):
        timer = _Timer(delay, callback)
        timers.append(timer)
        return timer

    probe = PausedProbeCoordinator(
        config, lambda key: store.get(key, {}), task_update,
        oper, chain, pause, timer_factory=make_timer,
        now_fn=lambda: now, delay_fn=lambda: 120,
    )
    media = MediaInfo(
        media_source="themoviedb", media_id="440", tmdb_id=440,
        title="暂停补搜剧", year="2026", type=MediaType.TV,
    )
    candidate = Context(
        meta_info=MetaInfo("Paused.Probe.S01E01.1080p.WEB-DL"), media_info=media,
        torrent_info=TorrentInfo(title="Paused.Probe.S01E01", pri_order=50),
        selected_episodes=[1],
    )
    media_key = subscribe_media_key(repository.get(440))
    missing = {media_key: {1: NotExistMediaInfo(
        season=1, episodes=list(range(1, 13)), total_episode=12, start_episode=1,
    )}}
    search = Mock(return_value=[])
    monkeypatch.setattr(MediaChain, "recognize_media", lambda _self, **_kwargs: media)
    monkeypatch.setattr(SearchChain, "process", search)
    # 媒体库查询属于外部边界，固定未下载范围；搜索处理、下载复核与完成进度仍真实执行。
    monkeypatch.setattr(chain, "check_and_handle_existing_media", lambda **_kwargs: (False, missing))
    download = Mock()
    monkeypatch.setattr(DownloadChain, "batch_download", download)
    try:
        yield SimpleNamespace(
            sessions=sessions, repository=repository, chain=chain, queue=queue,
            now=now, store=store, pause=pause, events=events, timers=timers,
            probe=probe, search=search, download=download, candidate=candidate,
            media_key=media_key,
        )
    finally:
        probe.stop()
        engine.dispose()


def _fire_probe(runtime):
    """从协调器调度出发，触发未打桩的 SubscribeChain.search 单订阅入口。"""
    runtime.probe.run()
    assert len(runtime.timers) == 1
    assert runtime.repository.get(440).state == "S"
    runtime.timers[0].fire()
    with runtime.sessions() as session:
        task = session.execute(select(SubscriptionSearchTask)).scalar_one()
        assert task.subscription_id == 440
        assert task.source == "targeted"
        assert task.state == "completed", task.last_error
        assert task.attempt_count == 1
    assert runtime.repository.get(440).last_search is not None
    runtime.search.assert_called_once()


def test_paused_probe_reaches_real_search_queue_without_resuming_on_no_results(probe_runtime):
    """无资源时真实队列完成搜索，保持 S 和首次暂停归因，不写恢复保护。"""
    runtime = probe_runtime

    _fire_probe(runtime)

    runtime.download.assert_not_called()
    assert runtime.repository.get(440).state == "S"
    task = runtime.store["subscribes"]["440"]
    assert task["pause_reason"] == "no_download"
    assert task["pause_since"] == runtime.now - 15 * 86400
    assert task[PROBE_LAST_SCHEDULED_AT] == runtime.now
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task
    assert "paused_probe_resume_guard_until" not in task
    runtime.probe.run()
    assert len(runtime.timers) == 1


def test_paused_probe_download_added_restores_running_with_48_hour_guard(probe_runtime):
    """搜索命中通过真实下载复核，DownloadAdded 恢复 R 并阻止同原因打回。"""
    runtime = probe_runtime
    runtime.search.return_value = [runtime.candidate]

    def download(**kwargs):
        # 到下载器边界仍为 S，证明恢复源于下载事实而不是搜索前临时启用。
        assert runtime.repository.get(440).state == "S"
        assert kwargs["contexts"] == [runtime.candidate]
        assert kwargs["governance"].cancelled() is False
        runtime.events.on_download_added(SimpleNamespace(event_data={
            "source": kwargs["source"], "hash": "probe-download-hash",
            "context": runtime.candidate, "episodes": [1], "downloader": "test",
        }))
        return [runtime.candidate], {runtime.media_key: {1: NotExistMediaInfo(
            season=1, episodes=list(range(2, 13)), total_episode=12, start_episode=1,
        )}}

    runtime.download.side_effect = download

    _fire_probe(runtime)

    runtime.download.assert_called_once()
    subscribe = runtime.repository.get(440)
    assert subscribe.state == "R"
    assert subscribe.note == [1]
    assert subscribe.lack_episode == 11
    task = runtime.store["subscribes"]["440"]
    assert "pause_reason" not in task
    assert PROBE_LAST_SCHEDULED_AT not in task
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task
    assert task["paused_probe_resume_guard_reason"] == "no_download"
    assert task["paused_probe_resume_guard_until"] == runtime.now + 48 * 3600
    assert runtime.pause.pause(subscribe, PauseRecord(reason="no_download")) is False
    assert runtime.repository.get(440).state == "R"
