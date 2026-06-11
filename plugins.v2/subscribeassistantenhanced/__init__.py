"""订阅助手（增强版）——完整订阅生命周期管理。

7 个业务域：信号引擎、完成守卫、待定判定、暂停管理、洗版流程、下载管理、完成后验证。
（识别增强为有意下线能力，不纳入增强版。）
"""
import datetime
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Tuple, Optional

from apscheduler.triggers.cron import CronTrigger

from app.plugins import _PluginBase
from app.log import logger
from app.core.event import eventmanager
from app.schemas.types import EventType, ChainEventType
from app.chain.storage import StorageChain
from app.chain.subscribe import SubscribeChain
from app.chain.tmdb import TmdbChain
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.subscribe_oper import SubscribeOper
from app.db.transferhistory_oper import TransferHistoryOper
from app.helper.downloader import DownloaderHelper

from .engine.types import CompletionSignal, SeasonScope, PauseRecord
from .engine.volatility import VolatilityTracker
from .engine.evaluate import evaluate as engine_evaluate
from .guard import CompletionGuard
from .pending.judge import PendingJudge
from .pending.refresh import PendingRefresh
from .pause.airing import AiringPauseChecker
from .pause.manager import PauseManager
from .pause.nodownload import NoDownloadPolicy
from .best_version.priority import PriorityManager
from .best_version.converter import BestVersionConverter
from .best_version.orchestrator import BestVersionOrchestrator
from .download.monitor import DownloadMonitor
from .download.cleanup import TorrentCleanup
from .shared.deletes import DeletesStore
from .postcheck.verifier import CompletionVerifier
from .postcheck.timeout import PendingTimeoutManager
from .events import EventProxy
from .shared.media import parse_date
from .engine.signals import last_aired_episode
from .shared.task import TaskDataManager
from .shared.config import DEFAULT_DELETE_EXCLUDE_TAGS, DEFAULT_TRACKER_RESPONSE, PluginConfig
from .shared.log import detail, truncate_log_value
from .shared.subscribe import format_subscribe


class SubscribeAssistantEnhanced(_PluginBase):
    """订阅助手增强版——插件入口。

    生命周期：init_plugin → 事件注册 → 定时任务 → stop_service。
    配置表单由 get_form 提供；运行概况由日志和 summary API 提供。
    继承 _PluginBase 以获得真实数据层（get_data/save_data）、事件管理器与消息能力。
    """

    # 插件名称
    plugin_name = "订阅助手（增强版）"
    # 插件描述
    plugin_desc = "多场景管理订阅，实现订阅全生命周期管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/subscribeassistantenhanced.png"
    # 插件版本
    plugin_version = "0.1"
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

    def __init__(self):
        """初始化插件运行期依赖与一次性任务状态。"""
        super().__init__()
        self._config: Optional[PluginConfig] = None
        self._task_manager: Optional[TaskDataManager] = None
        self._event_proxy: Optional[EventProxy] = None
        self._modules: dict = {}
        self._onlyonce = False
        # 依赖的 DB oper / chain，在 init_plugin 实例化后注入各域模块
        self._subscribe_oper: Optional[SubscribeOper] = None
        self._subscribe_chain: Optional[SubscribeChain] = None
        self._tmdb_chain: Optional[TmdbChain] = None
        self._storage_chain: Optional[StorageChain] = None
        self._transferhistory_oper: Optional[TransferHistoryOper] = None
        self._downloadhistory_oper: Optional[DownloadHistoryOper] = None
        self._downloader_helper: Optional[DownloaderHelper] = None
        # 信号引擎评估闭包，供定时巡检（待定释放/洗版完成）复用
        self._evaluate_fn: Optional[Callable] = None

    def init_plugin(self, config: dict = None):
        """解析配置 → 注入 DB/chain 依赖 → 初始化各域模块。"""
        self.stop_service()

        raw_config, should_persist = self._normalize_persisted_config(config or {})
        self._config = PluginConfig(raw_config)

        # 依赖注入：构造即可用、不触发外部网络；供洗版/下载/补搜等域写库与查询
        self._subscribe_oper = SubscribeOper()
        self._subscribe_chain = SubscribeChain()
        self._tmdb_chain = TmdbChain()
        self._storage_chain = StorageChain()
        self._transferhistory_oper = TransferHistoryOper()
        self._downloadhistory_oper = DownloadHistoryOper()
        self._downloader_helper = DownloaderHelper()

        # 任务数据读写走 _PluginBase 的 get_data/save_data 落盘接口
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
        logger.info(
            "初始化完成："
            f"总开关={cfg.enabled} 完成守卫={cfg.completion_guard_enabled} "
            f"待定增强={cfg.pending_enhanced_enabled} 暂停优化={cfg.pause_enhanced_enabled} "
            f"洗版类型={cfg.best_version_type} 下载管理={cfg.download_monitor_enabled} "
            f"完成验证={cfg.verify_enabled} 通知={cfg.notify}"
        )

    @staticmethod
    def _normalize_persisted_config(config: dict) -> Tuple[dict, bool]:
        """规范化需要持久安全默认值的配置，避免旧空值覆盖表单默认 model。"""
        raw = dict(config or {})
        changed = False
        default_text_fields = {
            "delete_exclude_tags": DEFAULT_DELETE_EXCLUDE_TAGS,
            "default_tracker_response": DEFAULT_TRACKER_RESPONSE,
        }
        for key, default in default_text_fields.items():
            if key in raw and not str(raw.get(key) or "").strip():
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
        )
        verifier = CompletionVerifier(
            tm.read, tm.update,
            tmdb_episodes_fn=self._tmdb_episodes,
            subscribe_oper=self._subscribe_oper,
            retention_days=cfg.verify_retention_days,
            notify_fn=self._notify_subscribe,
            rebuild_subscribe_fn=self._rebuild_subscribe_from_snapshot,
        )
        priority_manager = PriorityManager(tm.read, tm.update, subscribe_oper=self._subscribe_oper)
        converter = BestVersionConverter(subscribe_oper=self._subscribe_oper)
        pending_refresh = PendingRefresh(
            tm.read,
            tm.update,
            subscribe_get_fn=self._subscribe_oper.get,
            tmdb_episodes_fn=self._tmdb_episodes,
        )
        # 用户名自动暂停名单：逗号分隔字符串解析为列表，剔除空白与空项；空名单即不启用该能力
        auto_pause_users = [u.strip() for u in (cfg.auto_pause_users or "").split(",") if u.strip()]
        # 注入 subscribe_oper：pause()/resume() 据此真实写订阅 DB state（S/R），否则只写插件任务数据
        pause_manager = PauseManager(
            tm.read,
            tm.update,
            subscribe_oper=self._subscribe_oper,
            auto_pause_users=auto_pause_users,
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
            fetch_fn=self._fetch_downloader_torrent,
            present_fn=self._downloader_torrent_present if cfg.manual_delete_listen else None,
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
        )

        def evaluate_fn(subscribe, mediainfo):
            return engine_evaluate(
                subscribe, mediainfo,
                tmdb_episodes_fn=self._tmdb_episodes,
                volatility_tracker=volatility,
                config=cfg,
            )

        airing_checker = AiringPauseChecker(
            pause_days=cfg.airing_pause_days,
            evaluate_fn=evaluate_fn,
            movie_air_days=cfg.movie_air_pause_days,
            tv_air_days=cfg.tv_air_pause_days,
        )
        self._evaluate_fn = evaluate_fn

        pending_judge = PendingJudge(
            config=cfg,
            evaluate_fn=evaluate_fn,
            subscribe_oper=self._subscribe_oper,
            timeout_manager=timeout_manager,
            task_data_read=tm.read,
            task_data_update=tm.update,
        )

        guard = CompletionGuard(
            evaluate_fn=evaluate_fn,
            has_active_downloads_fn=lambda sub: download_monitor.has_active_downloads(
                sub.id),
            mark_pending_fn=pending_judge.mark_pending,
            verifier=verifier,
            timeout_manager=timeout_manager,
            pending_download_enabled=cfg.pending_download_enabled,
        )

        orchestrator = BestVersionOrchestrator(
            priority_manager=priority_manager,
            evaluate_fn=evaluate_fn,
            subscribe_oper=self._subscribe_oper,
            task_data_read=tm.read,
            task_data_update=tm.update,
            get_histories_fn=self._get_transfer_histories,
            delete_media_file_fn=self._delete_media_file,
            delete_history_fn=self._transferhistory_oper.delete,
            send_download_file_deleted_fn=self._send_download_file_deleted,
            notify_fn=self._notify_subscribe,
            best_version_type=cfg.best_version_type,
            clear_history_type=cfg.best_version_clear_history_type,
        )

        self._event_proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=self._subscribe_oper,
            post_message=self.post_message,
            deletes_store=deletes_store if cfg.download_monitor_enabled else None,
            skip_deletion=cfg.skip_deletion,
            backfill_enabled=cfg.best_version_backfill_enabled,
            pending_download_enabled=cfg.pending_download_enabled,
            guard=guard if cfg.completion_guard_enabled else None,
            volatility=volatility if cfg.volatility_enabled else None,
            pending_refresh=pending_refresh if cfg.pending_enhanced_enabled else None,
            pause_manager=pause_manager if cfg.pause_enhanced_enabled else None,
            airing_checker=airing_checker if cfg.pause_enhanced_enabled else None,
            pending_judge=pending_judge if cfg.pending_enhanced_enabled else None,
            evaluate_fn=evaluate_fn,
            tmdb_episodes_fn=self._tmdb_episodes,
            mediainfo_from_dict=self._mediainfo_from_dict,
            is_tv_fn=self._is_tv_media,
            detect_existing_episodes_fn=self._detect_existing_episodes,
            priority_manager=priority_manager,
            download_monitor=download_monitor if cfg.download_monitor_enabled else None,
            verifier=verifier if cfg.verify_enabled else None,
            orchestrator=orchestrator,
        )

        self._modules = {
            "volatility": volatility,
            "timeout_manager": timeout_manager,
            "verifier": verifier,
            "priority_manager": priority_manager,
            "converter": converter,
            "pending_judge": pending_judge,
            "pending_refresh": pending_refresh,
            "pause_manager": pause_manager,
            # airing_checker 同时放入 _modules，供 run_meta_check 周期巡检按 enabled 门控读取
            "airing_checker": airing_checker if cfg.pause_enhanced_enabled else None,
            "no_download_policy": no_download_policy,
            "download_monitor": download_monitor,
            "torrent_cleanup": torrent_cleanup,
            "deletes_store": deletes_store,
            "guard": guard,
            "orchestrator": orchestrator,
        }

    def stop_service(self):
        """清理定时任务和事件监听。"""
        self._event_proxy = None
        self._modules = {}

    def get_service(self) -> List[Dict[str, Any]]:
        """按域开关注册定时任务，并按元数据周期复查待定订阅。

        插件总开关关闭时不注册任何任务。
        每个 job 的 func 指向插件类薄方法，委托对应域模块执行；模块周期方法未就绪时安全跳过。
        周期 job 多用 interval 触发器；洗版完成检查用 cron 触发器（CronTrigger）；一次性全量巡检用 date 触发器延迟执行。
        """
        if not self._config:
            return []
        if not self._config.enabled:
            return []
        cfg = self._config
        name = self.__class__.__name__
        services: List[Dict[str, Any]] = []
        if self._onlyonce:
            services.append({
                "id": f"{name}_onlyonce",
                "name": "立即运行一次",
                "trigger": "date",
                "run_date": datetime.datetime.now() + datetime.timedelta(seconds=3),
                "func": self.run_all_checks,
                "kwargs": {},
            })
        services.append({
            "id": f"{name}_meta_check",
            "name": "元数据检查",
            "trigger": "interval",
            "func": self.run_meta_check,
            "kwargs": {"hours": cfg.meta_check_interval_hours},
        })
        if cfg.download_monitor_enabled:
            services.append({
                "id": f"{name}_download",
                "name": "下载任务检查",
                "trigger": "interval",
                "func": self.run_download_timeout_check,
                "kwargs": {"minutes": cfg.download_check_interval_minutes},
            })
        if cfg.best_version_type != "no" and cfg.best_version_cron:
            # 洗版按 cron 调度，区别于其余域的 interval 周期；cron 为空则不注册该任务
            services.append({
                "id": f"{name}_best_version",
                "name": "洗版订阅检查",
                "trigger": CronTrigger.from_crontab(cfg.best_version_cron),
                "func": self.run_best_version_check,
            })
        if cfg.verify_enabled:
            services.append({
                "id": f"{name}_verify",
                "name": "自动纠错",
                "trigger": "interval",
                "func": self.run_completion_verify,
                "kwargs": {"hours": cfg.verify_interval_hours},
            })
        services.append({
            "id": f"{name}_common_check",
            "name": "通用巡检",
            "trigger": "interval",
            "func": self.run_common_check,
            "kwargs": {"minutes": cfg.auto_check_interval_minutes},
        })
        detail("注册定时任务：" + "、".join(s["name"] for s in services))
        return services

    def run_all_checks(self):
        """一次性全量巡检：串跑所有定时任务入口，各入口按域开关自行短路。"""
        logger.info("立即运行一次：开始全量巡检")
        self.run_meta_check()
        self.run_download_timeout_check()
        self.run_best_version_check()
        self.run_completion_verify()
        self.run_common_check()

    def _reset_task_data(self):
        """清空全部插件任务数据。"""
        for key in [
            "subscribes",
            "torrents",
            "blocks",
            "snapshots",
            "deletes",
            "volatility",
            "best_version_clear_histories",
        ]:
            self.save_data(key, {})
        logger.info("重置任务：已清空全部插件任务数据（订阅/种子/待定块/完成快照/删除指纹/波动/洗版历史清理）")

    def _run_backfill_now(self):
        """对现有洗版订阅执行一次回填已存在集。"""
        count = 0
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            if subscribe.best_version:
                existing = self._detect_existing_episodes(subscribe)
                if existing:
                    self._modules["priority_manager"].backfill_existing(subscribe, existing)
                    count += 1
                    detail(f"洗版回填：{format_subscribe(subscribe)} 回填在库集 {existing}")
        logger.info(f"洗版回填：完成，共处理 {count} 个洗版订阅")

    def run_download_timeout_check(self):
        """下载超时/Tracker 删种巡检：取下载器实时种子状态判定，超时或命中 Tracker 关键字则删种并善后。"""
        monitor = self._modules.get("download_monitor")
        cleanup = self._modules.get("torrent_cleanup")
        if monitor:
            detail("下载超时巡检：开始")
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

    def _best_version_overdue(self, subscribe, now=None) -> bool:
        """洗版是否超时限：从最近活动时间起算超过 best_version_remaining_days 天。

        活动时间取该订阅在 torrents 任务数据中的最新记录时间；
        无下载记录则按首次观察锚点（缺失则置当前时间）。
        remaining_days=0 表示不限，永不超时。
        """
        days = self._config.best_version_remaining_days
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
        """洗版巡检：超时终止优先，全集转换优先于本轮完成判定。

        完成判定复用媒体库缺集结果。
        """
        if self._config and self._config.best_version_type == "no":
            return
        orchestrator = self._modules.get("orchestrator")
        priority = self._modules.get("priority_manager")
        converter = self._modules.get("converter")
        if not orchestrator or not priority or not self._subscribe_oper:
            return
        detail("洗版巡检：开始")
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            if not subscribe.best_version:
                continue
            mediainfo = self._recognize_mediainfo(subscribe)
            if mediainfo:
                if self._best_version_overdue(subscribe):
                    logger.info(f"洗版巡检：{format_subscribe(subscribe)} 超过洗版时限，标记洗版完成并停止洗版")
                    priority.mark_complete(subscribe)
                    continue
                # 完成判定须带媒体库缺集：优先级达标 + F 稳定 + 目标集全覆盖才算洗版完成
                no_exists = self._detect_missing_episodes(subscribe)
                if (
                    self._config.best_version_episode_to_full
                    and converter
                    and not subscribe.best_version_full
                    and not no_exists
                ):
                    logger.info(f"洗版巡检：{format_subscribe(subscribe)} 目标集已全部在库，转为全集洗版")
                    converter.convert_to_full(subscribe)
                    continue
                if orchestrator.check_complete(subscribe, mediainfo, no_exists):
                    logger.info(f"洗版巡检：{format_subscribe(subscribe)} 优先级达标且缺集已补齐，判定洗版完成")
                    priority.mark_complete(subscribe)
            else:
                detail(f"洗版巡检：{format_subscribe(subscribe)} 媒体识别失败，本轮跳过")

    def run_meta_check(self):
        """元数据检查巡检：对活动订阅周期性复核上映前/播出暂停（双向）与待定（进入/退出）。

        暂停语义：
        - 标记暂停（no_download / auto_user）在 state=S 时直接跳过，
          不被上映检查自动恢复、也不重复处理；用户重新启用（state!=S）则清掉插件标记。
        - 上映/播出类暂停（pre_air / airing_gap）双向：条件成立时暂停，条件解除且当前为 S 时自动恢复。
        暂停复核优先于待定：命中暂停即写状态并跳过本轮待定；洗版订阅整体跳过。各能力按对应域开关门控。
        """
        if not self._subscribe_oper:
            return
        cfg = self._config
        pending_judge = self._modules.get("pending_judge")
        airing = self._modules.get("airing_checker")
        pause_manager = self._modules.get("pause_manager")
        detail("元数据巡检：开始")
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            if subscribe.best_version:
                continue

            # 标记暂停跳过/清标记必须在媒体识别前判定，避免 S 态订阅被上映检查自动恢复。
            record = pause_manager.get_pause_record(subscribe) if pause_manager else None
            reason = record.reason if record else None
            flag_paused = reason in ("no_download", "auto_user")
            state = subscribe.state
            if flag_paused and state == "S":
                detail(f"元数据巡检：{format_subscribe(subscribe)} 标记暂停({reason})且为禁用态，本轮跳过")
                continue
            if flag_paused and state != "S" and pause_manager:
                # 用户已重新启用：丢弃插件标记，状态归属交还订阅本身，继续后续上映/待定判定
                logger.info(f"元数据巡检：{format_subscribe(subscribe)} 用户已重新启用，清除插件暂停标记({reason})")
                pause_manager.clear_pause_record(subscribe)

            mediainfo = self._recognize_mediainfo(subscribe)
            if not mediainfo:
                continue

            if (
                cfg.pending_enhanced_enabled
                and pending_judge
                and subscribe.state == "P"
            ):
                # P 状态由待定域负责退出，避免上映前/播出暂停在同一轮把待定状态覆盖为 S。
                pending_judge.check_exit(subscribe, mediainfo, self._tmdb_episodes)
                continue

            # 上映/播出暂停复核（双向）：上映前（电影/剧集）+ 播出间隔（仅剧集）
            if cfg.pause_enhanced_enabled and airing and pause_manager:
                record_now = airing.check_pre_air(subscribe, mediainfo)
                if not record_now and self._is_tv_media(mediainfo):
                    episodes = self._tmdb_episodes(
                        subscribe.tmdbid,
                        subscribe.season,
                        episode_group=subscribe.episode_group,
                    )
                    record_now = airing.check(
                        subscribe, mediainfo,
                        next_episode=mediainfo.next_episode_to_air,
                        latest_episode=last_aired_episode(episodes),
                    )
                if record_now:
                    # 条件成立：尚未暂停才置 S；已是 S 则保持。暂停后本轮不再做待定
                    if state != "S":
                        logger.info(f"元数据巡检：{format_subscribe(subscribe)} 命中{record_now.reason}暂停，置为禁用")
                        pause_manager.pause(subscribe, record_now)
                    continue
                # 条件解除：仅恢复由上映/播出检查写入的 S 态订阅，避免触碰外部暂停状态。
                if state == "S":
                    logger.info(f"元数据巡检：{format_subscribe(subscribe)} 上映/播出暂停条件解除，恢复订阅")
                    pause_manager.resume(subscribe)

            # 待定复核：进入/退出
            if cfg.pending_enhanced_enabled and pending_judge:
                episodes = self._tmdb_episodes(
                    subscribe.tmdbid,
                    subscribe.season,
                    episode_group=subscribe.episode_group,
                )
                signal = self._evaluate_fn(subscribe, mediainfo) if self._evaluate_fn else None
                should, reason = pending_judge.should_enter_pending(
                    subscribe, mediainfo, episodes, signal
                )
                if should:
                    logger.info(f"元数据巡检：{format_subscribe(subscribe)} 判定进入待定（{reason}）")
                    pending_judge.mark_pending(subscribe, source="pending_judge", reason=reason)

    def run_pending_release(self):
        """待定释放巡检：先按来源退出 pending_judge 的 P 订阅，再兜底 guard_veto 超时释放。

        check_exit() 内部按 task source 分治：pending_judge 来源条件解除即退出；guard_veto 仅在
        signal.completed 时退出，其余仍由下方 blocks 超时路径释放。两条路径对 guard_veto 的释放
        （update state=R / clear_block）幂等，无副作用叠加。
        """
        detail("待定释放巡检：开始")
        pending_judge = self._modules.get("pending_judge")
        if pending_judge and self._subscribe_oper:
            for subscribe in (self._subscribe_oper.list(state="P") or []):
                mediainfo = self._recognize_mediainfo(subscribe)
                if mediainfo:
                    pending_judge.check_exit(subscribe, mediainfo, self._tmdb_episodes)

        timeout_manager = self._modules.get("timeout_manager")
        if not timeout_manager or not self._subscribe_oper or not self._evaluate_fn:
            return
        for sid in list((self.get_data("blocks") or {}).keys()):
            subscribe = self._subscribe_oper.get(int(sid))
            if not subscribe:
                detail(f"待定释放：订阅 {sid} 已不存在，清理残留待定块")
                timeout_manager.clear_block(int(sid))
                continue
            mediainfo = self._recognize_mediainfo(subscribe)
            if not mediainfo:
                continue
            if timeout_manager.check_release(int(sid), self._evaluate_fn(subscribe, mediainfo)):
                logger.info(f"待定释放：{format_subscribe(subscribe)} 守门超时释放，状态置为 R")
                self._subscribe_oper.update(int(sid), {"state": "R"})
                timeout_manager.clear_block(int(sid))

    def run_common_check(self):
        """统一执行同周期的待定释放、无下载处理和删除记录清理。

        每个子任务独立捕获异常，避免单个业务域失败阻断同轮其他巡检。
        """
        tasks = []
        if self._config.timeout_release_enabled:
            tasks.append(("待定释放", self.run_pending_release))
        tasks.append(("无下载处理", self.run_no_download_check))
        if self._config.download_monitor_enabled:
            tasks.append(("删除记录清理", self.run_deletes_cleanup))

        detail("通用巡检：开始")
        for task_name, task in tasks:
            try:
                task()
            except Exception as err:
                logger.error(f"通用巡检：{task_name}执行失败：{err}", exc_info=True)

    def run_completion_verify(self):
        """完成后自验证巡检：复查完成快照，发现 TMDB 增集后重建订阅并通知。"""
        verifier = self._modules.get("verifier")
        if verifier:
            detail("完成后自验证巡检：开始")
            verifier.verify_all()

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

    def run_no_download_check(self):
        """无下载处理巡检：上映后超期且无下载的订阅按策略暂停、完成或删除。"""
        policy = self._modules.get("no_download_policy")
        pause_manager = self._modules.get("pause_manager")
        if not policy or not pause_manager or not self._subscribe_oper:
            return

        detail("无下载处理巡检：开始")
        for subscribe in (self._subscribe_oper.list(state="N,R,P") or []):
            mediainfo = self._recognize_mediainfo(subscribe)
            if not mediainfo:
                continue
            action = policy.evaluate(
                subscribe,
                mediainfo,
                self._last_download_date(subscribe),
            )
            subscribe_id = subscribe.id
            if action == "pause":
                logger.info(f"无下载处理：{format_subscribe(subscribe)}(id={subscribe_id}) 上映后超期且无下载，暂停订阅")
                pause_manager.pause(subscribe, PauseRecord(
                    reason="no_download",
                    since=time.time(),
                    detail="上映后超期且无下载",
                ))
            elif action == "complete":
                logger.info(f"无下载处理：{format_subscribe(subscribe)}(id={subscribe_id}) 上映后超期且无下载，写入完成历史并删除订阅")
                to_dict = getattr(subscribe, "to_dict", None)
                payload = to_dict() if callable(to_dict) else dict(getattr(subscribe, "__dict__", {}))
                self._subscribe_oper.add_history(**payload)
                self._subscribe_oper.delete(subscribe_id)
            elif action == "delete":
                logger.info(f"无下载处理：{format_subscribe(subscribe)}(id={subscribe_id}) 上映后超期且无下载，删除订阅")
                self._subscribe_oper.delete(subscribe_id)
            else:
                continue
            self._task_manager.clear_tasks(subscribe_id)

    def run_deletes_cleanup(self):
        """删除指纹老化清理巡检：清理超过保留期的删除指纹，避免长期误杀同源资源。"""
        deletes_store = self._modules.get("deletes_store")
        if deletes_store:
            removed = deletes_store.cleanup_expired(self._config.delete_record_retention_hours)
            if removed:
                logger.info(f"删除指纹清理：已清理 {removed} 条过期删除指纹")

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
        """订阅集数刷新 → 变更速率记录 + 待定集数覆盖。"""
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
        """订阅完成 → 任务清理 + H 快照 + 洗版编排。"""
        if self._event_proxy:
            self._event_proxy.on_subscribe_complete(event)

    @eventmanager.register(EventType.DownloadAdded)
    def on_download_added(self, event):
        """下载添加 → 种子监控登记。"""
        if self._event_proxy:
            self._event_proxy.on_download_added(event)

    @eventmanager.register(EventType.TransferComplete)
    def on_transfer_complete(self, event):
        """整理完成 → 移动模式任务同步清理 + 下载待定清除。"""
        if self._event_proxy:
            self._event_proxy.on_transfer_complete(event)

    @eventmanager.register(ChainEventType.ResourceSelection)
    def on_resource_selection(self, event):
        """资源选择 → 待定按集串行 + 删除资源防重过滤。"""
        if self._event_proxy:
            self._event_proxy.on_resource_selection(event)

    @eventmanager.register(ChainEventType.ResourceDownload, priority=9999)
    def on_resource_download(self, event):
        """资源下载 → 洗版优先级基线快照 + 洗版历史清理。"""
        if self._event_proxy:
            self._event_proxy.on_resource_download(event)

    @eventmanager.register(ChainEventType.TransferIntercept, priority=9999)
    def on_transfer_intercept(self, event):
        """整理拦截 → 洗版媒体库历史清理。"""
        if self._event_proxy:
            self._event_proxy.on_transfer_intercept(event)

    @eventmanager.register(EventType.PluginAction)
    def on_plugin_action(self, event):
        """插件命令 → /subscribe_toggle 切换订阅状态。"""
        if self._event_proxy:
            self._event_proxy.on_plugin_action(event)

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
            "summary": "订阅助手（增强版）概览",
            "description": "返回各业务域启用状态与待定/监控计数",
        }]

    def _api_summary(self) -> Dict[str, Any]:
        """概览数据：7 域启用状态 + 待定/监控种子计数（来自配置与任务数据）。"""
        cfg = self._config or PluginConfig({})
        subscribes = self.get_data("subscribes") or {}
        torrents = self.get_data("torrents") or {}
        pending = sum(1 for task in subscribes.values()
                      if isinstance(task, dict) and task.get("state") == "P")
        return {
            "domains": {
                "完成守卫": cfg.completion_guard_enabled,
                "待定增强": cfg.pending_enhanced_enabled,
                "暂停优化": cfg.pause_enhanced_enabled,
                "自动洗版": cfg.best_version_type != "no",
                "下载管理": cfg.download_monitor_enabled,
                "完成后验证": cfg.verify_enabled,
            },
            "pending_count": pending,
            "monitored_torrents": len(torrents),
        }

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回完整配置表单（vuetify schema 按 7 业务域折叠）+ 默认数据。"""
        from .form import build_form
        return build_form()

    def get_page(self) -> Optional[List[dict]]:
        """不提供详情页：框架按 has_page=False 处理，运行概况由 summary API 提供。"""
        pass

    def _tmdb_episodes(self, tmdbid: int, season: int, episode_group: str = None):
        """查询 TMDB 季内集信息供信号引擎判定完结；缺依赖或查询失败时返回空列表。"""
        if not self._tmdb_chain or not tmdbid or not season:
            return []
        return self._tmdb_chain.tmdb_episodes(
            tmdbid=tmdbid, season=season, episode_group=episode_group
        ) or []

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
        """媒体是否为电视剧（电影无季/集，不做播出暂停与待定）。"""
        from app.schemas.types import MediaType
        return mediainfo.type == MediaType.TV

    def _recognize_mediainfo(self, subscribe):
        """从订阅识别 MediaInfo，供定时巡检评估完结/释放；识别失败返回 None。"""
        from app.core.metainfo import MetaInfo
        from app.schemas.types import MediaType
        meta = MetaInfo(subscribe.name or "")
        meta.year = subscribe.year
        meta.begin_season = subscribe.season or None
        meta.type = MediaType.TV if str(subscribe.type) == MediaType.TV.value else MediaType.MOVIE
        try:
            return self.chain.recognize_media(
                meta=meta, mtype=meta.type,
                tmdbid=subscribe.tmdbid,
                episode_group=subscribe.episode_group,
                cache=False)
        except Exception as err:
            logger.warning(f"媒体识别失败：{format_subscribe(subscribe)}，错误：{err}")
            return None

    def _detect_existing_episodes(self, subscribe) -> list:
        """返回订阅目标范围内媒体库已经存在的集。"""
        existing, _ = self._detect_episode_coverage(subscribe)
        return existing

    def _detect_missing_episodes(self, subscribe) -> list:
        """返回订阅目标范围内媒体库仍缺失的集。"""
        _, missing = self._detect_episode_coverage(subscribe)
        return missing

    def _detect_episode_coverage(self, subscribe) -> Tuple[list, list]:
        """复用主程序缺集探测并返回 (已存在集, 缺失集)；探测失败按目标集全部缺失处理。"""
        total = subscribe.total_episode or 0
        start_episode = subscribe.start_episode or 1
        target = set(range(start_episode, total + 1))
        if not target:
            return [], []
        try:
            from app.chain.download import DownloadChain
            from app.core.metainfo import MetaInfo
            mediainfo = self._recognize_mediainfo(subscribe)
            if not mediainfo:
                return [], sorted(target)
            season = subscribe.season or 0
            meta = MetaInfo(subscribe.name or "")
            meta.begin_season = season or None
            exist_flag, no_exists = DownloadChain().get_no_exists_info(meta=meta, mediainfo=mediainfo)
            if exist_flag:
                return sorted(target), []
            missing = set()
            matched_scope = False
            for seasons in (no_exists or {}).values():
                info = seasons.get(season) if isinstance(seasons, dict) else None
                if info is None:
                    continue
                matched_scope = True
                eps = getattr(info, "episodes", None)
                if eps:
                    missing.update(eps)
                else:
                    # 主程序以空 episodes 表示该 scope 整季缺失。
                    missing.update(target)
            if not matched_scope:
                missing.update(target)
            missing &= target
            return sorted(target - missing), sorted(missing)
        except Exception:
            return [], sorted(target)

    def _rebuild_subscribe_from_snapshot(self, snap: dict, config: dict) -> bool:
        """把 H 快照配置转换为主程序要求的 MediaInfo + kwargs 订阅新增调用。"""
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
        try:
            subscribe_id, _ = self._subscribe_oper.add(mediainfo=mediainfo, **payload)
            if subscribe_id:
                logger.info(f"完成后验证：检测到增集，已重建订阅 tmdbid={snap.get('tmdbid')} season={snap.get('season')}（新 id={subscribe_id}）")
            return bool(subscribe_id)
        except Exception as err:
            logger.warning(
                "订阅助手（增强版）完成快照重建失败："
                f"tmdbid={snap.get('tmdbid')}, season={snap.get('season')}, error={err}"
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
        的 error 标志区分，让手动删除监听把"用户删种"与"下载器瞬断"分开，避免瞬断误触发善后。
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

    def _search_subscribe(self, subscribe):
        """删种后延迟触发该订阅补全搜索，避免长期缺集；延迟用于等待下载器清理与外部事件落定。"""
        if not self._subscribe_chain or not subscribe:
            return
        sid = subscribe.id
        if sid:
            logger.info(f"删种善后：{format_subscribe(subscribe)} 将在 300 秒后触发补全搜索")
            threading.Timer(300, lambda: self._subscribe_chain.search(sid=sid)).start()

    def _get_transfer_histories(self, tmdbid, mtype, season=None):
        """按 tmdbid/类型/季获取整理历史记录，供洗版清理定位旧文件。"""
        if not self._transferhistory_oper:
            return []
        if season is not None:
            return self._transferhistory_oper.get_by(tmdbid=tmdbid, mtype=mtype, season=season) or []
        return self._transferhistory_oper.get_by(tmdbid=tmdbid, mtype=mtype) or []

    def _delete_media_file(self, fileitem_dict):
        """删除媒体文件（洗版旧源文件或旧媒体库文件）；fileitem_dict 为整理记录的 src/dest_fileitem 序列化形态。

        删除不可逆，仅由洗版历史清理调用；清理范围由 best_version_clear_history_type 控制。
        """
        if not self._storage_chain or not fileitem_dict:
            return False
        from app import schemas
        path = fileitem_dict.get("path") if isinstance(fileitem_dict, dict) else None
        logger.info(f"洗版清理：删除媒体文件 {truncate_log_value(path or fileitem_dict)}（不可逆）")
        return self._storage_chain.delete_media_file(schemas.FileItem(**fileitem_dict))

    def _send_download_file_deleted(self, src, download_hash):
        """发 DownloadFileDeleted 事件：主程序据此移除历史下载的旧种子（洗版"清理历史下载种子"经此达成）。"""
        detail(f"洗版清理：发送 DownloadFileDeleted 事件，hash={download_hash}")
        eventmanager.send_event(EventType.DownloadFileDeleted, {"src": src, "hash": download_hash})

    def _notify_subscribe(self, title, text=None):
        """按通知开关发送订阅类通知（洗版清理等场景）。"""
        if not self._config or not self._config.notify:
            return
        from app.schemas import NotificationType
        self.post_message(mtype=NotificationType.Subscribe, title=title, text=text)
