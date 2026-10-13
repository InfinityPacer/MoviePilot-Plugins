"""插件调用主程序订阅 Chain 时的入参合同回归测试。

SubscribeOper 返回 ORM 记录，而 Chain 的回填与进度刷新会对入参执行 dataclasses.replace()，
只接受仓储快照。这里用真实 Chain、真实订阅仓储和 SQLite 验证插件以 ORM 记录发起时仍能落库。
"""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.chain.context import (
    configure_chain_runtime_context_provider,
    get_chain_runtime_context,
)
from app.application.subscription.mutation import SubscriptionMutation
from app.db.adapters.subscription import TransactionalSubscriptionRepository
from app.db.base import Base
from app.db.models.subscribe import Subscribe
from app.db.oper.subscribe import SubscribeOper
from app.plugins.subscribeassistantenhanced.best_version.priority import PriorityManager
from app.schemas.types import MediaType


@pytest.fixture
def chain_runtime(tmp_path):
    """装配真实订阅仓储与修改 scope，让插件内部新建的 SubscribeChain 读写同一 SQLite。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'chain-snapshot.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(Subscribe(
            id=456, name="遮天", year="2023", type=MediaType.TV.value,
            media_source="themoviedb", media_id="224839", season=1, state="R",
            total_episode=4, start_episode=1, lack_episode=4, note=[],
            best_version=1, best_version_full=0, current_priority=0,
            episode_priority={}, sites=[1],
        ))
        session.commit()

    repository = TransactionalSubscriptionRepository(sessions, None)

    def update(subscribe_id, payload):
        """插件兼容写库入口显式提交，返回值与 SubscribeOper.update 一样不被调用方依赖。"""
        with sessions() as session:
            SubscribeOper(session).update(subscribe_id, payload)
            session.commit()

    def mutate(subscribe_id, payload, _actor, *, existing, scene):
        """省略修改事件通知，只保留 Chain 写库与返回快照的契约。"""
        update(subscribe_id, payload)
        snapshot = repository.get(subscribe_id)
        return SubscriptionMutation(snapshot=snapshot, old=existing.to_dict(), new=snapshot.to_dict())

    @contextmanager
    def mutation_scope():
        yield SimpleNamespace(update=mutate)

    context = replace(
        get_chain_runtime_context(),
        subscription_repository=repository,
        sync_subscription_mutation_scope=mutation_scope,
    )
    configure_chain_runtime_context_provider(lambda: context)

    def load_orm():
        """模拟插件经 SubscribeOper 取得的脱离 Session 的 ORM 记录。"""
        with sessions() as session:
            return session.get(Subscribe, 456)

    oper = SimpleNamespace(get=lambda _sid: load_orm(), update=update)
    store = {}
    manager = PriorityManager(
        task_data_read=lambda key: store.get(key, {}),
        task_data_update=lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        subscribe_oper=oper,
    )
    try:
        yield SimpleNamespace(
            sessions=sessions, repository=repository, manager=manager, load_orm=load_orm, store=store,
        )
    finally:
        engine.dispose()


def test_backfill_existing_accepts_orm_subscribe(chain_runtime):
    """普通转洗版回填时插件持有 ORM 记录，Chain 仍按快照合同把在库集写成下载事实。"""
    subscribe = chain_runtime.load_orm()

    assert chain_runtime.manager.backfill_existing(subscribe, [1, 2], scene="subscribe_modified") is True

    snapshot = chain_runtime.repository.get(456)
    assert snapshot.note == [1, 2]
    assert snapshot.episode_priority["1"] == snapshot.episode_priority["2"] == 100


def test_episode_wash_complete_accepts_orm_subscribe(chain_runtime):
    """分集洗版超时完成时逐集回填目标范围，不因 ORM 入参中断。"""
    chain_runtime.manager.mark_full_best_version_complete(chain_runtime.load_orm())

    snapshot = chain_runtime.repository.get(456)
    assert snapshot.note == [1, 2, 3, 4]
    assert snapshot.episode_priority == {str(episode): 100 for episode in range(1, 5)}


def test_torrent_rollback_refreshes_progress_from_orm_subscribe(chain_runtime):
    """删种回滚写回按集优先级后，主程序进度刷新基于已落库快照执行。"""
    manager = chain_runtime.manager
    manager.capture_torrent_baseline(chain_runtime.load_orm(), "A", episodes=[1], contributed_priority=80)
    with chain_runtime.sessions() as session:
        session.get(Subscribe, 456).episode_priority = {"1": 80}
        session.commit()

    manager.rollback_torrent(chain_runtime.load_orm(), "A")

    assert chain_runtime.repository.get(456).episode_priority == {"1": 0}
