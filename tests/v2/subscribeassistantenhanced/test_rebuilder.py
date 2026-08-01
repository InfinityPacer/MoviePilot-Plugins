"""完成快照订阅重建组件单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.types import MediaType, SystemConfigKey

from subscribeassistantenhanced.postcheck.rebuilder import CompletionSubscribeRebuilder


def _sub(**kwargs):
    """构造重建结果校验所需的稳定订阅字段。"""
    values = {
        "tmdbid": 100,
        "season": 1,
        "episode_group": None,
        "best_version": 0,
        "best_version_full": 0,
        "start_episode": 13,
        "total_episode": 15,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _rebuilder(default_config=None, rebuilt=None):
    chain = MagicMock()
    chain.add.return_value = (88, "新增订阅成功")
    oper = MagicMock()
    oper.get.return_value = rebuilt or _sub()
    config_getter = MagicMock(return_value={} if default_config is None else default_config)
    rebuilder = CompletionSubscribeRebuilder(
        subscribe_chain=chain,
        subscribe_oper=oper,
        default_config_getter=config_getter,
        plugin_name="订阅助手（增强版）",
    )
    return rebuilder, chain, oper, config_getter


def test_rebuild_uses_non_full_default_mode_and_preserves_media_config():
    """非全集默认规则优先，并保留媒体专属配置与新增集范围。"""
    rebuilder, chain, _, _ = _rebuilder(
        default_config={"best_version": 1, "best_version_full": 0},
        rebuilt=_sub(episode_group="eg-1", best_version=1),
    )

    result = rebuilder.rebuild(
        {
            "tmdbid": 100,
            "season": 1,
            "episode_group_id": "eg-1",
            "subscribe_config": {"best_version": 0, "best_version_full": 0},
        },
        {
            "name": "测试",
            "year": "2026",
            "quality": "WEB-DL",
            "best_version": 1,
            "best_version_full": 1,
            "start_episode": 13,
            "total_episode": 15,
            "lack_episode": 3,
            "manual_total_episode": 92,
        },
    )

    assert result is True
    call = chain.add.call_args.kwargs
    assert call["title"] == "测试"
    assert call["year"] == "2026"
    assert call["mtype"] == MediaType.TV
    assert call["tmdbid"] == 100
    assert call["season"] == 1
    assert call["episode_group"] == "eg-1"
    assert call["quality"] == "WEB-DL"
    assert call["start_episode"] == 13
    assert call["total_episode"] == 15
    assert call["lack_episode"] == 3
    assert call["manual_total_episode"] == 0
    assert call["state"] == "N"
    assert call["message"] is False
    assert call["exist_ok"] is True
    assert call["best_version"] == 1
    assert call["best_version_full"] == 0


def test_full_default_restores_snapshot_episode_mode():
    """全集默认规则下，原分集洗版快照恢复为分集洗版。"""
    rebuilder, chain, _, _ = _rebuilder(
        default_config={"best_version": 1, "best_version_full": 1},
        rebuilt=_sub(best_version=1),
    )

    assert rebuilder.rebuild(
        {
            "tmdbid": 100,
            "season": 1,
            "subscribe_config": {"best_version": 1, "best_version_full": 0},
        },
        {"name": "测试", "start_episode": 13, "total_episode": 15, "lack_episode": 3},
    ) is True
    assert chain.add.call_args.kwargs["best_version"] == 1
    assert chain.add.call_args.kwargs["best_version_full"] == 0


def test_full_default_downgrades_full_or_legacy_snapshot_to_normal():
    """全集或旧快照在全集默认规则下回退普通订阅。"""
    for snap in (
        {
            "tmdbid": 100,
            "season": 1,
            "subscribe_config": {"best_version": 1, "best_version_full": 1},
        },
        {"tmdbid": 100, "season": 1},
    ):
        rebuilder, chain, _, _ = _rebuilder(
            default_config={"best_version": 1, "best_version_full": 1},
        )
        assert rebuilder.rebuild(
            snap,
            {"name": "测试", "start_episode": 13, "total_episode": 15, "lack_episode": 3},
        ) is True
        assert chain.add.call_args.kwargs["best_version"] == 0
        assert chain.add.call_args.kwargs["best_version_full"] == 0


def test_default_tv_mode_reads_saved_system_config():
    """模式解析读取主程序保存的默认电视剧订阅规则。"""
    rebuilder, _, _, config_getter = _rebuilder(
        default_config={"best_version": 1, "best_version_full": 0},
    )

    assert rebuilder._get_default_tv_mode() == (True, False)
    config_getter.assert_called_once_with(SystemConfigKey.DefaultTvSubscribeConfig)


def test_rebuild_rejects_wrong_identity_returned_by_exist_ok():
    """exist_ok 返回其他媒体或剧集组的记录时不得误报成功。"""
    rebuilder, _, oper, _ = _rebuilder(
        rebuilt=_sub(episode_group="eg-old"),
    )
    snap = {"tmdbid": 100, "season": 1, "episode_group_id": "eg-new"}
    config = {"name": "测试", "start_episode": 13, "total_episode": 15, "lack_episode": 3}

    assert rebuilder.rebuild(snap, config) is False

    oper.get.return_value = _sub(tmdbid=101, episode_group="eg-new")
    assert rebuilder.rebuild(snap, config) is False


def test_rebuild_rejects_result_without_requested_episode_range():
    """回读订阅未覆盖完整新增集区间时保留快照重试。"""
    rebuilder, _, oper, _ = _rebuilder(rebuilt=_sub(total_episode=14))
    snap = {"tmdbid": 100, "season": 1}
    config = {"name": "测试", "start_episode": 13, "total_episode": 15, "lack_episode": 3}

    assert rebuilder.rebuild(snap, config) is False

    oper.get.return_value = _sub(start_episode=14)
    assert rebuilder.rebuild(snap, config) is False


def test_rebuild_rejects_full_or_wrong_resolved_mode():
    """回读订阅必须匹配解析模式，且绝不能继续保持全集洗版。"""
    rebuilder, _, oper, _ = _rebuilder(
        default_config={"best_version": 1, "best_version_full": 0},
        rebuilt=_sub(best_version=1, best_version_full=1),
    )
    snap = {"tmdbid": 100, "season": 1}
    config = {"name": "测试", "start_episode": 13, "total_episode": 15, "lack_episode": 3}

    assert rebuilder.rebuild(snap, config) is False

    oper.get.return_value = _sub(best_version=0, best_version_full=0)
    assert rebuilder.rebuild(snap, config) is False


def test_validate_checks_existing_subscription_against_added_episode_range():
    """verifier 复用组件规则判断既有订阅是否已接管新增集。"""
    rebuilder, _, _, _ = _rebuilder(
        default_config={"best_version": 1, "best_version_full": 0},
    )
    snap = {"tmdbid": 100, "season": 1, "total_at_completion": 12}

    assert rebuilder.validate(_sub(best_version=1), snap, current_total=15) is True
    assert rebuilder.validate(None, snap, current_total=15) is False


def test_rebuild_fails_closed_without_dependencies_or_when_chain_raises():
    """重建能力不可用或订阅链异常时返回失败，交由 verifier 保留快照。"""
    rebuilder = CompletionSubscribeRebuilder(
        subscribe_chain=None,
        subscribe_oper=None,
        default_config_getter=MagicMock(return_value={}),
        plugin_name="订阅助手（增强版）",
    )
    assert rebuilder.rebuild({}, {}) is False

    rebuilder, chain, _, _ = _rebuilder()
    chain.add.side_effect = RuntimeError("subscribe chain failed")
    assert rebuilder.rebuild(
        {"tmdbid": 100, "season": 1},
        {"name": "测试", "start_episode": 13, "total_episode": 15},
    ) is False


def test_default_tv_mode_treats_non_mapping_config_as_normal():
    """主程序未保存结构化默认规则时按普通订阅处理。"""
    rebuilder, _, _, _ = _rebuilder(default_config=[])

    assert rebuilder._get_default_tv_mode() == (False, False)
