"""新增奇偶配置键的默认值与类型解析测试。"""
from subscribeassistantenhanced.shared.config import PluginConfig


def test_new_parity_config_defaults():
    cfg = PluginConfig({})
    # 全局
    assert cfg.enabled is False
    assert cfg.notify is True
    assert cfg.onlyonce is False
    assert cfg.reset_task is False
    assert cfg.download_check_interval_minutes == 10
    assert cfg.meta_check_interval_hours == 3
    # 待定
    assert cfg.pending_download_enabled is True
    assert cfg.auto_tv_pending_days == 0
    assert cfg.auto_tv_pending_episodes == 1
    assert "pending_default_total_episodes" not in cfg.declared_keys()
    # 暂停
    assert cfg.movie_air_pause_days == 7
    assert cfg.tv_air_pause_days == 14
    assert cfg.airing_pause_days == 30
    assert cfg.movie_no_download_days == 365
    assert cfg.tv_no_download_days == 180
    assert cfg.no_download_actions == []
    assert "download_pause_max_days" not in cfg.declared_keys()
    assert "download_pause_expire_action" not in cfg.declared_keys()
    assert cfg.pause_enhanced_enabled is False
    # 订阅清理与删种门禁
    assert cfg.manual_delete_listen is True
    assert cfg.tracker_response_listen is True
    assert cfg.auto_search_when_delete is True
    assert cfg.skip_deletion is True
    assert cfg.subscription_cleanup_history_type == "no"
    assert cfg.subscription_cleanup_history_scenes == []
    # 洗版
    assert cfg.best_version_type == "no"
    assert "best_version_clear_history_type" not in cfg.declared_keys()
    assert "best_version_remaining_days" not in cfg.declared_keys()
    assert cfg.best_version_movie_remaining_days == 0
    assert cfg.best_version_tv_remaining_days == 0
    assert cfg.best_version_episode_to_full is False
    assert cfg.best_version_backfill_enabled is False
    assert cfg.backfill_best_version_now is False
    # 完结信号
    assert cfg.completion_guard_mode == "balanced"
    assert cfg.verify_enabled is False


def test_no_download_actions_parses_list_or_csv():
    assert PluginConfig({"no_download_actions": ["pause_tv", "complete_movie"]}).no_download_actions == ["pause_tv", "complete_movie"]
    assert PluginConfig({"no_download_actions": "pause_tv,complete_movie"}).no_download_actions == ["pause_tv", "complete_movie"]
