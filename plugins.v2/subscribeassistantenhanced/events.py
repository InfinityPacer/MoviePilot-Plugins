"""事件薄代理——按域 enabled 开关按需注册，委托到对应模块。

12 个事件处理器：
- SubscribeCompletionCheck → guard
- SubscribeEpisodesRefresh → volatility.record (先) + site refresh consumer + pending observer (后)
- SubscribeAdded → best_version + priority.backfill + pause.auto_pause_user
- SubscribeDeleted → task_manager.cleanup
- SubscribeModified → 暂停状态归属维护 + task_manager.reset_on_modify
- SubscribeComplete → verifier.snapshot + best_version
- TransferIntercept → subscription_cleanup.history_clear
- ResourceSelection → 洗版串行 + 识别增强 + 删除指纹过滤
- ResourceDownload → subscription_cleanup + monitor.mark_pending
- DownloadAdded → monitor.on_download + 暂停订阅下载命中恢复
- TransferComplete → 清下载待定 + 移动模式清理 + 分集转全集补偿
- PluginAction → toggle_subscribe_state
"""
from types import SimpleNamespace

from app.log import logger
from app.core.context import MediaInfo
from app.schemas.event import SubscribeEpisodesRefreshEventData

from .shared.log import detail
from .shared.subscribe import (
    format_subscribe,
    format_subscribe_label,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    subscribe_from_source,
)


def _event_data(event):
    """取事件 payload（主程序固定放在 event.event_data）；链式事件的业务字段不从 wrapper 直读。"""
    return event.event_data


class EventProxy:
    """事件代理，持有各域模块引用，按 enabled 注册。"""

    def __init__(self, skip_deletion=True, backfill_enabled=True,
                 pending_download_enabled=True, download_monitor_enabled=True,
                 plugin_name="订阅助手（增强版）", **modules):
        """保存事件处理依赖；删除指纹过滤和洗版回填默认开启以兼容直接构造场景。"""
        modules["skip_deletion"] = skip_deletion
        modules["backfill_enabled"] = backfill_enabled
        modules["pending_download_enabled"] = pending_download_enabled
        modules["download_monitor_enabled"] = download_monitor_enabled
        modules["plugin_name"] = plugin_name
        self._modules = modules
        self._reset_backfilling_ids = set()

    def get(self, name):
        return self._modules.get(name)

    def _format_backfill_scene(self, scene: str) -> str:
        """为插件侧 backfill 调用补充插件名，向主程序保留可追踪来源。"""
        if scene.endswith(">") and "<" in scene:
            return scene
        return f"{scene}<{self.get('plugin_name')}>"

    def _format_subscribe_label(self, subscribe_id, subscribe_info=None):
        """按订阅 ID 生成日志标签；事件快照或查库成功时带名称、季号和 ID。"""
        if subscribe_id is None:
            return "未知订阅"
        if isinstance(subscribe_info, dict) and subscribe_info:
            return format_subscribe_label(SimpleNamespace(**subscribe_info), subscribe_id)
        subscribe_oper = self.get("subscribe_oper")
        subscribe = subscribe_oper.get(subscribe_id) if subscribe_oper else None
        return format_subscribe_label(subscribe, subscribe_id)

    def _schedule_initial_pending_search(self, subscribe):
        """新增态写入 P 前安排单订阅搜索，避免常规定时服务按 N 态过滤时漏掉首轮搜索。"""
        schedule_search = self.get("schedule_initial_pending_search_fn")
        if schedule_search:
            schedule_search(subscribe)

    @staticmethod
    def _format_episodes_refresh_label(data: SubscribeEpisodesRefreshEventData) -> str | None:
        """格式化集数刷新事件来源；订阅不可查或创建场景用媒体信息兜底。"""
        subscribe_id = data.subscribe_id
        parts = []
        mediainfo = data.mediainfo
        tmdbid = data.tmdbid
        if isinstance(mediainfo, MediaInfo):
            if mediainfo.title_year:
                parts.append(mediainfo.title_year)
            if tmdbid is None:
                tmdbid = mediainfo.tmdb_id
        elif isinstance(mediainfo, dict):
            title = mediainfo.get("title")
            year = mediainfo.get("year")
            if title:
                label = f"{title} ({year})" if year else title
                parts.append(label)
            if tmdbid is None:
                tmdbid = mediainfo.get("tmdb_id")
        season = data.season
        if season is not None:
            parts.append(f"S{season}")
        markers = []
        if subscribe_id:
            markers.append(f"id={subscribe_id}")
        if tmdbid:
            markers.append(f"tmdbid={tmdbid}")
        scene = data.scene
        if scene:
            markers.append(f"scene={scene}")
        if markers:
            marker_text = f"({', '.join(markers)})"
            if parts:
                parts[-1] = f"{parts[-1]}{marker_text}"
            else:
                parts.append(marker_text)
        return " ".join(parts) if parts else "未知订阅"

    def on_completion_check(self, event):
        """CompletionCheck → guard。"""
        guard = self.get("guard")
        if guard:
            guard.handle(event)

    def on_episodes_refresh(self, event):
        """EpisodesRefresh → F record (先) + 站点证据消费 + pending observer (后)。

        链式事件：业务字段在 event.event_data（主程序只回读该数据类），wrapper 上没有这些字段。
        """
        data: SubscribeEpisodesRefreshEventData = _event_data(event)
        if data is None:
            return
        label = None
        if data.subscribe_id is not None:
            label = self._format_subscribe_label(data.subscribe_id)
            if label == f"订阅 {data.subscribe_id}":
                label = self._format_episodes_refresh_label(data) or label
        else:
            label = self._format_episodes_refresh_label(data)
        label = label or "未知订阅"
        detail(f"集数刷新事件：{label} 当前总集数 {data.current_total_episode}")
        volatility = self.get("volatility")
        if volatility:
            subscribe_oper = self.get("subscribe_oper")
            subscribe = subscribe_oper.get(data.subscribe_id) if (
                subscribe_oper and data.subscribe_id
            ) else None
            record_kwargs = {
                "total": data.current_total_episode,
                "subscribe_id": data.subscribe_id,
            }
            if subscribe is not None:
                record_kwargs["subscribe"] = subscribe
            volatility.record(**record_kwargs)
        site_refresh = self.get("site_refresh")
        if site_refresh:
            site_refresh.handle_refresh(data)
        pending_refresh = self.get("pending_refresh")
        if pending_refresh:
            pending_refresh.handle_refresh(data)

    def on_subscribe_added(self, event):
        """SubscribeAdded → 回填下载事实后委托 lifecycle 处理新增态状态流转。"""
        data = event.event_data
        if not isinstance(data, dict):
            return
        subscribe_id = data.get("subscribe_id")
        if not subscribe_id:
            return
        subscribe_oper = self.get("subscribe_oper")
        subscribe = subscribe_oper.get(subscribe_id) if subscribe_oper else None
        if not subscribe:
            return
        detail(f"订阅新增事件：{format_subscribe(subscribe)}(id={subscribe_id})")

        priority = self.get("priority_manager")
        if (
            subscribe.best_version
            and self.get("backfill_enabled")
            and priority
            and priority.can_backfill(subscribe)
        ):
            detect = self.get("detect_backfill_episodes_fn") or self.get("detect_existing_episodes_fn")
            if detect:
                episodes = detect(subscribe)
                if episodes:
                    logger.info(f"订阅新增：{format_subscribe(subscribe)} 分集洗版订阅回填已下载集 {episodes}")
                    priority.backfill_existing(
                        subscribe, episodes, scene=self._format_backfill_scene("plugin_backfill")
                    )

        mediainfo_from_dict = self.get("mediainfo_from_dict")
        mediainfo = mediainfo_from_dict(data.get("mediainfo")) if mediainfo_from_dict else None
        if not mediainfo:
            detail(f"订阅新增：{format_subscribe(subscribe)} 媒体信息缺失，跳过播出暂停/待定")
            return

        lifecycle = self.get("lifecycle")
        if lifecycle:
            lifecycle.handle_subscribe_added(subscribe, mediainfo)

    def on_subscribe_deleted(self, event):
        """SubscribeDeleted → 清理该订阅关联的全部任务数据（订阅任务 + 名下种子任务）。"""
        data = event.event_data
        subscribe_id = data.get("subscribe_id") if isinstance(data, dict) else None
        subscribe_info = data.get("subscribe_info") if isinstance(data, dict) else None
        task_manager = self.get("task_manager")
        if subscribe_id and task_manager:
            detail(f"订阅删除事件：清理 {self._format_subscribe_label(subscribe_id, subscribe_info)} 关联任务数据")
            task_manager.clear_tasks(subscribe_id)

    def on_subscribe_modified(self, event):
        """SubscribeModified → 状态变更维护暂停归属 + 分集洗版下载事实回填。

        state 变化时维护插件侧暂停记录；普通订阅首次切成洗版时，
        把媒体库已有集交给主程序 backfill 合同，避免已在库的集被重新洗版。
        """
        data = event.event_data
        if not isinstance(data, dict):
            return
        subscribe_id = data.get("subscribe_id")
        subscribe_info = data.get("subscribe_info") or {}
        old_info = data.get("old_subscribe_info") or {}
        if not subscribe_id:
            return
        fields = data.get("fields")
        different_keys = set(fields) if isinstance(fields, list) else {
            key for key in subscribe_info.keys() & old_info.keys()
            if subscribe_info[key] != old_info[key]
        }
        subscribe_oper = self.get("subscribe_oper")
        subscribe = subscribe_oper.get(subscribe_id) if subscribe_oper else None
        if not subscribe:
            return

        if "state" in different_keys:
            lifecycle = self.get("lifecycle")
            if lifecycle:
                old_state = old_info.get("state")
                new_state = subscribe_info.get("state", subscribe.state)
                lifecycle.handle_subscribe_modified_state_change(
                    subscribe, old_state=old_state, new_state=new_state
                )

        # 只在普通订阅首次切成洗版时回填；插件后续写进度字段也会触发修改事件，不能重复回填。
        if ("best_version" in different_keys
                and subscribe_info.get("best_version")
                and not old_info.get("best_version")
                and self.get("backfill_enabled")):
            priority = self.get("priority_manager")
            detect = self.get("detect_backfill_episodes_fn") or self.get("detect_existing_episodes_fn")
            if priority and detect and priority.can_backfill(subscribe):
                episodes = detect(subscribe)
                if episodes:
                    logger.info(f"订阅修改：{format_subscribe(subscribe)} 普通转洗版，回填已下载集 {episodes}")
                    priority.backfill_existing(
                        subscribe, episodes, scene=self._format_backfill_scene("plugin_backfill")
                    )

        reset_fields = {"note", "lack_episode", "current_priority", "episode_priority", "state"}
        if (
                data.get("scene") == "reset"
                and different_keys & reset_fields
                and subscribe_id not in self._reset_backfilling_ids
                and self.get("backfill_enabled")):
            priority = self.get("priority_manager")
            detect = self.get("detect_backfill_episodes_fn") or self.get("detect_existing_episodes_fn")
            if priority and detect and priority.can_backfill(subscribe):
                episodes = detect(subscribe)
                if episodes:
                    logger.info(f"订阅重置：{format_subscribe(subscribe)} 分集洗版订阅回填已下载集 {episodes}")
                    self._reset_backfilling_ids.add(subscribe_id)
                    try:
                        priority.backfill_existing(
                            subscribe, episodes, scene=self._format_backfill_scene("reset_backfill")
                        )
                    finally:
                        self._reset_backfilling_ids.discard(subscribe_id)

    def on_subscribe_complete(self, event):
        """SubscribeComplete → 清理任务数据 + H 快照 + 自动洗版创建。

        从 event.event_data（dict）取 subscribe_id / subscribe_info / mediainfo；快照所需的订阅对象优先查库，
        查不到（完成后已删等）退回用 subscribe_info 重建，避免把整个 event_data 误当订阅。
        自动洗版创建由洗版编排在开关开启时新建洗版订阅。
        """
        data = event.event_data
        if not isinstance(data, dict):
            return
        subscribe_id = data.get("subscribe_id")
        subscribe_info = data.get("subscribe_info") or {}
        subscribe_oper = self.get("subscribe_oper")
        subscribe = subscribe_oper.get(subscribe_id) if (subscribe_oper and subscribe_id) else None
        if subscribe is None and subscribe_info:
            subscribe = SimpleNamespace(**subscribe_info)
        detail(f"订阅完成事件：{format_subscribe_label(subscribe, subscribe_id)}")

        mediainfo_from_dict = self.get("mediainfo_from_dict")
        mediainfo = None
        if mediainfo_from_dict:
            try:
                mediainfo = mediainfo_from_dict(data.get("mediainfo"))
            except Exception:
                logger.warning(
                    f"订阅完成事件：{format_subscribe_label(subscribe, subscribe_id)} "
                    "媒体信息解析失败，按无媒体信息继续保存快照并清理任务"
                )

        verifier = self.get("verifier")
        if subscribe and verifier:
            verifier.snapshot(subscribe=subscribe, mediainfo=mediainfo, scope=None)

        task_manager = self.get("task_manager")
        if subscribe_id and task_manager:
            task_manager.clear_tasks(subscribe_id)

        if not subscribe:
            return

        # 自动洗版创建（按开关；mediainfo 由事件重建，洗版编排判断是否新建洗版订阅）
        orchestrator = self.get("orchestrator")
        if orchestrator and mediainfo:
            detail(f"订阅完成：{format_subscribe(subscribe)} 检查是否需要自动创建洗版订阅")
            orchestrator.start_best_version(subscribe, mediainfo)

    def on_transfer_intercept(self, event):
        """TransferIntercept → 订阅清理目标文件删除。"""
        subscription_cleanup = self.get("subscription_cleanup")
        if subscription_cleanup and subscription_cleanup.handle_history_clear(event):
            detail("整理拦截事件：已完成订阅清理记录处理")

    def on_resource_selection(self, event):
        """ResourceSelection → 洗版下载串行控制 + 识别增强 + 剔除近期删除资源防重选。

        洗版存在下载待定时不再选择其他资源；分集洗版只挡住覆盖待定集的候选，
        待定集未知时保守全挡，避免同集多版本并发下载产生覆盖竞态。
        """
        data = _event_data(event)
        if not data:
            return
        contexts = data.contexts or []
        if not contexts:
            return
        if data.updated and data.updated_contexts is not None:
            base = list(data.updated_contexts)
        else:
            base = list(contexts)
        kept = base
        changed = False

        serial_input_count = len(kept)
        serial = self._filter_pending_serial(data, kept)
        if serial is not None and len(serial) != len(kept):
            kept, changed = serial, True
        stage_counts = [{"stage": "wash_serial", "input": serial_input_count, "output": len(kept)}]

        recognition_guard = self.get("recognition_guard")
        recognition_ran = False
        if recognition_guard:
            subscribe_oper = self.get("subscribe_oper")
            _, subscribe = subscribe_from_source(data.origin, subscribe_oper)
            if subscribe:
                guarded = recognition_guard.filter(
                    kept,
                    subscribe=subscribe,
                    event_data=data,
                    selection_original_count=len(contexts),
                    stage_counts=stage_counts,
                )
                recognition_ran = True
                if guarded is not None:
                    if guarded != kept:
                        kept, changed = guarded, True
                    else:
                        kept = guarded

        delete_input_count = len(kept)
        if self.get("skip_deletion"):
            deletes_store = self.get("deletes_store")
            if deletes_store:
                deduped = [ctx for ctx in kept if not self._is_deleted_resource(ctx, deletes_store)]
                if len(deduped) != len(kept):
                    kept, changed = deduped, True
        stage_counts.append({"stage": "delete_fingerprint", "input": delete_input_count, "output": len(kept)})
        if recognition_ran:
            recognition_guard.finalize_batch(final_count=len(kept), stage_counts=stage_counts)
            notify_fn = self.get("notify_fn")
            payload = recognition_guard.notification_payload(subscribe) if notify_fn else None
            if payload:
                title, text = payload
                notify_fn(title, text=text, diagnostic=True)

        if changed:
            detail(
                f"ResourceSelection：候选从 {len(base)} 个减少到 {len(kept)} 个"
                "（洗版下载串行控制 + 识别增强 + 删除指纹防重）"
            )
            data.updated = True
            data.updated_contexts = kept
            data.source = "订阅助手（增强版）"

    def _filter_pending_serial(self, data, contexts):
        """洗版订阅有下载待定时，根据洗版模式过滤后续候选。

        洗版整体串行，分集洗版按集串行；非洗版、无待定或无任务管理器时返回 None。
        """
        task_manager = self.get("task_manager")
        if not self.get("pending_download_enabled"):
            return None
        if not task_manager:
            return None
        subscribe_oper = self.get("subscribe_oper")
        _, subscribe = subscribe_from_source(data.origin, subscribe_oper)
        if not subscribe or not subscribe.best_version:
            return None
        sid = subscribe.id
        pending = (task_manager.read("subscribes") or {}).get(str(sid), {}).get("download_pending", {})
        if not pending:
            return None
        if is_full_best_version_subscribe(subscribe):
            return []
        torrents = task_manager.read("torrents") or {}
        pending_eps, unknown = set(), False
        for torrent_hash in pending:
            eps = (torrents.get(torrent_hash) or {}).get("episodes")
            if eps:
                pending_eps.update(self._normalize_episodes(eps))
            else:
                unknown = True
        if unknown:
            return []  # 待定集无法确定时保守全挡，避免同集多版本绕过串行造成覆盖竞态。
        kept = []
        for ctx in contexts:
            ctx_eps = set(self._context_episodes(ctx))
            if ctx_eps and (ctx_eps & pending_eps):
                continue
            kept.append(ctx)
        return kept

    @staticmethod
    def _is_deleted_resource(ctx, deletes_store) -> bool:
        """判断候选资源是否命中删除指纹（enclosure/page_url）。"""
        torrent_info = getattr(ctx, "torrent_info", None)
        if not torrent_info:
            return False
        return deletes_store.match(
            enclosure=getattr(torrent_info, "enclosure", None),
            page_url=getattr(torrent_info, "page_url", None))

    def on_resource_download(self, event):
        """ResourceDownload → 订阅清理 + 下载待定 + 按种子记录优先级基线。

        ResourceDownload 阶段尚无 hash，先写无 hash 待定以覆盖 DownloadAdded 前的完成检查空窗；
        洗版优先级基线按 enclosure 归属，便于删种后按集回滚并隔离并行洗版。
        """
        data = _event_data(event)
        if not data or data.cancel:
            return
        subscribe_oper = self.get("subscribe_oper")
        _, subscribe = subscribe_from_source(data.origin, subscribe_oper)
        if not subscribe:
            return
        # context.torrent_info 来自主程序事件，可能为空或对象结构不完整。
        torrent_info = getattr(data.context, "torrent_info", None)
        monitor = self.get("download_monitor")
        if monitor and self.get("pending_download_enabled") and torrent_info:
            detail(
                f"ResourceDownload：{format_subscribe(subscribe)} 写入无 hash 下载待定，"
                "等待 DownloadAdded 确认"
            )
            monitor.mark_download_started(
                subscribe,
                episodes=self._normalize_episodes(data.episodes),
                downloader=getattr(data, "downloader", None),
                enclosure=getattr(torrent_info, "enclosure", None),
                page_url=getattr(torrent_info, "page_url", None),
                title=getattr(torrent_info, "title", None),
                description=getattr(torrent_info, "description", None),
            )

        subscription_cleanup = self.get("subscription_cleanup")
        if subscription_cleanup:
            detail(
                f"ResourceDownload：{format_subscribe(subscribe)} 执行订阅清理前置检查"
            )
            subscription_cleanup.handle_resource_download_history_clear(
                subscribe,
                context=data.context,
                episodes=data.episodes,
            )
        priority = self.get("priority_manager")
        if priority and subscribe.best_version and torrent_info:
            enclosure = getattr(torrent_info, "enclosure", None)
            if enclosure:
                detail(
                    f"ResourceDownload：{format_subscribe(subscribe)} "
                    f"{self._best_version_mode_label(subscribe)}记录按种子优先级基线"
                )
                priority.capture_torrent_baseline(
                    subscribe, enclosure,
                    self._normalize_episodes(data.episodes),
                    contributed_priority=getattr(torrent_info, "pri_order", 0),
                    target_episodes=self._subscribe_target_episodes(subscribe),
                )

    def on_download_added(self, event):
        """DownloadAdded → 登记种子监控数据，并在暂停订阅命中下载时恢复订阅。"""
        data = event.event_data
        if not isinstance(data, dict):
            return
        subscribe_oper = self.get("subscribe_oper")
        _, subscribe = subscribe_from_source(data.get("source"), subscribe_oper)
        if not subscribe:
            return
        monitor = self.get("download_monitor")
        if monitor and (self.get("pending_download_enabled") or self.get("download_monitor_enabled")):
            detail(f"DownloadAdded：{format_subscribe(subscribe)} 登记种子监控 hash={data.get('hash')}")
            torrent_info = getattr(data.get("context"), "torrent_info", None)
            monitor.on_download(
                subscribe.id,
                data.get("hash"),
                episodes=data.get("episodes"),
                downloader=data.get("downloader"),
                enclosure=getattr(torrent_info, "enclosure", None),
                page_url=getattr(torrent_info, "page_url", None),
                title=getattr(torrent_info, "title", None),
                description=getattr(torrent_info, "description", None),
            )
        lifecycle = self.get("lifecycle")
        result = lifecycle.handle_download_added_for_subscribe(subscribe) if lifecycle else None
        if result and result.changed:
            self._notify_download_resume(subscribe, result.reason)

    def _notify_download_resume(self, subscribe, reason: str):
        """发送下载命中恢复暂停订阅通知；实际推送仍由全局通知开关控制。"""
        notify_fn = self.get("notify_fn")
        if not notify_fn:
            return
        external = reason == "external"
        title = (
            f"{format_subscribe(subscribe)} 检测到下载任务，已恢复外部暂停订阅"
            if external else
            f"{format_subscribe(subscribe)} 检测到下载任务，已恢复暂停订阅"
        )
        notification_image_fn = self.get("notification_image_fn")
        notify_fn(
            title,
            reason=self._pause_reason_label(reason),
            action="已恢复为订阅中",
            follow_up=(
                "用户再次手动暂停仍会立即生效"
                if external else
                "48小时内不会因同一原因再次自动暂停"
            ),
            image=notification_image_fn(subscribe) if notification_image_fn else None,
        )

    @staticmethod
    def _pause_reason_label(reason: str) -> str:
        """把内部暂停原因转换为通知可读文本。"""
        return {
            "no_download": "无下载暂停",
            "pre_air": "上映/开播暂停",
            "airing_gap": "播出间隔暂停",
            "auto_user": "用户名暂停",
            "external": "外部暂停",
        }.get(reason, f"{reason} 暂停")

    def on_transfer_complete(self, event):
        """TransferComplete → 清下载待定 + 移动模式同步清理种子任务记录。

        订阅归属需在清理 torrents 任务前反查；移动模式下源已转走，只同步清理插件任务记录，
        不在此处调用下载器删除 API。
        """
        data = event.event_data
        if not isinstance(data, dict):
            return
        download_hash = data.get("download_hash")
        if not download_hash:
            return
        task_manager = self.get("task_manager")

        # 先查下载任务归属，再清下载待定，避免任务记录删掉后找不到订阅。
        subscribe_id = None
        if task_manager:
            torrent_task = (task_manager.read("torrents") or {}).get(download_hash)
            if torrent_task:
                subscribe_id = torrent_task.get("subscribe_id")
        monitor = self.get("download_monitor")
        if monitor and subscribe_id:
            detail(
                f"TransferComplete：{self._format_subscribe_label(subscribe_id)} "
                f"下载已入库，解除 hash={download_hash} 的下载待定"
            )
            monitor.clear_download_pending(subscribe_id, download_hash)

        # 移动模式下下载源已转走，插件不再继续检查该下载任务。
        transfer_info = data.get("transferinfo")
        if transfer_info and transfer_info.transfer_type == "move" and task_manager:
            detail(f"TransferComplete：移动模式清理已完成下载任务 hash={download_hash}")
            task_manager.clean_torrent_tasks(download_hash)
        lifecycle = self.get("lifecycle")
        if lifecycle:
            lifecycle.handle_library_updated(subscribe_id)
        self._convert_episode_best_version_to_full_if_ready(subscribe_id)

    def _convert_episode_best_version_to_full_if_ready(self, subscribe_id):
        """整理完成后补偿检查当前分集洗版订阅，避免目标集已齐全还要等下一次洗版巡检。"""
        if not subscribe_id or not self.get("best_version_episode_to_full"):
            return
        subscribe_oper = self.get("subscribe_oper")
        converter = self.get("converter")
        detect_missing = self.get("detect_missing_episodes_fn")
        resolve_missing = self.get("resolve_missing_fn")
        recognize = self.get("recognize_mediainfo_fn")
        if not (subscribe_oper and converter and recognize):
            return
        subscribe = subscribe_oper.get(subscribe_id)
        if not subscribe or not is_tv_episode_best_version_subscribe(subscribe):
            return
        mediainfo = recognize(subscribe)
        if not mediainfo:
            return
        if resolve_missing:
            satisfied, _ = resolve_missing(
                subscribe=subscribe,
                mediainfo=mediainfo,
                best_version_accept_downloaded=True,
            )
        else:
            if not detect_missing or (subscribe.lack_episode or 0) > 0:
                return
            satisfied = not detect_missing(subscribe)
        if not satisfied:
            return
        detail(f"TransferComplete：{format_subscribe(subscribe)} 分集洗版目标满足，立即转为全集洗版")
        converter.convert_to_full(subscribe, mediainfo)

    @staticmethod
    def _best_version_mode_label(subscribe) -> str:
        """按订阅实际洗版形态返回日志标签。"""
        if is_full_best_version_subscribe(subscribe):
            return "洗版"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "分集洗版"
        return ""

    def on_plugin_action(self, event):
        """PluginAction → /subscribe_toggle 切换订阅启用(R)/禁用(S)状态。

        关键字为纯数字按订阅 id 匹配、否则按名称匹配；命中唯一则切换并通知，命中多个则回列表让用户带 id 重试。
        """
        data = event.event_data
        if not isinstance(data, dict) or data.get("action") != "subscribe_toggle":
            return
        subscribe_oper = self.get("subscribe_oper")
        if not subscribe_oper:
            return
        post_message = self.get("post_message")
        channel, userid, source = data.get("channel"), data.get("user"), data.get("source")

        def notify(title, text=None):
            if post_message:
                post_message(channel=channel, title=title, text=text, userid=userid, source=source)

        keyword = (data.get("arg_str") or "").strip()
        if not keyword:
            notify("未能获取到订阅信息")
            return
        subscribes = subscribe_oper.list() or []
        if keyword.isdigit():
            matched = [s for s in subscribes if s.id == int(keyword)]
        else:
            matched = [s for s in subscribes if s.name == keyword]
        if not matched:
            notify("没有找到符合要求的订阅")
            return
        if len(matched) == 1:
            subscribe = matched[0]
            lifecycle = self.get("lifecycle")
            if not lifecycle:
                logger.warning(f"订阅切换命令：{format_subscribe(subscribe)} 生命周期未就绪，跳过状态切换")
                notify("订阅生命周期未就绪，无法切换订阅状态")
                return
            result = lifecycle.toggle_subscribe_by_user_command(subscribe)
            new_state = result.state or ("S" if subscribe.state != "S" else "R")
            logger.info(f"订阅切换命令：{format_subscribe(subscribe)} 状态切换为 {new_state}")
            notify(f"{format_subscribe(subscribe)} 已{'禁用' if new_state == 'S' else '启用'}")
        else:
            lines = [f"{s.id}. {s.name}" for s in matched]
            notify("回复对应指令切换订阅状态：/subscribe_toggle [id]", text="\n".join(lines))

    @staticmethod
    def _normalize_episodes(episodes):
        """规整集数为 int 列表，过滤无法转 int 的值。"""
        result = []
        for ep in episodes or []:
            try:
                result.append(int(ep))
            except (TypeError, ValueError):
                continue
        return result

    @classmethod
    def _context_episodes(cls, context):
        """从 ResourceSelection 候选读取集数，兼容主程序 Context 与轻量测试替身。"""
        direct = cls._normalize_episodes(getattr(context, "episodes", None))
        if direct:
            return direct
        torrent = getattr(context, "torrent_info", None)
        torrent_eps = cls._normalize_episodes(getattr(torrent, "episode_list", None))
        if torrent_eps:
            return torrent_eps
        meta = getattr(context, "meta_info", None)
        meta_eps = cls._normalize_episodes(getattr(meta, "episode_list", None))
        if meta_eps:
            return meta_eps
        begin = getattr(meta, "begin_episode", None)
        end = getattr(meta, "end_episode", None)
        try:
            begin = int(begin) if begin is not None else None
            end = int(end) if end is not None else begin
        except (TypeError, ValueError):
            return []
        if begin is not None and end is not None and end >= begin:
            return list(range(begin, end + 1))
        return []

    @staticmethod
    def _subscribe_target_episodes(subscribe):
        """订阅目标集范围 start_episode..total_episode，供整季包 episodes 为空时的基线回退。"""
        total = subscribe.total_episode or 0
        if not total:
            return []
        start = subscribe.start_episode or 1
        return list(range(start, total + 1))

    def _get_subscribe(self, event):
        """从事件取 subscribe：优先 wrapper 直属，回退 event_data.subscribe。"""
        return getattr(event, "subscribe", None) or getattr(event.event_data, "subscribe", None)

    def _get_subscribe_from_event_data(self, event):
        """取 event_data 作 subscribe：dict 形态包成 SimpleNamespace 以统一属性访问。"""
        event_data = event.event_data
        if isinstance(event_data, dict):
            from types import SimpleNamespace
            return SimpleNamespace(**event_data)
        return event_data
