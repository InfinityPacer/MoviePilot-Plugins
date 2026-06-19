"""engine/proximity.py 完成阶段接近度单测。"""
from datetime import date
from types import SimpleNamespace

from subscribeassistantenhanced.engine.proximity import assess_completion_proximity


def _ep(num, air_date="2026-01-01"):
    return SimpleNamespace(episode_number=num, air_date=air_date, episode_type="standard")


def test_mid_airing_total_shrink_is_not_near_completion():
    """南部档案 36→33 播出中段校准不属于接近完结。"""
    episodes = [_ep(i, air_date="2026-06-01") for i in range(1, 18)]
    episodes.extend(_ep(i, air_date="2026-06-23") for i in range(18, 34))

    result = assess_completion_proximity(
        episodes=episodes,
        total=33,
        missing_episodes=list(range(18, 34)),
        as_of=date(2026, 6, 17),
        completion_check=False,
    )

    assert result.near_completion is False
    assert result.aired_ratio < 0.8


def test_unknown_missing_count_does_not_imply_near_completion():
    """剩余目标未知时，不能按 0 集剩余触发接近完结。"""
    episodes = [_ep(i, air_date="2026-06-01") for i in range(1, 18)]
    episodes.extend(_ep(i, air_date="2026-06-23") for i in range(18, 34))

    result = assess_completion_proximity(
        episodes=episodes,
        total=33,
        missing_episodes=None,
        as_of=date(2026, 6, 17),
        completion_check=False,
    )

    assert result.near_completion is False
    assert result.remaining_count is None


def test_partial_air_dates_do_not_make_mid_airing_scope_near_completion():
    """后续目标集缺少 air_date 时，不能把最后一个有日期的中段集当成末集。"""
    episodes = [_ep(i, air_date="2026-06-01") for i in range(1, 18)]
    episodes.extend(_ep(i, air_date=None) for i in range(18, 34))

    result = assess_completion_proximity(
        episodes=episodes,
        total=33,
        missing_episodes=None,
        as_of=date(2026, 6, 2),
        completion_check=False,
    )

    assert result.near_completion is False
    assert "last_air_date" not in result.reasons


def test_finale_day_is_near_completion():
    """末集播出日属于接近完结。"""
    episodes = [_ep(i, air_date="2026-06-01") for i in range(1, 33)]
    episodes.append(_ep(33, air_date="2026-06-17"))

    result = assess_completion_proximity(
        episodes=episodes,
        total=33,
        missing_episodes=[],
        as_of=date(2026, 6, 17),
        completion_check=False,
    )

    assert result.near_completion is True
    assert "last_air_date" in result.reasons


def test_completion_check_context_is_near_completion():
    """主程序已进入完成检查时，按完成前风险区处理。"""
    result = assess_completion_proximity(
        episodes=[_ep(1), _ep(2)],
        total=2,
        missing_episodes=[],
        as_of=date(2026, 6, 17),
        completion_check=True,
    )

    assert result.near_completion is True
    assert "completion_check" in result.reasons
