"""订阅助手（增强版）——完整订阅生命周期管理入口。

插件入口负责配置解析、事件注册、定时任务和各业务域模块组装；具体业务规则由独立领域模块承载。
ResourceSelection 链式事件在这里接入候选准入、洗版串行和删除指纹过滤，保持入口只做编排。
"""
import datetime
import json
import random
import re
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple, Optional

from apscheduler.triggers.cron import CronTrigger

from app.plugins import _PluginBase
from app.log import logger
from app.core.event import eventmanager
from app.core.metainfo import MetaInfo
from app.schemas.types import EventType, ChainEventType, MediaType
from app.chain.storage import StorageChain
from app.chain.subscribe import SubscribeChain
from app.chain.tmdb import TmdbChain
from app.chain.torrents import TorrentsChain
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.subscribe_oper import SubscribeOper
from app.db.transferhistory_oper import TransferHistoryOper
from app.helper.downloader import DownloaderHelper

from .engine.types import CompletionSignal, SeasonScope
from .engine.site import SiteEpisodesRefreshHandler, SiteEvidenceScanner, SiteEvidenceStore
from .engine.volatility import VolatilityTracker
from .engine.pipeline import CompletionEvidencePipeline
from .guard import CompletionGuard
from .lifecycle import SubscribeLifecycleCoordinator
from .pending.judge import PendingJudge
from .pending.refresh import PendingRefresh
from .pending.state import PendingStateCoordinator
from .pause.airing import AiringPauseChecker
from .pause.manager import PauseManager
from .pause.nodownload import NoDownloadPolicy
from .pause.probe import PausedProbeCoordinator
from .best_version.priority import PriorityManager
from .best_version.converter import BestVersionConverter
from .best_version.orchestrator import BestVersionOrchestrator
from .cleanup import SubscriptionCleanup
from .download.monitor import DownloadMonitor
from .download.cleanup import TorrentCleanup
from .recognition import RecognitionGuard, RecognitionRuntime, RecognitionSettings
from .recognition.audit import redact_sensitive_text
from .shared.deletes import DeletesStore
from .shared.subscribe import (
    build_subscribe_meta,
    format_subscribe_label,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)
from .postcheck.verifier import CompletionVerifier, _format_snapshot_label
from .postcheck.timeout import PendingTimeoutManager
from .events import EventProxy
from .shared.media import parse_date
from .shared.task import TaskDataManager
from .shared.config import (
    DEFAULT_DELETE_EXCLUDE_TAGS,
    DEFAULT_RECOGNITION_GUARD_CUSTOM_CONFIG,
    DEFAULT_TRACKER_RESPONSE,
    PluginConfig,
)
from .shared.log import detail, truncate_log_value
from .shared.subscribe import format_subscribe


class SubscribeAssistantEnhanced(_PluginBase):
    """订阅助手增强版——插件入口。

    生命周期：init_plugin → 事件注册 → 定时任务 → stop_service。
    配置界面由 Vue 联邦 Config 渲染，get_form 提供初始模型与默认值；
    运行概况由日志和只读 summary API 提供。
    继承 _PluginBase 以获得真实数据层（get_data/save_data）、事件管理器与消息能力。
    """

    # 插件名称
    plugin_name = "订阅助手（增强版）"
    # 插件描述
    plugin_desc = "多场景管理订阅，实现订阅全生命周期管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/subscribeassistantenhanced.png"
    # 插件版本
    plugin_version = "0.6.6"
    _site_cache_candidate_helper_warned = False
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscribeassistantenhanced_"
    # 加载顺序
    plugin_order = 5
    # 可使用的用户级别
    auth_level = 1

    @property
    def name(self) -> str:
        """错误处理读取的插件展示名。"""
        return self.plugin_name

    def __init__(self):
        """初始化插件运行期依赖与一次性任务状态。"""
        super().__init__()
        self._config: Optional[PluginConfig] = None
        self._task_manager: Optional[TaskDataManager] = None
        self._event_proxy: Optional[EventProxy] = None
        self._paused_probe_coordinator: Optional[PausedProbeCoordinator] = None
        self._modules: dict = {}
        self._onlyonce = False
        # DB oper / chain 在 init_plugin 实例化后注入各业务域模块。
        self._subscribe_oper: Optional[SubscribeOper] = None
        self._subscribe_chain: Optional[SubscribeChain] = None
        self._tmdb_chain: Optional[TmdbChain] = None
        self._storage_chain: Optional[StorageChain] = None
        self._transferhistory_oper: Optional[TransferHistoryOper] = None
        self._downloadhistory_oper: Optional[DownloadHistoryOper] = None
        self._downloader_helper: Optional[DownloaderHelper] = None

    def init_plugin(self, config: dict = None):
        """解析配置 → 注入 DB/chain 依赖 → 初始化各业务域模块。"""
        self.stop_service()

        raw_config, should_persist = self._normalize_persisted_config(config or {})
        self._config = PluginConfig(raw_config)

        # 依赖注入：构造即可用且不触发外部网络，供洗版、下载、补搜等业务域写库与查询。
        self._subscribe_oper = SubscribeOper()
        self._subscribe_chain = SubscribeChain()
        self._tmdb_chain = TmdbChain()
        self._storage_chain = StorageChain()
        self._transferhistory_oper = TransferHistoryOper()
        self._downloadhistory_oper = DownloadHistoryOper()
        self._downloader_helper = DownloaderHelper()

        # 任务数据统一走 _PluginBase 的 get_data/save_data 持久化接口。
        self._task_manager = TaskDataManager(
            get_data_fn=self.get_data,
            save_data_fn=self.save_data,
        )

        self._init_modules()

        self._onlyonce = self._config.onlyonce
        if self._config.reset_task:
            self._reset_task_data()
        if self._config.backfill_best_version_now:
            self._run_backfill_now()
        if self._config.onlyonce or self._config.reset_task or self._config.backfill_best_version_now:
            raw_config["onlyonce"] = False
            raw_config["reset_task"] = False
            raw_config["backfill_best_version_now"] = False
            should_persist = True
        if should_persist:
            self.update_config(raw_config)
            self._config = PluginConfig(raw_config)

        # 启动摘要：一眼看清各业务域开关，排查"某能力为何不生效"先看这条
        cfg = self._config
        recognition_mode = cfg.recognition_guard_mode
        recognition_notify = cfg.recognition_guard_notify
        recognition_interval = cfg.recognition_guard_notify_interval
        recognition_recheck = cfg.recognition_guard_tmdb_recheck_mode
        recognition_cache_size = cfg.recognition_guard_cache_maxsize
        recognition_warnings = ",".join(sorted(cfg.recognition_guard_config_warnings)) or "none"
        logger.info(
            "初始化完成："
            f"总开关={cfg.enabled} 完成守卫模式={cfg.completion_guard_mode} "
            f"待定增强={cfg.pending_enhanced_enabled} 暂停优化={cfg.pause_enhanced_enabled} "
            f"洗版类型={cfg.best_version_type} 下载管理={cfg.download_monitor_enabled} "
            f"完成验证={cfg.verify_enabled} 识别增强={recognition_mode} "
            f"站点集数探测={cfg.site_total_probe_enabled} "
            f"站点完结信号={cfg.site_completion_evidence_enabled} "
            f"识别增强通知={recognition_notify} 二次识别={recognition_recheck} "
            f"识别增强通知限频={recognition_interval} 识别增强缓存={recognition_cache_size} "
            f"识别增强告警={recognition_warnings} 通知={cfg.notify}"
        )

    @staticmethod
    def _normalize_persisted_config(config: dict) -> Tuple[dict, bool]:
        """规范化需要持久安全默认值的配置，避免旧空值覆盖表单默认 model。"""
        raw = dict(config or {})
        changed = False
        retired_config_keys = {
            "recognition_guard_enabled",
            "recognition_guard_active",
            "recognition_guard_keyword_config",
            "recognition_guard_target_mode",
            "recognition_guard_missing_year_policy",
            "open_tracker_dialog",
            "progress_diagnostic_mode",
            "progress_diagnostic_stalled_rounds",
            "progress_diagnostic_cooldown_hours",
        }
        for key in retired_config_keys:
            if key in raw:
                raw.pop(key, None)
                changed = True
        default_text_fields = {
            "delete_exclude_tags": DEFAULT_DELETE_EXCLUDE_TAGS,
            "default_tracker_response": DEFAULT_TRACKER_RESPONSE,
        }
        for key, default in default_text_fields.items():
            if key in raw and not str(raw.get(key) or "").strip():
                raw[key] = default
                changed = True
        recognition_defaults = {
            "recognition_guard_mode": "off",
            "recognition_guard_notify": "off",
            "recognition_guard_notify_interval": 3600,
            "recognition_guard_tmdb_recheck_mode": "balanced_strict",
            "recognition_guard_cache_maxsize": 100000,
            "recognition_guard_custom_config": DEFAULT_RECOGNITION_GUARD_CUSTOM_CONFIG,
        }
        for key, default in recognition_defaults.items():
            if key not in raw:
                raw[key] = default
                changed = True
        return raw, changed

    def _init_modules(self):
        """初始化各域模块并注入运行期依赖。"""
        cfg = self._config
        tm = self._task_manager

        volatility = VolatilityTracker(tm, window_days=cfg.volatility_window_days)
        timeout_manager = PendingTimeoutManager(
            tm.read, tm.update,
            timeout_days=cfg.timeout_release_days,
            cadence_acceleration=cfg.timeout_cadence_acceleration,
            subscribe_get_fn=self._subscribe_oper.get,
        )
        verifier = CompletionVerifier(
            tm.read, tm.update,
            tmdb_episodes_fn=self._tmdb_episodes,
            subscribe_oper=self._subscribe_oper,
            retention_days=cfg.verify_retention_days,
            notify_fn=self._notify_subscribe,
            rebuild_subscribe_fn=self._rebuild_subscribe_from_snapshot,
        )
        priority_manager = PriorityManager(
            tm.read,
            tm.update,
            subscribe_oper=self._subscribe_oper,
            plugin_name=self.plugin_name,
        )
        converter = BestVersionConverter(
            subscribe_oper=self._subscribe_oper,
            clear_tasks_fn=self._task_manager.clear_tasks,
            send_event_fn=eventmanager.send_event,
            notify_fn=self._notify_subscribe,
            restore_fn=self._restore_subscribe_from_snapshot,
            snapshot_fn=verifier.snapshot,
            format_desc_fn=lambda subscribe, mediainfo: self._format_subscribe_desc(subscribe, mediainfo),
            plugin_name=self.plugin_name,
        )
        pending_refresh = PendingRefresh()
        pending_state = PendingStateCoordinator(
            tm.read,
            tm.update,
            subscribe_oper=self._subscribe_oper,
        )
        # 用户名自动暂停名单：逗号分隔字符串解析为列表，剔除空白与空项；空名单即不启用该能力
        auto_pause_users = [u.strip() for u in (cfg.auto_pause_users or "").split(",") if u.strip()]
        # 注入 subscribe_oper：pause()/resume() 据此真实写订阅 DB state（S/R），否则只写插件任务数据
        pause_manager = PauseManager(
            tm.read,
            tm.update,
            subscribe_oper=self._subscribe_oper,
            auto_pause_users=auto_pause_users,
            notify_fn=self._send_subscribe_status_notification,
            pending_state=pending_state,
            pause_enhanced_enabled=cfg.pause_enhanced_enabled,
        )
        no_download_policy = NoDownloadPolicy(
            movie_days=cfg.movie_no_download_days,
            tv_days=cfg.tv_no_download_days,
            actions=cfg.no_download_actions,
        )
        tracker_keywords = [k.strip() for k in (cfg.default_tracker_response or "").splitlines() if k.strip()]
        if not cfg.tracker_response_listen:
            tracker_keywords = []
        exclude_tags = [t.strip() for t in (cfg.delete_exclude_tags or "").replace("&", ",").split(",") if t.strip()]
        download_monitor = DownloadMonitor(
            tm.read, tm.update,
            timeout_minutes=cfg.download_timeout_minutes,
            progress_threshold=cfg.download_progress_threshold,
            retry_limit=cfg.download_retry_limit,
            tracker_keywords=tracker_keywords,
            exclude_tags=exclude_tags,
            subscribe_oper=self._subscribe_oper,
            state_coordinator=None,
            fetch_fn=self._fetch_downloader_torrent,
            present_fn=self._downloader_torrent_present,
            manual_delete_enabled=cfg.download_monitor_enabled and cfg.manual_delete_listen,
            pending_download_enabled=cfg.pending_download_enabled,
        )

        deletes_store = DeletesStore(tm.read, tm.update)
        torrent_cleanup = TorrentCleanup(
            priority_manager=priority_manager,
            clear_download_pending_fn=download_monitor.clear_download_pending,
            task_data_update=tm.update,
            task_data_read=tm.read,
            deletes_store=deletes_store,
            delete_torrent_fn=self._delete_downloader_torrent,
            search_fn=self._search_subscribe if cfg.auto_search_when_delete else None,
            notify_fn=self._notify_subscribe,
            get_subscribe_image_fn=self._get_subscribe_image,
            subscribe_oper=self._subscribe_oper,
        )

        site_store = SiteEvidenceStore(tm)
        if not cfg.site_total_probe_enabled:
            site_store.clear_all_leases()
        completion_pipeline = CompletionEvidencePipeline(
            tmdb_episodes_fn=self._tmdb_episodes,
            volatility_tracker=volatility,
            config=cfg,
            site_evidence_provider=site_store.read_snapshot,
        )
        site_evidence = SiteEvidenceScanner(
            config=cfg,
            store=site_store,
            candidate_provider=self._site_cache_candidates,
        )
        site_refresh = SiteEpisodesRefreshHandler(
            config=cfg,
            store=site_store,
            subscribe_oper=self._subscribe_oper,
            resolve_missing_fn=self._resolve_subscribe_missing,
            mediainfo_from_dict=self._mediainfo_from_dict,
        )

        airing_checker = AiringPauseChecker(
            pause_days=cfg.airing_pause_days,
            evidence_pipeline=completion_pipeline,
            movie_air_days=cfg.movie_air_pause_days,
            tv_air_days=cfg.tv_air_pause_days,
        )

        pending_judge = PendingJudge(
            config=cfg,
            evidence_pipeline=completion_pipeline,
            subscribe_oper=self._subscribe_oper,
            timeout_manager=timeout_manager,
            task_data_read=tm.read,
            task_data_update=tm.update,
            resolve_missing_fn=self._resolve_subscribe_missing,
            notify_fn=self._send_subscribe_status_notification,
            state_coordinator=pending_state,
        )

        lifecycle = SubscribeLifecycleCoordinator(
            config=cfg,
            subscribe_oper=self._subscribe_oper,
            pause_manager=pause_manager,
            pending_judge=pending_judge,
            pending_state=pending_state,
            airing_checker=airing_checker if cfg.pause_enhanced_enabled else None,
            tmdb_episodes_fn=lambda *args, **kwargs: self._tmdb_episodes(*args, **kwargs),
            recognize_mediainfo_fn=lambda subscribe: self._recognize_mediainfo(subscribe),
            is_tv_fn=lambda mediainfo: self._is_tv_media(mediainfo),
            schedule_initial_pending_search_fn=lambda subscribe: self._schedule_initial_pending_search(subscribe),
            has_active_downloads_fn=lambda sid: bool(
                download_monitor and download_monitor.has_active_downloads(sid)
            ),
            clear_orphan_completion_observation_fn=self._clear_orphan_completion_observation,
            clear_tasks_for_pause_fn=lambda subscribe_id: self._task_manager.clear_tasks_for_pause(
                subscribe_id,
                preserve_subscribe_keys=[
                    "pause_reason",
                    "pause_since",
                    "pause_detail",
                    "paused_probe_resume_guard_reason",
                    "paused_probe_resume_guard_until",
                ],
            ),
        )
        download_monitor.set_state_coordinator(lifecycle.download_pending_adapter())

        guard = CompletionGuard(
            evidence_pipeline=completion_pipeline,
            has_active_downloads_fn=lambda sub: download_monitor.has_active_downloads(
                sub.id),
            mark_pending_fn=lambda subscribe, source="guard_veto", reason="": lifecycle.enter_guard_pending(
                subscribe,
                reason=reason,
            ),
            timeout_manager=timeout_manager,
            mode=cfg.completion_guard_mode,
            pending_download_enabled=cfg.pending_download_enabled,
            resolve_missing_fn=self._resolve_subscribe_missing,
        )
        recognition_guard = RecognitionGuard(
            settings=RecognitionSettings(
                mode=cfg.recognition_guard_mode,
                notify_mode=cfg.recognition_guard_notify,
                notify_interval=cfg.recognition_guard_notify_interval,
                tmdb_recheck_mode=cfg.recognition_guard_tmdb_recheck_mode,
                cache_maxsize=cfg.recognition_guard_cache_maxsize,
                custom_config=cfg.recognition_guard_custom_config,
            ),
            runtime=RecognitionRuntime(
                target_mediainfo_resolver=self._recognize_mediainfo,
                tmdb_episodes_fn=self._tmdb_episodes,
                secondary_recognizer=self._recognize_by_meta_for_recognition,
                logger_fn=detail,
            ),
        )

        orchestrator = BestVersionOrchestrator(
            priority_manager=priority_manager,
            subscribe_oper=self._subscribe_oper,
            send_subscribe_added_fn=self._send_subscribe_added,
            notify_fn=self._notify_subscribe,
            related_downloads_fn=self._related_download_histories,
            best_version_type=cfg.best_version_type,
            plugin_name=self.plugin_name,
        )
        subscription_cleanup = SubscriptionCleanup(
            task_data_read=tm.read,
            task_data_update=tm.update,
            get_histories_fn=self._get_transfer_histories,
            delete_media_file_fn=self._delete_media_file,
            delete_history_fn=self._transferhistory_oper.delete,
            send_download_file_deleted_fn=self._send_download_file_deleted,
            notify_fn=self._notify_subscribe,
            get_subscribe_image_fn=self._get_subscribe_image,
            torrent_exists_fn=self._torrent_exists,
            cleanup_history_type=cfg.subscription_cleanup_history_type,
            cleanup_history_scenes=cfg.subscription_cleanup_history_scenes,
        )
        paused_probe = PausedProbeCoordinator(
            cfg,
            tm.read,
            tm.update,
            subscribe_oper=self._subscribe_oper,
            subscribe_chain=self._subscribe_chain,
            pause_manager=pause_manager,
            download_monitor=download_monitor,
        )
        self._paused_probe_coordinator = paused_probe

        self._event_proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=self._subscribe_oper,
            post_message=self.post_message,
            notify_fn=self._notify_subscribe,
            plugin_name=self.plugin_name,
            deletes_store=deletes_store if cfg.download_monitor_enabled else None,
            skip_deletion=cfg.skip_deletion,
            backfill_enabled=cfg.best_version_backfill_enabled,
            pending_download_enabled=cfg.pending_download_enabled,
            download_monitor_enabled=cfg.download_monitor_enabled,
            guard=guard if cfg.completion_guard_mode != "off" else None,
            recognition_guard=recognition_guard if cfg.recognition_guard_mode != "off" else None,
            volatility=volatility if cfg.volatility_enabled else None,
            site_refresh=site_refresh,
            pending_refresh=pending_refresh if cfg.pending_enhanced_enabled else None,
            pause_manager=pause_manager if cfg.pause_enhanced_enabled else None,
            airing_checker=airing_checker if cfg.pause_enhanced_enabled else None,
            pending_judge=pending_judge if cfg.pending_enhanced_enabled else None,
            pending_state=pending_state,
            lifecycle=lifecycle,
            tmdb_episodes_fn=self._tmdb_episodes,
            mediainfo_from_dict=self._mediainfo_from_dict,
            is_tv_fn=self._is_tv_media,
            detect_existing_episodes_fn=self._detect_existing_episodes,
            detect_backfill_episodes_fn=self._detect_backfill_episodes,
            detect_missing_episodes_fn=self._detect_missing_episodes,
            schedule_initial_pending_search_fn=self._schedule_initial_pending_search,
            resolve_missing_fn=self._resolve_subscribe_missing,
            recognize_mediainfo_fn=self._recognize_mediainfo,
            priority_manager=priority_manager,
            download_monitor=download_monitor,
            verifier=verifier,
            orchestrator=orchestrator,
            subscription_cleanup=subscription_cleanup,
            converter=converter,
            best_version_episode_to_full=cfg.best_version_episode_to_full,
        )

        self._modules = {
            "volatility": volatility,
            "timeout_manager": timeout_manager,
            "verifier": verifier,
            "priority_manager": priority_manager,
            "converter": converter,
            "pending_judge": pending_judge,
            "pending_state": pending_state,
            "lifecycle": lifecycle,
            "pending_refresh": pending_refresh,
            "pause_manager": pause_manager,
            # airing_checker 同时放入 _modules，供 run_meta_check 周期巡检按 enabled 门控读取
            "airing_checker": airing_checker if cfg.pause_enhanced_enabled else None,
            "no_download_policy": no_download_policy,
            "download_monitor": download_monitor,
            "paused_probe": paused_probe,
            "torrent_cleanup": torrent_cleanup,
            "deletes_store": deletes_store,
            "guard": guard,
            "recognition_guard": recognition_guard,
            "orchestrator": orchestrator,
            "subscription_cleanup": subscription_cleanup,
            "completion_pipeline": completion_pipeline,
            "site_evidence_store": site_store,
            "site_evidence": site_evidence,
            "site_refresh": site_refresh,
        }

    def stop_service(self):
        """清理定时任务和事件监听。"""
        if self._paused_probe_coordinator:
            self._paused_probe_coordinator.stop()
            self._paused_probe_coordinator = None
        self._event_proxy = None
        self._modules = {}

    @staticmethod
    def _format_service_registration(service: Dict[str, Any], schedules: Dict[str, str]) -> str:
        """生成定时任务注册摘要；周期信息由注册入口按配置显式传入，避免从触发器反推。"""
        schedule = schedules.get(service["id"])
        if schedule:
            return f"{service['name']}={schedule}"
        return service["name"]

    def get_service(self) -> List[Dict[str, Any]]:
        """按域开关注册定时任务，并按元数据周期复查待定订阅。

        插件总开关关闭时不注册任何任务。
        每个 job 的 func 指向插件类薄方法，委托对应域模块执行；模块周期方法未就绪时安全跳过。
        周期 job 多用 interval 触发器；洗版订阅检查用 cron 触发器（CronTrigger）；一次性全量巡检用 date 触发器延迟执行。
        """
        if not self._config:
            return []
        if not self._config.enabled:
            return []
        cfg = self._config
        name = self.__class__.__name__
        services: List[Dict[str, Any]] = []
        service_schedules: Dict[str, str] = {}
        if self._onlyonce:
            service_id = f"{name}_onlyonce"
            services.append({
                "id": service_id,
                "name": "立即运行一次",
                "trigger": "date",
                "run_date": datetime.datetime.now() + datetime.timedelta(seconds=3),
                "func": self.run_all_checks,
                "kwargs": {},
            })
            service_schedules[service_id] = "约3s后"
        service_id = f"{name}_meta_check"
        services.append({
            "id": service_id,
            "name": "元数据检查",
            "trigger": "interval",
            "func": self.run_meta_check,
            "kwargs": {"hours": cfg.meta_check_interval_hours},
        })
        service_schedules[service_id] = f"{cfg.meta_check_interval_hours}h"
        if cfg.pending_download_enabled or cfg.download_monitor_enabled:
            service_id = f"{name}_download"
            services.append({
                "id": service_id,
                "name": "下载任务检查",
                "trigger": "interval",
                "func": self.run_download_timeout_check,
                "kwargs": {"minutes": cfg.download_check_interval_minutes},
            })
            service_schedules[service_id] = f"{cfg.download_check_interval_minutes}m"
        if cfg.best_version_type != "no" and cfg.best_version_cron:
            # 洗版按 cron 调度，区别于其余域的 interval 周期；cron 为空则不注册该任务
            service_id = f"{name}_best_version"
            services.append({
                "id": service_id,
                "name": "洗版订阅检查",
                "trigger": CronTrigger.from_crontab(cfg.best_version_cron),
                "func": self.run_best_version_check,
            })
            service_schedules[service_id] = f"cron({cfg.best_version_cron})"
        if cfg.verify_enabled:
            service_id = f"{name}_verify"
            services.append({
                "id": service_id,
                "name": "自动纠错",
                "trigger": "interval",
                "func": self.run_completion_verify,
                "kwargs": {"hours": cfg.verify_interval_hours},
            })
            service_schedules[service_id] = f"{cfg.verify_interval_hours}h"
        service_id = f"{name}_common_check"
        services.append({
            "id": service_id,
            "name": "通用巡检",
            "trigger": "interval",
            "func": self.run_common_check,
            "kwargs": {"minutes": cfg.auto_check_interval_minutes},
        })
        service_schedules[service_id] = f"{cfg.auto_check_interval_minutes}m"
        detail("注册定时任务：" + "、".join(
            self._format_service_registration(service, service_schedules) for service in services
        ))
        return services

    def run_all_checks(self):
        """一次性执行所有周期检查；各检查会按功能开关自行跳过。"""
        logger.info("立即运行一次：开始全量巡检")
        self.run_meta_check()
        self.run_download_timeout_check()
        self.run_best_version_check()
        if self._config.verify_enabled:
            self.run_completion_verify()
        self.run_common_check()

    def _reset_task_data(self):
        """先恢复增强版持有的订阅状态，再清空全部插件任务数据。"""
        if self._paused_probe_coordinator:
            self._paused_probe_coordinator.stop()
        lifecycle = self._modules.get("lifecycle")
        result = lifecycle.restore_owned_states_before_reset() if lifecycle else None
        if result and result.changed:
            summary = result.message or result.reason
            logger.info(f"重置任务：数据清空前已恢复订阅状态；{summary}")
            self._notify_subscribe("订阅助手数据重置前已恢复订阅状态", text=summary)
        else:
            logger.info("重置任务：数据清空前未发现需要恢复的订阅状态")
        for key in [
            "subscribes",
            "torrents",
            "blocks",
            "releases",
            "snapshots",
            "deletes",
            "volatility",
            "site_evidence",
            "subscription_cleanup_histories",
        ]:
            self.save_data(key, {})
        logger.info("重置任务：已清空全部插件任务数据（订阅、下载任务、完成前观察记录、放行令牌、完成快照、删除指纹、集数变化记录、站点证据、订阅清理记录）")

    def _run_backfill_now(self):
        """对现有分集洗版订阅执行一次下载事实回填，并推送扫描结果汇总。"""
        results = {"scanned": 0, "updated": 0, "skipped": 0, "filled_episodes": 0}
        priority = self._modules["priority_manager"]
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            if not subscribe or not subscribe.best_version:
                continue
            results["scanned"] += 1
            if not priority.can_backfill(subscribe):
                results["skipped"] += 1
                continue
            existing = self._detect_backfill_episodes(subscribe)
            filled_episodes = [
                episode for episode in existing
                if str(episode) not in (subscribe.episode_priority or {})
            ]
            scene = f"plugin_backfill<{self.plugin_name}>"
            if existing and priority.backfill_existing(subscribe, existing, scene=scene):
                results["updated"] += 1
                results["filled_episodes"] += len(filled_episodes)
                detail(f"洗版回填：{format_subscribe(subscribe)} 回填已下载集 {filled_episodes}")
            else:
                results["skipped"] += 1
        logger.info(
            f"洗版回填：完成，扫描 {results['scanned']} 个，写入 {results['updated']} 个，"
            f"跳过 {results['skipped']} 个，累计补写 {results['filled_episodes']} 集"
        )
        self._notify_subscribe(
            "洗版订阅下载事实回填",
            action=(
                f"扫描 {results['scanned']} 个订阅，成功回填 {results['updated']} 个，"
                f"跳过 {results['skipped']} 个，累计补写 {results['filled_episodes']} 集"
            ),
        )

    def run_download_timeout_check(self):
        """下载任务检查：读取下载器状态，处理超时无进度、Tracker 删除关键字和手动删种。"""
        monitor = self._modules.get("download_monitor")
        cleanup = self._modules.get("torrent_cleanup") if (
            self._config and self._config.download_monitor_enabled
        ) else None
        if monitor:
            detail("下载任务检查：开始")
            monitor.run_timeout_check(cleanup)

    def _ensure_best_version_anchor(self, sid, now) -> float:
        """读取洗版首次观察锚点；缺失时以当前时间写入订阅任务数据。"""
        subscribes = self._task_manager.read("subscribes") or {}
        anchor = (subscribes.get(str(sid)) or {}).get("best_version_anchor")
        if anchor:
            return anchor

        def set_anchor(data):
            """在保留订阅既有任务字段的前提下写入首次观察锚点。"""
            data = dict(data or {})
            record = dict(data.get(str(sid)) or {})
            record["best_version_anchor"] = now
            data[str(sid)] = record
            return data

        self._task_manager.update("subscribes", set_anchor)
        return now

    def _best_version_timeout_days(self, subscribe) -> int:
        """按媒体类型读取洗版时限。"""
        if resolve_subscribe_media_type(subscribe) == MediaType.MOVIE:
            return self._config.best_version_movie_remaining_days
        return self._config.best_version_tv_remaining_days

    def _best_version_overdue(self, subscribe, now=None) -> bool:
        """洗版是否超时限：从最近活动时间起算超过对应媒体类型洗版时限。

        活动时间取该订阅在 torrents 任务数据中的最新记录时间；
        无下载记录则按首次观察锚点（缺失则置当前时间）。
        remaining_days=0 表示不限，永不超时。
        """
        days = self._best_version_timeout_days(subscribe)
        if not days:
            return False
        now = now or time.time()
        sid = subscribe.id
        torrents = self._task_manager.read("torrents") or {}
        times = [
            torrent.get("time", 0)
            for torrent in torrents.values()
            if torrent.get("subscribe_id") == sid
        ]
        anchor = self._ensure_best_version_anchor(sid, now)
        last = max(times + [anchor]) if times else anchor
        return (now - last) > days * 86400

    def run_best_version_check(self):
        """洗版巡检：处理洗版超时终止，并兜底推进分集洗版转全集。"""
        if self._config and self._config.best_version_type == "no":
            return
        priority = self._modules.get("priority_manager")
        converter = self._modules.get("converter")
        if not priority or not self._subscribe_oper:
            return
        detail("洗版巡检：开始")
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            if not subscribe.best_version:
                continue
            mode_label = self._best_version_mode_label(subscribe)
            mediainfo = self._recognize_mediainfo(subscribe)
            if mediainfo:
                if is_full_best_version_subscribe(subscribe) and self._best_version_overdue(subscribe):
                    logger.info(f"洗版巡检：{format_subscribe(subscribe)} {mode_label}超过洗版时限，标记洗版完成并停止洗版")
                    priority.mark_complete(subscribe)
                    self._notify_subscribe(
                        f"{format_subscribe(subscribe)} {mode_label}超过时限"
                        f"（{self._best_version_timeout_days(subscribe)}天），已标记洗版优先级为完成",
                        image=mediainfo.get_message_image(),
                    )
                    continue
                if (
                    self._config.best_version_episode_to_full
                    and converter
                    and is_tv_episode_best_version_subscribe(subscribe)
                ):
                    satisfied, _no_exists = self._resolve_subscribe_missing(
                        subscribe,
                        mediainfo,
                        best_version_accept_downloaded=True,
                    )
                    if not satisfied:
                        continue
                    logger.info(f"洗版巡检：{format_subscribe(subscribe)} 分集洗版目标满足，转为全集洗版")
                    converter.convert_to_full(subscribe, mediainfo)
                    continue
            else:
                detail(
                    f"洗版巡检：{format_subscribe(subscribe)} {mode_label}媒体识别失败，本轮跳过；"
                    f"订阅ID：{subscribe.id}，TMDB：{subscribe.tmdbid or '未设置'}，"
                    f"媒体类型：{subscribe.type or '未设置'}，季号：{subscribe.season if subscribe.season is not None else '未设置'}；"
                    f"建议检查订阅名称、年份、TMDB ID、媒体类型和季号"
                )

    @staticmethod
    def _best_version_mode_label(subscribe) -> str:
        """按订阅实际洗版形态返回日志和通知标签。"""
        if is_full_best_version_subscribe(subscribe):
            return "洗版"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "分集洗版"
        return ""

    def run_meta_check(self):
        """元数据检查巡检：枚举订阅并委托生命周期协调器处理单订阅状态流转。"""
        if not self._subscribe_oper:
            return
        lifecycle = self._modules.get("lifecycle")
        detail("元数据巡检：开始")
        for subscribe in (self._subscribe_oper.list(state="N,R,P,S") or []):
            if lifecycle:
                lifecycle.handle_meta_check_subscription(subscribe)

    @staticmethod
    def _pending_release_sources(task: dict) -> list[str]:
        """返回需要通过待定判定器复核的业务待定来源。"""
        sources = task.get("pending_sources") if isinstance(task, dict) else None
        if isinstance(sources, dict) and sources:
            ordered_sources = [
                source for source in ("pending_judge", "guard_veto")
                if source in sources
            ]
            return ordered_sources or ["pending_judge"]
        source = task.get("source") if isinstance(task, dict) else None
        if source in ("pending_judge", "guard_veto"):
            return [source]
        return ["pending_judge"]

    def run_pending_release(self):
        """待定释放巡检：活跃来源走待定判定器，残留观察记录只做清理。

        PendingStateCoordinator 对 download_pending、pending_judge、guard_veto 做多来源仲裁；
        guard_veto 退出必须经完成证据流水线复核，孤儿观察记录不参与状态释放。
        """
        detail("待定释放巡检：开始")
        lifecycle = self._modules.get("lifecycle")
        if lifecycle and self._subscribe_oper:
            task_data = self.get_data("subscribes") or {}
            for subscribe in (self._subscribe_oper.list(state="P") or []):
                task = task_data.get(str(subscribe.id), {})
                for source in self._pending_release_sources(task):
                    lifecycle.release_pending_source(
                        subscribe,
                        source=source,
                        reason="待定释放巡检",
                    )

        timeout_manager = self._modules.get("timeout_manager")
        if not timeout_manager or not self._subscribe_oper:
            return
        for sid in list((self.get_data("blocks") or {}).keys()):
            subscribe = self._subscribe_oper.get(int(sid))
            if not subscribe:
                detail(f"待定释放：{format_subscribe_label(subscribe_id=sid)} 已不存在，清理残留完成前观察记录")
                timeout_manager.clear_observation(int(sid))
                timeout_manager.clear_release_token(int(sid))
                continue
            task_data = self.get_data("subscribes") or {}
            task = task_data.get(str(sid), {})
            has_guard_source = (
                task.get("source") == "guard_veto"
                or "guard_veto" in (task.get("pending_sources") or {})
            )
            if subscribe.state == "P" and has_guard_source:
                continue
            detail(f"待定释放：{format_subscribe(subscribe)} 无活跃完成前观察来源，清理残留记录")
            timeout_manager.clear_observation(int(sid))
            timeout_manager.clear_release_token(int(sid))

    def run_pending_state_reconcile(self):
        """修复增强版任务仍声明 P、但所有待定来源均已丢失的状态残留。"""
        lifecycle = self._modules.get("lifecycle")
        if not lifecycle or not self._subscribe_oper:
            return
        for subscribe in (self._subscribe_oper.list(state="P") or []):
            lifecycle.reconcile_pending(
                subscribe,
                reason="待定状态一致性检查",
            )

    def _clear_orphan_completion_observation(self, subscribe):
        """恢复无活跃 guard_veto 的 P 残留后，清理同订阅完成前观察状态。"""
        timeout_manager = self._modules.get("timeout_manager")
        if not timeout_manager or not subscribe:
            return
        timeout_manager.clear_observation(subscribe.id)
        timeout_manager.clear_release_token(subscribe.id)

    def run_common_check(self):
        """统一执行待定、无下载及各类本地过期数据清理。

        每个子任务独立捕获异常，避免单个检查失败阻断同轮其他检查。
        """
        tasks = [("待定释放", self.run_pending_release)]
        tasks.append(("待定状态一致性检查", self.run_pending_state_reconcile))
        tasks.append(("无下载处理", self.run_no_download_check))
        tasks.append(("暂停订阅低频补搜", self.run_paused_probe_check))
        tasks.append(("站点证据采样", self.run_site_evidence_scan))
        if self._config.download_monitor_enabled:
            tasks.append(("删除记录清理", self.run_deletes_cleanup))
        tasks.append(("完成快照清理", self.run_completion_snapshot_cleanup))
        tasks.append(("订阅清理事务清理", self.run_subscription_cleanup_expired))

        detail("通用巡检：开始")
        for task_name, task in tasks:
            try:
                task()
            except Exception as err:
                logger.error(f"通用巡检：{task_name}执行失败：{err}", exc_info=True)

    def run_paused_probe_check(self):
        """暂停订阅低频补搜巡检：登记外部暂停，并按配置安排单订阅搜索。"""
        coordinator = self._modules.get("paused_probe")
        if coordinator:
            coordinator.run()

    def run_site_evidence_scan(self):
        """站点证据采样：只读主程序 RSS/spider 缓存并固化短窗口资源证据。"""
        site_evidence = self._modules.get("site_evidence")
        if not site_evidence or not self._subscribe_oper:
            return
        detail("站点证据采样：开始")
        for subscribe in (self._subscribe_oper.list(state="P,R") or []):
            if (
                getattr(subscribe, "state", None) in ("P", "R")
                and
                resolve_subscribe_media_type(subscribe) == MediaType.TV
                and not is_full_best_version_subscribe(subscribe)
                and not bool(getattr(subscribe, "manual_total_episode", False))
            ):
                site_evidence.refresh_subscribe(subscribe)

    def run_completion_verify(self):
        """完成后自验证巡检：复查完成快照，发现 TMDB 增集后重建订阅并通知。"""
        verifier = self._modules.get("verifier")
        if verifier:
            detail("完成后验证：开始")
            verifier.verify_all()

    def run_completion_snapshot_cleanup(self):
        """按 verify_retention_days 清理 H 快照，不触发自动纠错或 TMDB 请求。"""
        verifier = self._modules.get("verifier")
        if verifier:
            removed = verifier.cleanup_expired()
            if removed:
                logger.info(f"完成快照清理：已清理 {removed} 条过期快照")

    def run_subscription_cleanup_expired(self):
        """清理超过 36 小时的订阅清理事务。"""
        subscription_cleanup = self._modules.get("subscription_cleanup")
        if subscription_cleanup:
            removed = subscription_cleanup.cleanup_expired_clear_histories()
            if removed:
                logger.info(f"订阅清理事务：已清理 {removed} 条超过 36 小时的记录")

    def _last_download_date(self, subscribe) -> Optional[datetime.date]:
        """订阅最近一次真实下载日期（取自主程序下载历史），无则 None。"""
        try:
            mtype = subscribe.type
            title = subscribe.name
            year = subscribe.year
            tmdbid = subscribe.tmdbid
            if mtype == "电影":
                histories = self._downloadhistory_oper.get_last_by(
                    mtype=mtype,
                    title=title,
                    year=year,
                    tmdbid=tmdbid,
                )
            else:
                season = subscribe.season
                histories = self._downloadhistory_oper.get_last_by(
                    mtype=mtype,
                    title=title,
                    year=year,
                    season=f"S{int(season):02d}" if season is not None else None,
                    tmdbid=tmdbid,
                )
            history_dates = [history.date for history in histories or [] if history.date]
            if not history_dates:
                return None
            last_download = max(history_dates)
            if isinstance(last_download, datetime.datetime):
                return last_download.date()
            if isinstance(last_download, datetime.date):
                return last_download
            return (
                parse_date(last_download, fmt="%Y-%m-%d %H:%M:%S")
                or parse_date(last_download)
            )
        except Exception:
            return None

    def _related_download_histories(self, subscribe) -> list:
        """获取同一订阅完成后的分集下载历史，用于判断是否应自动洗版。"""
        try:
            if subscribe.type == "电影":
                histories = self._downloadhistory_oper.get_last_by(
                    mtype=subscribe.type,
                    title=subscribe.name,
                    year=subscribe.year,
                    tmdbid=subscribe.tmdbid,
                )
            else:
                histories = self._downloadhistory_oper.get_last_by(
                    mtype=subscribe.type,
                    title=subscribe.name,
                    year=subscribe.year,
                    season=f"S{int(subscribe.season):02d}" if subscribe.season is not None else None,
                    tmdbid=subscribe.tmdbid,
                )
        except Exception as err:
            logger.warning(f"洗版编排：查询关联下载历史失败，跳过分集洗版判定：{err}")
            return []

        related = []
        subscribe_date = self._parse_datetime(subscribe.date)
        for history in histories or []:
            source = history.note.get("source") if isinstance(history.note, dict) else ""
            source_info = self._subscribe_info_from_source(source)
            if not source_info:
                continue
            if source_info.get("id") != subscribe.id:
                continue
            if source_info.get("tmdbid") != subscribe.tmdbid:
                continue
            if source_info.get("year") != subscribe.year:
                continue
            history_date = self._parse_datetime(history.date)
            if subscribe_date and history_date and history_date <= subscribe_date:
                continue
            if subscribe.type != "电影":
                if source_info.get("season") != subscribe.season:
                    continue
                source_episode_group = source_info.get("episode_group")
                if source_episode_group and source_episode_group != subscribe.episode_group:
                    continue
                if history.episode_group and history.episode_group != subscribe.episode_group:
                    continue
                if self._is_full_pack_download(history, subscribe.total_episode):
                    continue
            related.append(history)
        return related

    @staticmethod
    def _is_full_pack_download(history, total_episode: Optional[int]) -> bool:
        """判断下载历史是否为合集/全集包；全集包不参与分集洗版触发计数。"""
        if not total_episode:
            return False
        meta_info = MetaInfo(title=history.torrent_name, subtitle=history.torrent_description)
        if meta_info.total_episode == total_episode:
            return True
        text = f"{history.torrent_name or ''} {history.torrent_description or ''}"
        patterns = (
            rf"全\s*{int(total_episode)}\s*集",
            rf"complete\s*{int(total_episode)}\s*(?:episodes?|eps?)",
            rf"{int(total_episode)}\s*(?:episodes?|eps?)\s*complete",
        )
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _subscribe_info_from_source(source: str) -> dict:
        """从下载历史 source 中解析订阅信息；解析失败按无关联处理。"""
        if not source or "|" not in source:
            return {}
        _prefix, raw = source.split("|", 1)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _parse_datetime(value):
        """解析下载历史/订阅时间，无法解析时返回 None。"""
        if not value:
            return None
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            return datetime.datetime.combine(value, datetime.time.min)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(str(value), fmt)
            except ValueError:
                continue
        return None

    def run_no_download_check(self):
        """无下载处理巡检：上映后超期且无下载的订阅按策略暂停、完成或删除。"""
        policy = self._modules.get("no_download_policy")
        lifecycle = self._modules.get("lifecycle")
        if not policy or not lifecycle or not self._subscribe_oper:
            return

        detail("无下载处理巡检：开始")
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            mediainfo = self._recognize_mediainfo(subscribe)
            if not mediainfo:
                continue
            decision = policy.evaluate_detail(
                subscribe,
                mediainfo,
                self._last_download_date(subscribe),
            )
            action = decision.action if decision else None
            subscribe_id = subscribe.id
            if action == "pause":
                logger.info(
                    f"无下载处理：{format_subscribe(subscribe)}(id={subscribe_id}) "
                    f"原因={decision.reason}，处理=暂停订阅"
                )
                result = lifecycle.pause_for_no_download(subscribe, decision.reason)
                if not result.changed:
                    continue
            elif action == "complete":
                logger.info(
                    f"无下载处理：{format_subscribe(subscribe)}(id={subscribe_id}) "
                    f"原因={decision.reason}，处理=写入完成历史并删除订阅"
                )
                payload = subscribe.to_dict()
                self._subscribe_oper.add_history(**payload)
                self._subscribe_oper.delete(subscribe_id)
            elif action == "delete":
                logger.info(
                    f"无下载处理：{format_subscribe(subscribe)}(id={subscribe_id}) "
                    f"原因={decision.reason}，处理=删除订阅"
                )
                self._subscribe_oper.delete(subscribe_id)
            else:
                continue
            if action != "pause":
                self._task_manager.clear_tasks(subscribe_id)
            self._send_no_download_notification(subscribe, mediainfo, action, reason=decision.reason)

    def run_deletes_cleanup(self):
        """删除指纹老化清理：移除超过保留期的近期删除资源，避免长期误挡同源资源。"""
        deletes_store = self._modules.get("deletes_store")
        if deletes_store:
            removed = deletes_store.cleanup_expired(self._config.delete_record_retention_hours)
            if removed:
                logger.info(f"删除指纹清理：已清理 {removed} 条过期记录（近期删除资源）")

    def get_state(self) -> bool:
        """返回插件总开关状态。"""
        return self._config is not None and self._config.enabled

    # ---- 事件处理器：注册在插件类上。主程序按 handler.__qualname__ 的首段（类名=plugin_id）
    #      解析运行实例分发（app/core/event.py），故 handler 必须是插件类方法，不能注册 EventProxy
    #      的绑定方法（否则按 "EventProxy" 找不到运行插件、事件永不触发）。实际逻辑委托 EventProxy，
    #      未启用的域在 EventProxy 内部按 get() 短路。----

    @eventmanager.register(ChainEventType.SubscribeCompletionCheck)
    def on_completion_check(self, event):
        """订阅完成检查 → 完成守卫（链式事件，可否决完成）。"""
        if self._event_proxy:
            self._event_proxy.on_completion_check(event)

    @eventmanager.register(ChainEventType.SubscribeEpisodesRefresh)
    def on_episodes_refresh(self, event):
        """订阅集数刷新 → 变更速率记录 + 站点证据消费 + 待定状态观察。"""
        if self._event_proxy:
            self._event_proxy.on_episodes_refresh(event)

    @eventmanager.register(EventType.SubscribeAdded)
    def on_subscribe_added(self, event):
        """订阅新增 → 优先级回填 + 播出暂停 + 待定判定。"""
        if self._event_proxy:
            self._event_proxy.on_subscribe_added(event)

    @eventmanager.register(EventType.SubscribeDeleted)
    def on_subscribe_deleted(self, event):
        """订阅删除 → 清理关联任务数据。"""
        if self._event_proxy:
            self._event_proxy.on_subscribe_deleted(event)

    @eventmanager.register(EventType.SubscribeModified)
    def on_subscribe_modified(self, event):
        """订阅修改 → 任务状态重置 + 普通转洗版回填。"""
        if self._event_proxy:
            self._event_proxy.on_subscribe_modified(event)

    @eventmanager.register(EventType.SubscribeComplete)
    def on_subscribe_complete(self, event):
        """订阅完成 → 任务清理 + H 完成快照 + 自动洗版编排。"""
        if self._event_proxy:
            self._event_proxy.on_subscribe_complete(event)

    @eventmanager.register(EventType.DownloadAdded)
    def on_download_added(self, event):
        """DownloadAdded → 种子监控登记 + 下载待定 hash 确认。"""
        if self._event_proxy:
            self._event_proxy.on_download_added(event)

    @eventmanager.register(EventType.TransferComplete)
    def on_transfer_complete(self, event):
        """整理完成 → 移动模式任务同步清理 + 下载待定清除。"""
        if self._event_proxy:
            self._event_proxy.on_transfer_complete(event)

    @eventmanager.register(ChainEventType.ResourceSelection)
    def on_resource_selection(self, event):
        """ResourceSelection → 洗版待定按集串行 + 识别增强候选准入 + 删除指纹防重过滤。"""
        if self._event_proxy:
            self._event_proxy.on_resource_selection(event)

    @eventmanager.register(ChainEventType.ResourceDownload, priority=9999)
    def on_resource_download(self, event):
        """ResourceDownload → 订阅清理 + 无 hash 下载待定 + 洗版优先级基线。"""
        if self._event_proxy:
            self._event_proxy.on_resource_download(event)

    @eventmanager.register(ChainEventType.TransferIntercept, priority=9999)
    def on_transfer_intercept(self, event):
        """整理拦截 → 订阅清理目标媒体文件。"""
        if self._event_proxy:
            self._event_proxy.on_transfer_intercept(event)

    @eventmanager.register(EventType.PluginAction)
    def on_plugin_action(self, event):
        """插件命令 → /subscribe_toggle 切换订阅状态。"""
        if self._event_proxy:
            self._event_proxy.on_plugin_action(event)

    @eventmanager.register(ChainEventType.PluginDataReset)
    def on_plugin_data_reset(self, event):
        """插件数据重置前 → 恢复增强版持有的订阅状态。"""
        event_data = event.event_data
        if not event_data or event_data.plugin_id != self.__class__.__name__ or not event_data.reset_data:
            return
        self._reset_task_data()

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册 /subscribe_toggle 远程命令：切换订阅启用/禁用状态。"""
        return [{
            "cmd": "/subscribe_toggle",
            "event": EventType.PluginAction,
            "desc": "切换订阅状态",
            "category": "订阅",
            "data": {"action": "subscribe_toggle"},
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        """暴露只读概览接口：返回各业务域启用状态与待定/监控计数。"""
        return [{
            "path": "/summary",
            "endpoint": self._api_summary,
            "methods": ["GET"],
            "auth": "bear",
            "summary": "订阅助手（增强版）概览",
            "description": "返回各业务域启用状态与待定/监控计数",
        }]

    def _api_summary(self) -> Dict[str, Any]:
        """概览数据：各业务域启用状态 + 待定订阅与监控种子计数。"""
        cfg = self._config or PluginConfig({})
        subscribes = self.get_data("subscribes") or {}
        torrents = self.get_data("torrents") or {}
        pending = sum(1 for task in subscribes.values()
                      if isinstance(task, dict) and task.get("state") == "P")
        return {
            "domains": {
                "完结守卫模式": cfg.completion_guard_mode,
                "待定增强": cfg.pending_enhanced_enabled,
                "暂停优化": cfg.pause_enhanced_enabled,
                "自动洗版": cfg.best_version_type != "no",
                "下载管理": cfg.download_monitor_enabled,
                "完成后验证": cfg.verify_enabled,
                "站点集数探测": cfg.site_total_probe_enabled,
                "站点完结信号": cfg.site_completion_evidence_enabled,
                "识别增强": cfg.recognition_guard_mode,
            },
            "pending_count": pending,
            "monitored_torrents": len(torrents),
        }

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """使用 Vue 联邦组件渲染配置页，构建产物随插件发布。"""
        return "vue", "frontend/dist/assets"

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回宿主配置接口需要的表单结构和默认模型，Vue Config 使用默认模型初始化。"""
        from .form import build_form
        return build_form()

    def get_page(self) -> Optional[List[dict]]:
        """不提供详情页：框架按 has_page=False 处理，运行概况由 summary API 提供。"""
        pass

    def _tmdb_episodes(self, tmdbid: int, season: int, episode_group: str = None):
        """查询 TMDB 季内集信息供完成证据流水线构建 SeasonScope；不可用时返回空列表。"""
        if not self._tmdb_chain or not tmdbid or season is None:
            return []
        return self._tmdb_chain.tmdb_episodes(
            tmdbid=tmdbid, season=season, episode_group=episode_group
        ) or []

    @staticmethod
    def _site_cache_candidates(subscribe, **kwargs):
        """读取主程序已有 RSS/spider 缓存候选；不触发站点刷新或缓存写入。"""
        chain = TorrentsChain()
        helper = getattr(chain, "get_subscribe_cache_candidates", None)
        if not callable(helper):
            if not SubscribeAssistantEnhanced._site_cache_candidate_helper_warned:
                logger.warning(
                    "信号引擎(S)：当前 MoviePilot 主程序缺少站点缓存候选读取能力，"
                    "跳过站点证据扫描；请升级主程序后再启用站点证据"
                )
                SubscribeAssistantEnhanced._site_cache_candidate_helper_warned = True
            return []
        return helper(subscribe, **kwargs)

    @staticmethod
    def _mediainfo_from_dict(data):
        """从事件 mediainfo dict 重建 MediaInfo 对象；空数据返回 None。"""
        if not data:
            return None
        from app.core.context import MediaInfo
        mediainfo = MediaInfo()
        mediainfo.from_dict(data)
        return mediainfo

    @staticmethod
    def _is_tv_media(mediainfo) -> bool:
        """媒体是否为剧集（电影无季/集，不做播出暂停与待定）。"""
        from app.schemas.types import MediaType
        return mediainfo.type == MediaType.TV

    def _recognize_mediainfo(self, subscribe):
        """从订阅识别 MediaInfo，供定时巡检评估完结/释放；识别失败返回 None。"""
        meta = build_subscribe_meta(subscribe, failure_context="媒体识别失败")
        if meta is None:
            return None
        try:
            return self.chain.recognize_media(
                meta=meta, mtype=meta.type,
                tmdbid=subscribe.tmdbid,
                episode_group=subscribe.episode_group,
                cache=False)
        except Exception as err:
            logger.warning(f"媒体识别失败：{format_subscribe(subscribe)}，错误：{redact_sensitive_text(err)}")
            return None

    def _recognize_by_meta_for_recognition(self, meta_info):
        """识别增强二次识别入口；外部识别失败按无补充证据处理。"""
        if not meta_info:
            return None
        try:
            return self.chain.recognize_media(meta=meta_info, mtype=getattr(meta_info, "type", None), cache=False)
        except Exception as err:
            logger.warning(f"识别增强二次识别失败：{redact_sensitive_text(err)}")
            return None

    def _detect_existing_episodes(self, subscribe) -> list:
        """返回订阅目标范围内媒体库已经存在的集。"""
        existing, _ = self._detect_episode_coverage(subscribe)
        return existing

    def _detect_backfill_episodes(self, subscribe) -> list:
        """返回洗版回填候选：媒体库已有集与订阅 note 中的已下载集并集。"""
        total_episode = subscribe.total_episode or 0
        try:
            total_episode = int(total_episode)
        except (TypeError, ValueError):
            total_episode = 0
        candidates = {
            episode
            for episode in self._detect_existing_episodes(subscribe)
            if isinstance(episode, int) and 1 <= episode <= total_episode
        }
        for episode in subscribe.note or []:
            try:
                episode_number = int(episode)
            except (TypeError, ValueError):
                continue
            if 1 <= episode_number <= total_episode:
                candidates.add(episode_number)
        return sorted(candidates)

    def _detect_missing_episodes(self, subscribe) -> list:
        """返回订阅目标范围内媒体库仍缺失的集。"""
        _, missing = self._detect_episode_coverage(subscribe)
        return missing

    def _resolve_subscribe_missing(self, subscribe, mediainfo, meta=None,
                                   best_version_accept_downloaded: bool = False):
        """按主程序订阅目标口径查询剩余缺集，不触发订阅完成写库。"""
        if meta is None:
            meta = build_subscribe_meta(subscribe, failure_context="目标缺集查询失败")
            if meta is None:
                return False, {}
        if self._subscribe_chain is None:
            logger.warning(f"目标缺集查询失败：{format_subscribe(subscribe)}，主程序订阅链未初始化")
            return False, {}
        return self._subscribe_chain.resolve_subscribe_missing(
            subscribe=subscribe,
            meta=meta,
            mediainfo=mediainfo,
            best_version_accept_downloaded=best_version_accept_downloaded,
        )

    def _detect_episode_coverage(self, subscribe) -> Tuple[list, list]:
        """复用主程序缺集探测并返回 (已存在集, 缺失集)；探测失败按目标集全部缺失处理。"""
        total = subscribe.total_episode or 0
        start_episode = subscribe.start_episode or 1
        target = set(range(start_episode, total + 1))
        if not target:
            return [], []
        try:
            from app.chain.download import DownloadChain
            mediainfo = self._recognize_mediainfo(subscribe)
            if not mediainfo:
                return [], sorted(target)
            season = subscribe.season if subscribe.season is not None else 0
            meta = build_subscribe_meta(subscribe, failure_context="媒体库缺集探测失败")
            if meta is None:
                return [], sorted(target)
            totals = {season: total} if subscribe.season is not None and total else {}
            exist_flag, no_exists = DownloadChain().get_no_exists_info(meta=meta, mediainfo=mediainfo, totals=totals)
            if exist_flag:
                return sorted(target), []
            missing = set()
            matched_scope = False
            for seasons in (no_exists or {}).values():
                info = seasons.get(season) if isinstance(seasons, dict) else None
                if info is None:
                    continue
                matched_scope = True
                eps = info.episodes
                if eps:
                    missing.update(eps)
                else:
                    # 主程序以空 episodes 表示该季目标范围整季缺失。
                    missing.update(target)
            if not matched_scope:
                missing.update(target)
            if missing and missing.isdisjoint(target):
                detail(
                    f"媒体库缺集探测：{format_subscribe(subscribe)} 返回集号 {sorted(missing)[:5]} "
                    f"不在订阅目标集 {start_episode}-{total} 内，按目标集仍缺失处理"
                )
                missing = set(target)
            missing &= target
            return sorted(target - missing), sorted(missing)
        except Exception:
            return [], sorted(target)

    def _rebuild_subscribe_from_snapshot(self, snap: dict, config: dict) -> bool:
        """把 H 完成快照转换为主程序要求的 MediaInfo + kwargs 订阅新增调用。"""
        if not self._subscribe_oper:
            return False
        probe = SimpleNamespace(
            name=config.get("name", ""),
            year=config.get("year"),
            season=snap.get("season"),
            type=config.get("type", "电视剧"),
            tmdbid=snap.get("tmdbid"),
            episode_group=snap.get("episode_group_id"),
        )
        mediainfo = self._recognize_mediainfo(probe)
        if not mediainfo:
            return False
        payload = dict(config)
        payload["season"] = snap.get("season")
        payload["episode_group"] = snap.get("episode_group_id")
        payload["manual_total_episode"] = 0
        try:
            subscribe_id, _ = self._subscribe_oper.add(mediainfo=mediainfo, **payload)
            if subscribe_id:
                logger.info(f"完成后验证：{_format_snapshot_label(snap)} 检测到增集，已重建订阅（新 id={subscribe_id}）")
                self._send_subscribe_added(subscribe_id, mediainfo)
            return bool(subscribe_id)
        except Exception as err:
            logger.warning(
                "订阅助手（增强版）按完成快照重建订阅失败："
                f"{_format_snapshot_label(snap)}, error={err}"
            )
            return False

    def _delete_downloader_torrent(self, downloader, torrent_hash):
        """从下载器删除种子（delete_file=True，连源文件一并删）；缺下载器服务或参数时跳过。

        删除不可逆，仅由超时/Tracker 巡检判定后经 TorrentCleanup 调用。
        """
        if not self._downloader_helper or not downloader or not torrent_hash:
            return
        service = self._downloader_helper.get_service(name=downloader)
        if service and service.instance:
            logger.info(f"删除种子：从下载器 {downloader} 删除种子 {torrent_hash}（含源文件，不可逆）")
            service.instance.delete_torrents(delete_file=True, ids=torrent_hash)

    def _fetch_downloader_torrent(self, downloader, torrent_hash):
        """连下载器取单个种子并映射为 TorrentInfo；取不到或下载器出错返回 None。

        巡检据此判定超时——返回 None 时该种子本轮跳过，避免下载器瞬断被误判为无进度而删种。
        """
        if not self._downloader_helper or not downloader or not torrent_hash:
            return None
        service = self._downloader_helper.get_service(name=downloader)
        if not service or not service.instance:
            return None
        torrents, error = service.instance.get_torrents(ids=torrent_hash)
        if error or not torrents:
            detail(f"下载器查询：{downloader} 取种子 {torrent_hash} 无结果或瞬断（error={bool(error)}），本轮跳过该种子")
            return None
        from .download.torrent import TorrentAdapter
        return TorrentAdapter.get_info(torrents[0], service.type)

    def _downloader_torrent_present(self, downloader, torrent_hash):
        """探测种子是否仍在下载器：True=在；False=下载器可达但已不存在；None=不可判定（无服务/报错）。

        与 _fetch_downloader_torrent 的区别：后者把"报错"与"不存在"都压成 None；本方法据 get_torrents
        的 error 标志区分，让手动删除监听把"用户删种"与"下载器瞬断"分开，避免瞬断误触发删除处理。
        顺序固定为先判下载器可达、再判种子缺失，避免把瞬断当成确删。
        """
        if not self._downloader_helper or not downloader or not torrent_hash:
            return None
        service = self._downloader_helper.get_service(name=downloader)
        if not service or not service.instance:
            return None
        torrents, error = service.instance.get_torrents(ids=torrent_hash)
        if error:
            return None
        return bool(torrents)

    def _schedule_delayed_subscribe_search(self, subscribe, scene: str):
        """随机延迟执行单订阅搜索，并返回实际延迟秒数供调用方展示。"""
        if not self._subscribe_chain or not subscribe:
            return None
        sid = subscribe.id
        if sid:
            delay_minutes = random.uniform(3, 5)
            delay_seconds = delay_minutes * 60
            logger.info(
                f"{scene}：{format_subscribe(subscribe)} 将在 {delay_minutes:.2f} 分钟后触发补全搜索"
            )
            threading.Timer(delay_seconds, lambda: self._subscribe_chain.search(sid=sid)).start()
            return delay_seconds
        return None

    def _search_subscribe(self, subscribe):
        """删种后随机延迟补搜，并返回实际延迟秒数供通知展示。"""
        return self._schedule_delayed_subscribe_search(subscribe, scene="种子删除处理")

    def _schedule_initial_pending_search(self, subscribe):
        """新增订阅进入待定前安排一次单订阅搜索。"""
        return self._schedule_delayed_subscribe_search(subscribe, scene="新增待定处理")

    def _get_transfer_histories(self, tmdbid, mtype, season=None, episode=None):
        """按 tmdbid/类型/季/集获取整理历史记录，供订阅清理定位旧文件。"""
        if not self._transferhistory_oper:
            return []
        if season is not None and episode is not None:
            return self._transferhistory_oper.get_by(tmdbid=tmdbid, mtype=mtype, season=season, episode=episode) or []
        if season is not None:
            return self._transferhistory_oper.get_by(tmdbid=tmdbid, mtype=mtype, season=season) or []
        return self._transferhistory_oper.get_by(tmdbid=tmdbid, mtype=mtype) or []

    def _delete_media_file(self, fileitem_dict):
        """删除媒体文件（旧源文件或旧媒体库文件）；fileitem_dict 为整理记录的 src/dest_fileitem 序列化形态。

        删除不可逆，仅由订阅清理调用；清理范围由订阅清理配置控制。
        """
        if not self._storage_chain or not fileitem_dict:
            return False
        from app import schemas
        path = fileitem_dict.get("path") if isinstance(fileitem_dict, dict) else None
        logger.info(f"订阅清理：删除媒体文件 {truncate_log_value(path or fileitem_dict)}（不可逆）")
        return self._storage_chain.delete_media_file(schemas.FileItem(**fileitem_dict))

    def _send_download_file_deleted(self, src, download_hash):
        """发 DownloadFileDeleted 事件：主程序据此移除历史下载旧种子。"""
        detail(f"订阅清理：发送 DownloadFileDeleted 事件，hash={download_hash}，通知主程序移除旧下载")
        eventmanager.send_event(EventType.DownloadFileDeleted, {"src": src, "hash": download_hash})

    def _torrent_exists(self, download_hash: str) -> Optional[bool]:
        """跨全部下载器查询旧 hash；任一查询失败且均未命中时返回 None。"""
        if not self._downloader_helper or not download_hash:
            return None
        services = self._downloader_helper.get_services()
        if not services:
            return None
        query_failed = False
        for name, service in services.items():
            if not service or not service.instance:
                query_failed = True
                continue
            try:
                torrents, error = service.instance.get_torrents(ids=download_hash)
            except Exception as err:
                logger.warning(f"订阅清理：查询下载器 {name} 的旧任务失败 hash={download_hash}，错误信息：{err}")
                query_failed = True
                continue
            if error:
                logger.warning(f"订阅清理：下载器 {name} 查询旧任务失败 hash={download_hash}")
                query_failed = True
                continue
            if torrents:
                return True
        if query_failed:
            return None
        return False

    def _send_subscribe_added(self, subscribe_id, mediainfo=None, username=None):
        """发 SubscribeAdded 事件，让主程序和其他插件感知订阅创建。"""
        eventmanager.send_event(EventType.SubscribeAdded, {
            "subscribe_id": subscribe_id,
            "username": username or self.plugin_name,
            "mediainfo": mediainfo.to_dict() if mediainfo else {},
        })

    def _format_subscribe_desc(self, subscribe, mediainfo=None) -> str:
        """生成通知标题中的订阅描述，优先使用媒体标题和季号。"""
        title = mediainfo.title_year if mediainfo else subscribe.name
        season = f" S{subscribe.season}" if subscribe.season is not None else ""
        return f"{title}{season}"

    def _restore_subscribe_from_snapshot(self, subscribe_dict: dict, mediainfo=None) -> bool:
        """根据订阅快照重建分集洗版订阅，并补发 SubscribeAdded 事件。"""
        try:
            from app.db.models import Subscribe
            restore_payload = {
                key: value
                for key, value in (subscribe_dict or {}).items()
                if hasattr(Subscribe, key)
            }
            restore_payload["manual_total_episode"] = 0
            restored = Subscribe(**restore_payload)
            restored.create(self._subscribe_oper._db)
            sid = restore_payload.get("id")
            if sid and self._subscribe_oper.get(sid):
                self._send_subscribe_added(sid, mediainfo, username=restore_payload.get("username"))
                return True
        except Exception as err:
            logger.error(f"重建分集洗版订阅时发生异常: {err}")
        return False

    def _send_no_download_notification(self, subscribe, mediainfo, action: str,
                                       reason: Optional[str] = None):
        """发送无下载处理状态通知。"""
        action_name = {"pause": "暂停", "complete": "完成", "delete": "删除"}.get(action, action)
        days = self._config.tv_no_download_days if subscribe.type == "电视剧" else self._config.movie_no_download_days
        title = f"{self._format_subscribe_desc(subscribe, mediainfo)} 近 {days} 天未有下载记录，已标记{action_name}"
        self._notify_subscribe(
            title,
            score=mediainfo.vote_average,
            user=subscribe.username,
            reason=reason or "上映后超期且无下载",
            image=mediainfo.get_message_image(),
            link="#/subscribe/tv?tab=mysub" if subscribe.type == "电视剧" else "#/subscribe/movie?tab=mysub",
        )

    def _send_subscribe_status_notification(self, subscribe, title_suffix: str,
                                            mediainfo=None, detail: Optional[str] = None):
        """发送订阅状态变更通知，沿用状态类消息的标题和正文结构。"""
        mediainfo = mediainfo or self._recognize_mediainfo(subscribe)
        title = f"{self._format_subscribe_desc(subscribe, mediainfo)} {title_suffix}"
        media_type = mediainfo.type.value if mediainfo else subscribe.type
        self._notify_subscribe(
            title,
            score=mediainfo.vote_average if mediainfo else None,
            user=subscribe.username,
            reason=detail,
            image=mediainfo.get_message_image() if mediainfo else None,
            link="#/subscribe/tv?tab=mysub" if media_type == "电视剧" else "#/subscribe/movie?tab=mysub",
        )

    def _notify_subscribe(self, title, text=None, image=None, link=None,
                          score=None, user=None, reason=None, action=None,
                          follow_up=None, next_step=None, diagnostic: bool = False):
        """按通知开关发送订阅卡片，并统一正文字段顺序。

        状态结果使用单行字段，诊断明细使用多行字段；没有值的字段不输出。
        """
        if not self._config or not self._config.notify:
            return
        from app.schemas import NotificationType
        from app.core.config import settings
        if link and link.startswith("#"):
            link = settings.MP_DOMAIN(link)
        text = self._format_notification_text(
            text=text,
            score=score,
            user=user,
            reason=reason,
            action=action,
            follow_up=follow_up if follow_up is not None else next_step,
            diagnostic=diagnostic,
        )
        image = image or self.plugin_icon
        self.post_message(mtype=NotificationType.Subscribe, title=title, text=text, image=image, link=link)

    @staticmethod
    def _format_notification_text(text=None, score=None, user=None, reason=None,
                                  action=None, follow_up=None, diagnostic: bool = False):
        """按评分、用户、原因、处理、后续顺序生成通知正文。"""
        fields = [
            ("评分", score),
            ("用户", user),
            ("原因", reason),
            ("处理", action),
            ("后续", follow_up),
        ]
        parts = []
        if text not in (None, ""):
            parts.append(str(text))
        parts.extend([
            f"{label}：{str(value).replace(chr(10), '；')}"
            for label, value in fields
            if value not in (None, "")
        ])
        if not parts:
            return text
        separator = "\n" if diagnostic else "，"
        return separator.join(parts)

    @staticmethod
    def _get_subscribe_image(subscribe):
        """优先返回订阅背景图，其次返回海报的 w500 地址。"""
        if subscribe.backdrop:
            return subscribe.backdrop.replace("original", "w500")
        if subscribe.poster:
            return subscribe.poster.replace("original", "w500")
        return ""
