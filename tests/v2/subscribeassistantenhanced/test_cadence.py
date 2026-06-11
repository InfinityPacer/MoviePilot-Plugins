"""engine/cadence.py G 播出节奏推算单测。"""
from datetime import date, timedelta

from subscribeassistantenhanced.engine.cadence import check_cadence_expired


def _ep(num, air_date):
    from types import SimpleNamespace
    return SimpleNamespace(episode_number=num, air_date=air_date, episode_type="standard")


class TestCheckCadenceExpired:

    def test_fewer_than_3_episodes_returns_false(self):
        """不足 3 集有 air_date → 不参与。"""
        eps = [_ep(1, "2026-01-01"), _ep(2, "2026-01-08")]
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=date(2026, 12, 1)) is False

    def test_weekly_within_window(self):
        """周播剧（间隔 7 天），窗口内 → False。"""
        base = date(2026, 1, 1)
        eps = [_ep(i, (base + timedelta(weeks=i-1)).isoformat()) for i in range(1, 13)]
        # 最后集 = base + 11 weeks = 2026-03-18
        # 窗口 = 3/18 + 7*2.5 = 3/18 + 17.5 = ~4/5
        as_of = date(2026, 3, 25)  # 在窗口内
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=as_of) is False

    def test_weekly_past_window(self):
        """周播剧窗口过期 → True。"""
        base = date(2026, 1, 1)
        eps = [_ep(i, (base + timedelta(weeks=i-1)).isoformat()) for i in range(1, 13)]
        as_of = date(2026, 5, 1)  # 远超窗口
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=as_of) is True

    def test_daily_min_window_7_days(self):
        """日播剧（间隔 1 天），窗口下限 7 天。"""
        base = date(2026, 1, 1)
        eps = [_ep(i, (base + timedelta(days=i-1)).isoformat()) for i in range(1, 31)]
        # 最后集 = 1/30，间隔 1 天 * 2.5 = 2.5 天 → 下限 7 天 → 窗口 = 1/30 + 7 = 2/6
        as_of = date(2026, 2, 3)  # 在 7 天下限内
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=as_of) is False

    def test_daily_past_min_window(self):
        """日播剧超过 7 天下限 → True。"""
        base = date(2026, 1, 1)
        eps = [_ep(i, (base + timedelta(days=i-1)).isoformat()) for i in range(1, 31)]
        as_of = date(2026, 2, 10)  # 超过下限
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=as_of) is True

    def test_future_episodes_excluded(self):
        """未来集不参与间隔计算。"""
        eps = [_ep(1, "2026-01-01"), _ep(2, "2026-01-08"),
               _ep(3, "2026-01-15"), _ep(4, "2027-01-01")]
        as_of = date(2026, 1, 20)  # 最后已播=1/15，窗口=1/15+7*2.5=~2/2
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=as_of) is False

    def test_no_air_date_episodes_excluded(self):
        """无 air_date 的集不参与。"""
        eps = [_ep(1, "2026-01-01"), _ep(2, "2026-01-08"),
               _ep(3, "2026-01-15"), _ep(4, None)]
        as_of = date(2026, 3, 1)
        assert check_cadence_expired(eps, multiplier=2.5, min_window_days=7,
                                      min_episodes=3, as_of=as_of) is True
