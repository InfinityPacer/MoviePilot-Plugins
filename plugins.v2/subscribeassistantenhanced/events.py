"""事件薄代理——按域 enabled 开关按需注册，委托到对应模块。

12 个事件处理器：
- SubscribeCompletionCheck → guard
- SubscribeEpisodesRefresh → volatility.record (先) + pending.refresh (后)
- SubscribeAdded → best_version + priority.backfill + pause.auto_pause_user
- SubscribeDeleted → task_manager.cleanup
- SubscribeModified → task_manager.reset_on_modify
- SubscribeComplete → verifier.snapshot + best_version
- TransferIntercept → best_version.history_clear
- ResourceSelection → 洗版串行与删除指纹过滤（识别增强保持下线）
- ResourceDownload → monitor.mark_pending
- DownloadAdded → monitor.on_download
- TransferComplete → monitor.on_transfer + best_version.on_transfer
- PluginAction → toggle_subscribe_state
"""
from types import SimpleNamespace

from app.log import logger
from app.core.context import MediaInfo
from app.schemas.event import SubscribeEpisodesRefreshEventData

from .engine.signals import last_aired_episode
from .shared.log import detail
from .shared.subscribe import format_subscribe, format_subscribe_label, subscribe_from_source
from .shared.update import update_subscribe


def _event_data(event):
    """取事件 payload（主程序固定放在 event.event_data）；链式事件的业务字段不从 wrapper 直读。"""
    return event.event_data


class EventProxy:
    """事件代理，持有各域模块引用，按 enabled 注册。"""

    def __init__(self, skip_deletion=True, backfill_enabled=True,
                 pending_download_enabled=True, **modules):
        """保存事件处理依赖；删除指纹过滤和洗版回填默认开启以兼容直接构造场景。"""
        modules["skip_deletion"] = skip_deletion
        modules["backfill_enabled"] = backfill_enabled
        modules["pending_download_enabled"] = pending_download_enabled
        self._modules = modules

    def get(self, name):
        return self._modules.get(name)

    def _format_subscribe_label(self, subscribe_id):
        """按订阅 ID 生成日志标签；查库成功时带名称/季号/ID，失败时保留 ID 兜底。"""
        if subscribe_id is None:
            return "未知订阅"
        subscribe_oper = self.get("subscribe_oper")
        subscribe = subscribe_oper.get(subscribe_id) if subscribe_oper else None
        return format_subscribe_label(subscribe, subscribe_id)

    @staticmethod
    def _format_episodes_refresh_label(data: SubscribeEpisodesRefreshEventData) -> str | None:
        """格式化集数刷新事件来源；创建场景无订阅 ID 时用媒体信息兜底。"""
        subscribe_id = data.subscribe_id
        if subscribe_id is not None:
            return None
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
        if tmdbid:
            markers.append(f"tmdbid={tmdbid}")
        if data.scene:
            markers.append(f"scene={data.scene}")
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
        """EpisodesRefresh → F record (先) + pending refresh (后)。

        链式事件：业务字段在 event.event_data（主程序只回读该数据类），wrapper 上没有这些字段。
        """
        data: SubscribeEpisodesRefreshEventData = _event_data(event)
        if data is None:
            return
        label = self._format_episodes_refresh_label(data) or self._format_subscribe_label(data.subscribe_id)
        detail(f"集数刷新事件：{label} 当前总集数 {data.current_total_episode}")
        volatility = self.get("volatility")
        if volatility:
            volatility.record(
                total=data.current_total_episode,
                subscribe_id=data.subscribe_id,
            )
        pending_refresh = self.get("pending_refresh")
        if pending_refresh:
            pending_refresh.handle_refresh(data)

    def on_subscribe_added(self, event):
        """SubscribeAdded → 用户名自动暂停 + 上映前暂停 + 电视剧待定 / 播出暂停。

        洗版订阅不做播出暂停/待定。普通订阅先检查上映窗口，电视剧再按 TMDB 集数和播出间隔判定。
        """
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

        pause_manager = self.get("pause_manager")
        if pause_manager:
            pause_manager.check_auto_pause_for_user(subscribe)

        # 洗版订阅不做播出暂停/待定
        if subscribe.best_version:
            detail(f"订阅新增：{format_subscribe(subscribe)} 为洗版订阅，跳过播出暂停/待定")
            return

        mediainfo_from_dict = self.get("mediainfo_from_dict")
        mediainfo = mediainfo_from_dict(data.get("mediainfo")) if mediainfo_from_dict else None
        if not mediainfo:
            detail(f"订阅新增：{format_subscribe(subscribe)} 媒体信息缺失，跳过播出暂停/待定")
            return

        # 上映前暂停同时适用于电影和电视剧，必须先于电视剧专属流程判定
        airing = self.get("airing_checker")
        if airing and pause_manager:
            record = airing.check_pre_air(subscribe, mediainfo)
            if record:
                logger.info(f"订阅新增：{format_subscribe(subscribe)} 满足上映前暂停条件，置为禁用")
                pause_manager.pause(subscribe, record)
                return

        is_tv = self.get("is_tv_fn")
        if is_tv and not is_tv(mediainfo):
            return

        tmdb_episodes_fn = self.get("tmdb_episodes_fn")
        episodes = tmdb_episodes_fn(
            subscribe.tmdbid,
            subscribe.season,
            episode_group=subscribe.episode_group,
        ) if tmdb_episodes_fn else []

        # TV 待定优先于播出暂停：满足待定条件即进入待定并跳过播出暂停。
        pending_judge = self.get("pending_judge")
        evaluate = self.get("evaluate_fn")
        if pending_judge:
            signal = evaluate(subscribe, mediainfo) if evaluate else None
            should, reason = pending_judge.should_enter_pending(subscribe, mediainfo, episodes, signal)
            if should:
                logger.info(f"订阅新增：{format_subscribe(subscribe)} 判定进入待定（{reason}）")
                pending_judge.mark_pending(subscribe, source="pending_judge", reason=reason)
                return

        # 新增订阅尚未经过媒体库/下载状态沉淀，只处理明确的下一集断档，避免历史季全缺时被最后已播日期直接暂停。
        if airing and pause_manager:
            record = airing.check(
                subscribe, mediainfo,
                next_episode=mediainfo.next_episode_to_air,
                latest_episode=None,
            )
            if record:
                logger.info(f"订阅新增：{format_subscribe(subscribe)} 满足播出间隔暂停条件，置为禁用")
                pause_manager.pause(subscribe, record)

    def on_subscribe_deleted(self, event):
        """SubscribeDeleted → 清理该订阅关联的全部任务数据（订阅任务 + 名下种子任务）。"""
        data = event.event_data
        subscribe_id = data.get("subscribe_id") if isinstance(data, dict) else None
        task_manager = self.get("task_manager")
        if subscribe_id and task_manager:
            detail(f"订阅删除事件：清理 {self._format_subscribe_label(subscribe_id)} 关联任务数据")
            task_manager.clear_tasks(subscribe_id)

    def on_subscribe_modified(self, event):
        """SubscribeModified → 状态变更重置暂停跟踪 + 普通转洗版按集优先级回填。

        state 变化时重置插件侧暂停记录；普通转洗版边沿（best_version 由假转真）
        把媒体库已有集回填为 priority=100，避免已在库的集被重新洗版。
        """
        data = event.event_data
        if not isinstance(data, dict):
            return
        subscribe_id = data.get("subscribe_id")
        subscribe_info = data.get("subscribe_info") or {}
        old_info = data.get("old_subscribe_info") or {}
        if not subscribe_id:
            return
        different_keys = {
            key for key in subscribe_info.keys() & old_info.keys()
            if subscribe_info[key] != old_info[key]
        }
        subscribe_oper = self.get("subscribe_oper")
        subscribe = subscribe_oper.get(subscribe_id) if subscribe_oper else None
        if not subscribe:
            return

        if "state" in different_keys:
            pause_manager = self.get("pause_manager")
            if pause_manager:
                detail(f"订阅修改事件：{format_subscribe(subscribe)} 状态已变更，清理插件暂停记录")
                pause_manager.clear_pause_record(subscribe)

        # 仅在旧假新真的转洗版边沿回填，避免内部 update 反复触发
        if ("best_version" in different_keys
                and subscribe_info.get("best_version")
                and not old_info.get("best_version")
                and self.get("backfill_enabled")):
            priority = self.get("priority_manager")
            detect = self.get("detect_existing_episodes_fn")
            if priority and detect:
                existing = detect(subscribe)
                if existing:
                    logger.info(f"订阅修改：{format_subscribe(subscribe)} 普通转洗版，回填在库集 {existing}")
                    priority.backfill_existing(subscribe, existing)

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
        task_manager = self.get("task_manager")
        if subscribe_id and task_manager:
            task_manager.clear_tasks(subscribe_id)

        if not subscribe:
            return

        verifier = self.get("verifier")
        if verifier:
            verifier.snapshot(subscribe=subscribe, mediainfo=None, scope=None)

        # 自动洗版创建（按开关；mediainfo 由事件重建，洗版编排判断是否新建洗版订阅）
        orchestrator = self.get("orchestrator")
        mediainfo_from_dict = self.get("mediainfo_from_dict")
        if orchestrator and mediainfo_from_dict:
            mediainfo = mediainfo_from_dict(data.get("mediainfo"))
            if mediainfo:
                detail(f"订阅完成：{format_subscribe(subscribe)} 检查是否需要自动创建洗版订阅")
                orchestrator.start_best_version(subscribe, mediainfo)

    def on_transfer_intercept(self, event):
        """TransferIntercept → 洗版历史清理。"""
        orchestrator = self.get("orchestrator")
        if orchestrator and orchestrator.handle_history_clear(event):
            detail("整理拦截事件：已清理本次洗版对应的旧媒体库文件")

    def on_resource_selection(self, event):
        """ResourceSelection → 洗版待定按集串行 + 剔除近期删除资源防重选。

        洗版订阅存在下载待定时挡住覆盖待定集的候选，其余集仍可并行；
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

        serial = self._filter_pending_serial(data, kept)
        if serial is not None and len(serial) != len(kept):
            kept, changed = serial, True

        if self.get("skip_deletion"):
            deletes_store = self.get("deletes_store")
            if deletes_store:
                deduped = [ctx for ctx in kept if not self._is_deleted_resource(ctx, deletes_store)]
                if len(deduped) != len(kept):
                    kept, changed = deduped, True

        if changed:
            detail(
                f"ResourceSelection：候选从 {len(base)} 个减少到 {len(kept)} 个"
                "（洗版按集串行 + 删除指纹防重）"
            )
            data.updated = True
            data.updated_contexts = kept
            data.source = "订阅助手（增强版）"

    def _filter_pending_serial(self, data, contexts):
        """洗版订阅有下载待定时，剔除覆盖待定集的候选，实现按集串行。

        返回过滤后列表；非洗版、无待定或无任务管理器时返回 None，表示本规则不参与。
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
            ctx_eps = set(self._normalize_episodes(
                getattr(ctx, "episodes", None) or getattr(getattr(ctx, "torrent_info", None), "episode_list", None)))
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
        """ResourceDownload → 下载待定 + 洗版历史清理 + 按种子记录优先级基线。

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
            )

        orchestrator = self.get("orchestrator")
        if orchestrator and subscribe.best_version:
            detail(f"ResourceDownload：{format_subscribe(subscribe)} 执行洗版历史清理前置检查")
            orchestrator.handle_resource_download_history_clear(
                subscribe,
                context=data.context,
                episodes=data.episodes,
            )
        priority = self.get("priority_manager")
        if priority and subscribe.best_version and torrent_info:
            enclosure = getattr(torrent_info, "enclosure", None)
            if enclosure:
                detail(f"ResourceDownload：{format_subscribe(subscribe)} 记录按种子洗版优先级基线")
                priority.capture_torrent_baseline(
                    subscribe, enclosure,
                    self._normalize_episodes(data.episodes),
                    contributed_priority=getattr(torrent_info, "pri_order", 0),
                    target_episodes=self._subscribe_target_episodes(subscribe),
                )

    def on_download_added(self, event):
        """DownloadAdded → 登记种子监控数据，并为无 hash 下载待定补齐真实 hash。

        下载添加不在此处恢复暂停；暂停恢复仅由元数据检查的上映条件双向判定负责，
        避免下载落地即把上映暂停或标记暂停误清掉。
        """
        data = event.event_data
        if not isinstance(data, dict):
            return
        subscribe_oper = self.get("subscribe_oper")
        _, subscribe = subscribe_from_source(data.get("source"), subscribe_oper)
        if not subscribe:
            return
        monitor = self.get("download_monitor")
        if monitor:
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
            )

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
            new_state = "S" if subscribe.state != "S" else "R"
            logger.info(f"订阅切换命令：{format_subscribe(subscribe)} 状态切换为 {new_state}")
            update_subscribe(subscribe_oper, subscribe.id, {"state": new_state})
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
