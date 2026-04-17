from functools import wraps
from typing import Any, Dict, List, Optional, Set, Tuple

from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler


class ServiceManager(_PluginBase):
    # 插件名称
    plugin_name = "服务管理"
    # 插件描述
    plugin_desc = "实现自定义服务管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/servicemanager.png"
    # 插件版本
    plugin_version = "1.3"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "servicemanager_"
    # 加载顺序
    plugin_order = 29
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    # 是否开启
    _enabled = False
    # 站点数据刷新（cron 表达式）
    _sitedata_refresh = ""
    # 订阅搜索补全（cron 表达式）
    _subscribe_search = ""
    # 缓存清理（cron 表达式）
    _clear_cache = ""
    # 壁纸缓存（cron 表达式）
    _random_wallpager = ""
    # 订阅元数据更新（小时）
    _subscribe_tmdb = ""
    # 缓存系统任务模板，确保实现跟随主项目
    _system_job_templates: Dict[str, Dict[str, Any]] = {}
    # 缓存系统调度模板，用于取消接管时轻量恢复默认服务
    _system_schedule_templates: Dict[str, Dict[str, Any]] = {}
    # 当前主项目默认不启用调度的系统任务
    _absent_system_schedules: Set[str] = set()
    # 任务ID映射：系统任务ID -> 插件任务ID
    _start_redirects: Dict[str, str] = {}
    # 插件任务ID映射：插件任务ID -> 系统任务ID，用于运行中切换时同步 running 状态
    _plugin_job_aliases: Dict[str, str] = {}
    # 正在运行的托管系统任务计数：系统任务ID -> 运行实例数
    _running_redirects: Dict[str, int] = {}
    # Scheduler.start 原始方法
    _original_scheduler_start = None
    # Scheduler.init 原始方法
    _original_scheduler_init = None
    # 当前生效实例
    _active_instance = None
    # Scheduler.init 执行期上下文，用于复用主项目正在构建的系统任务模板
    _scheduler_context = None
    # 恢复默认服务的完整 init 兜底保护，避免递归重建
    _restore_init_in_progress = False

    # 可接管的系统任务
    _MANAGED_JOB_IDS = (
        "sitedata_refresh",
        "subscribe_search",
        "clear_cache",
        "random_wallpager",
        "subscribe_tmdb",
    )

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._sitedata_refresh = config.get("sitedata_refresh")
        self._subscribe_search = config.get("subscribe_search")
        self._clear_cache = config.get("clear_cache")
        self._random_wallpager = config.get("random_wallpager")
        self._subscribe_tmdb = config.get("subscribe_tmdb")

        if not self._enabled:
            self._disable_takeover(restore_system_jobs=True)
            return

        self.__class__._active_instance = self
        self._install_init_hook()
        self._install_start_hook()
        self._apply_takeover()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后插件将处于激活状态',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'sitedata_refresh',
                                            'label': '站点数据刷新',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置站点数据刷新的周期，如 0 8 * * * 表示每天 8:00',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'subscribe_search',
                                            'label': '订阅搜索补全',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置订阅搜索补全的周期，如 0 12 * * * 表示每天中午 12:00',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'clear_cache',
                                            'label': '缓存清理',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置缓存清理任务的周期，如 0 3 * * * 表示每天凌晨 3:00',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'random_wallpager',
                                            'label': '壁纸缓存',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置壁纸缓存更新的周期，如 0 6 * * * 表示每天早晨 6:00',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'subscribe_tmdb',
                                            'label': '订阅元数据更新',
                                            'type': 'number',
                                            "min": "1",
                                            'placeholder': '最低不能小于1',
                                            'hint': '设置订阅元数据更新的周期，如 1/3/6/12，最低为 1',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：启用本插件后，默认的系统服务将失效，仅以本插件设置为准'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：系统服务正在运行时，请慎重启停用，否则可能导致死锁等一系列问题'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '注意：请勿随意调整服务频率，否则可能导致站点警告、封禁等后果，相关风险请自行评估与承担'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False
        }

    def get_page(self) -> List[dict]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数,
            "func_kwargs": {} # 方法参数
        }]
        """
        if not self._enabled:
            return []

        scheduler = self.__class__._scheduler_context or self._get_scheduler_if_ready()
        if scheduler:
            self._cache_system_job_templates(scheduler)

        services = []

        if self._sitedata_refresh:
            service = self._build_service_from_system(
                job_id="sitedata_refresh",
                trigger=CronTrigger.from_crontab(self._sitedata_refresh),
            )
            if service:
                services.append(service)

        if settings.SUBSCRIBE_SEARCH and self._subscribe_search:
            service = self._build_service_from_system(
                job_id="subscribe_search",
                trigger=CronTrigger.from_crontab(self._subscribe_search),
            )
            if service:
                services.append(service)

        if self._clear_cache:
            service = self._build_service_from_system(
                job_id="clear_cache",
                trigger=CronTrigger.from_crontab(self._clear_cache),
            )
            if service:
                services.append(service)

        if self._random_wallpager:
            service = self._build_service_from_system(
                job_id="random_wallpager",
                trigger=CronTrigger.from_crontab(self._random_wallpager),
            )
            if service:
                services.append(service)

        if self._subscribe_tmdb:
            try:
                subscribe_tmdb = max(int(self._subscribe_tmdb or 1), 1)
            except (ValueError, TypeError):
                subscribe_tmdb = 1
            service = self._build_service_from_system(
                job_id="subscribe_tmdb",
                trigger="interval",
                schedule_kwargs={"hours": subscribe_tmdb},
            )
            if service:
                services.append(service)

        return services

    def stop_service(self):
        """
        退出插件
        """
        self._disable_takeover(restore_system_jobs=True)

    @staticmethod
    def clear_cache():
        """
        清理缓存
        """
        Scheduler().clear_cache()

    def _get_plugin_id(self) -> str:
        from app.core.plugin import PluginManager

        for plugin_id, plugin in PluginManager().running_plugins.items():
            if plugin is self:
                return plugin_id
        return self.__class__.__name__

    def _get_legacy_plugin_ids(self, plugin_id: str) -> List[str]:
        legacy_plugin_id = self.__class__.__name__.lower()
        if legacy_plugin_id and legacy_plugin_id != plugin_id:
            return [legacy_plugin_id]
        return []

    @classmethod
    def _get_scheduler_if_ready(cls) -> Optional[Scheduler]:
        scheduler = getattr(type(Scheduler), "_instances", {}).get(Scheduler)
        if scheduler and getattr(scheduler, "_scheduler", None):
            return scheduler
        return None

    def _get_takeover_targets(self) -> List[str]:
        targets = []
        if self._sitedata_refresh:
            targets.append("sitedata_refresh")
        if settings.SUBSCRIBE_SEARCH and self._subscribe_search:
            targets.append("subscribe_search")
        if self._clear_cache:
            targets.append("clear_cache")
        if self._random_wallpager:
            targets.append("random_wallpager")
        if self._subscribe_tmdb:
            targets.append("subscribe_tmdb")
        return targets

    def _cache_system_job_templates(self, scheduler: Scheduler):
        for job_id in self._MANAGED_JOB_IDS:
            service = scheduler._jobs.get(job_id)
            if not service or service.get("pid"):
                continue
            func = service.get("func")
            if not func:
                continue
            self._system_job_templates[job_id] = {
                "name": service.get("name") or job_id,
                "func": func,
                "kwargs": dict(service.get("kwargs") or {}),
            }

    def _cache_system_schedule_templates(self, scheduler: Scheduler, refresh: bool = False):
        if not getattr(scheduler, "_scheduler", None):
            return
        current_job_ids = set()
        for job in list(scheduler._scheduler.get_jobs()):
            job_id = job.id.split("|")[0]
            if job_id not in self._MANAGED_JOB_IDS:
                continue
            current_job_ids.add(job_id)
            self._system_schedule_templates[job_id] = {
                "trigger": job.trigger,
                "name": job.name,
                "kwargs": dict(job.kwargs or {}),
            }
            self._absent_system_schedules.discard(job_id)
        if refresh:
            for job_id in self._MANAGED_JOB_IDS:
                if job_id not in current_job_ids:
                    self._system_schedule_templates.pop(job_id, None)
                    self._absent_system_schedules.add(job_id)

    def _build_service_from_system(
        self,
        job_id: str,
        trigger: Any,
        schedule_kwargs: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        template = self._system_job_templates.get(job_id)
        if not template:
            logger.warning(f"服务管理插件：未找到系统任务模板 {job_id}，跳过接管")
            return {}
        service = {
            "id": job_id,
            "name": template.get("name") or job_id,
            "trigger": trigger,
            "func": template.get("func"),
        }
        func_kwargs = template.get("kwargs") or {}
        if func_kwargs:
            service["func_kwargs"] = func_kwargs
        if schedule_kwargs:
            service["kwargs"] = schedule_kwargs
        return service

    def _ensure_plugin_jobs(self, scheduler: Scheduler, pid: str):
        from app.core.plugin import PluginManager

        plugin_manager = PluginManager()
        running_plugins = plugin_manager.running_plugins
        registered = running_plugins.get(pid) is self
        if not registered:
            running_plugins[pid] = self
        try:
            scheduler.update_plugin_job(pid=pid)
        finally:
            if not registered and running_plugins.get(pid) is self:
                running_plugins.pop(pid, None)

    def _restore_system_jobs(self, scheduler: Scheduler, job_ids: List[str]) -> bool:
        if not getattr(scheduler, "_scheduler", None):
            return False
        restored = True
        with scheduler._lock:
            scheduler_job_ids = {job.id.split("|")[0] for job in scheduler._scheduler.get_jobs()}
            for job_id in job_ids:
                service = scheduler._jobs.get(job_id)
                if service and not service.get("pid") and job_id in scheduler_job_ids:
                    continue

                service_template = self._system_job_templates.get(job_id)
                schedule_template = self._system_schedule_templates.get(job_id)
                if not service_template:
                    logger.warning(f"服务管理插件：未找到系统服务模板 {job_id}，无法轻量恢复")
                    restored = False
                    continue
                if not schedule_template:
                    if job_id in self.__class__._absent_system_schedules:
                        scheduler._jobs[job_id] = {
                            "func": service_template["func"],
                            "name": service_template["name"],
                            "kwargs": service_template.get("kwargs") or {},
                            "running": bool(
                                (service.get("running") if service else False)
                                or self.__class__._running_redirects.get(job_id)
                            ),
                        }
                        logger.info(
                            f"服务管理插件已恢复系统服务：{service_template['name']}"
                            "（系统默认未启用调度）"
                        )
                        continue
                    logger.warning(f"服务管理插件：未找到系统调度模板 {job_id}，无法轻量恢复")
                    restored = False
                    continue

                scheduler._jobs[job_id] = {
                    "func": service_template["func"],
                    "name": service_template["name"],
                    "kwargs": service_template.get("kwargs") or {},
                    "running": bool(
                        (service.get("running") if service else False)
                        or self.__class__._running_redirects.get(job_id)
                    ),
                }
                scheduler._scheduler.add_job(
                    scheduler.start,
                    schedule_template["trigger"],
                    id=job_id,
                    name=schedule_template.get("name") or service_template["name"],
                    kwargs=schedule_template.get("kwargs") or {"job_id": job_id},
                    replace_existing=True,
                )
                logger.info(f"服务管理插件已恢复系统服务：{service_template['name']}")
        return restored

    def _remove_system_job(self, scheduler: Scheduler, job_id: str):
        if not getattr(scheduler, "_scheduler", None):
            return
        with scheduler._lock:
            self._cache_system_schedule_templates(scheduler)
            service = scheduler._jobs.get(job_id)
            if not service:
                return
            keep_running_state = bool(service.get("running"))
            if not keep_running_state:
                scheduler._jobs.pop(job_id, None)
            job_removed = False
            for job in list(scheduler._scheduler.get_jobs()):
                job_id_from_service = job.id.split("|")[0]
                if job_id != job_id_from_service:
                    continue
                try:
                    scheduler._scheduler.remove_job(job.id)
                    job_removed = True
                except Exception:
                    pass
            if job_removed:
                message = f"服务管理插件已移除系统服务：{service.get('name')}"
                if keep_running_state:
                    message = f"{message}，当前运行实例将继续执行至结束"
                logger.info(message)

    @staticmethod
    def _get_running_job_names(scheduler: Scheduler) -> List[str]:
        return [
            service.get("name") or job_id
            for job_id, service in scheduler._jobs.items()
            if service.get("running")
        ]

    def _apply_takeover(self, scheduler: Optional[Scheduler] = None):
        if not self._enabled:
            return
        scheduler = scheduler or self._get_scheduler_if_ready()
        if not scheduler:
            logger.debug("服务管理插件等待定时器初始化后接管服务")
            return
        previous_targets = set(self.__class__._start_redirects)
        refresh_schedule_templates = self.__class__._scheduler_context is scheduler
        self._cache_system_job_templates(scheduler)
        self._cache_system_schedule_templates(scheduler, refresh=refresh_schedule_templates)
        pid = self._get_plugin_id()
        takeover_targets = self._get_takeover_targets()

        for legacy_pid in self._get_legacy_plugin_ids(pid):
            scheduler.remove_plugin_job(pid=legacy_pid)

        # 复用主项目的插件服务注册逻辑；
        # 热重载时插件可能尚未写入 running_plugins，这里做短暂补位。
        self._ensure_plugin_jobs(scheduler, pid)

        dropped_targets = sorted(previous_targets - set(takeover_targets))
        if dropped_targets:
            if not self._restore_system_jobs(scheduler, dropped_targets):
                if self.__class__._restore_init_in_progress:
                    logger.warning(
                        "服务管理插件：部分系统服务无默认调度，跳过轻量恢复："
                        f"{', '.join(dropped_targets)}"
                    )
                else:
                    logger.info("服务管理插件恢复系统服务模板缺失，重新初始化定时器")
                    self.__class__._restore_init_in_progress = True
                    try:
                        scheduler.init()
                    finally:
                        self.__class__._restore_init_in_progress = False
                    return

        redirects = {}
        for job_id in takeover_targets:
            plugin_job_id = f"{pid}_{job_id}"
            if not scheduler._jobs.get(plugin_job_id):
                logger.warning(f"服务管理插件：插件任务不存在，跳过接管 {plugin_job_id}")
                continue
            self._remove_system_job(scheduler, job_id)
            redirects[job_id] = plugin_job_id

        self.__class__._start_redirects = redirects
        self.__class__._plugin_job_aliases.update(
            {plugin_job_id: job_id for job_id, plugin_job_id in redirects.items()}
        )
        if self.__class__._start_redirects:
            self._install_start_hook()
            logger.info(
                f"服务管理插件已接管服务：{', '.join(sorted(self.__class__._start_redirects.keys()))}"
            )
        else:
            self._uninstall_start_hook()
            logger.info("服务管理插件未接管任何服务，继续使用系统默认任务")

    def _disable_takeover(self, restore_system_jobs: bool = True):
        restore_job_ids = sorted(self.__class__._start_redirects) or list(self._MANAGED_JOB_IDS)
        pid = self._get_plugin_id()
        if self.__class__._active_instance is self:
            self.__class__._active_instance = None
        self.__class__._start_redirects = {}
        self._uninstall_init_hook()
        if not restore_system_jobs:
            self._uninstall_start_hook()
            return

        self._enabled = False
        scheduler = self._get_scheduler_if_ready()
        if not scheduler:
            self._uninstall_start_hook()
            return
        try:
            running_jobs = self._get_running_job_names(scheduler)
            if running_jobs:
                logger.warning(
                    "服务管理插件正在恢复系统服务，等待运行中的服务结束："
                    f"{', '.join(running_jobs)}"
                )
            for legacy_pid in self._get_legacy_plugin_ids(pid):
                scheduler.remove_plugin_job(pid=legacy_pid)
            scheduler.remove_plugin_job(pid=pid)
            if not self._restore_system_jobs(scheduler, restore_job_ids):
                scheduler.init()
        except Exception as e:
            logger.warning(f"服务管理插件恢复系统任务失败：{str(e)}")
        finally:
            self._uninstall_start_hook()

    @classmethod
    def _install_start_hook(cls):
        if cls._original_scheduler_start:
            return
        original = Scheduler.start

        @wraps(original)
        def _wrapped_start(scheduler_self, job_id: str, *args, **kwargs):
            redirect_job_id = cls._start_redirects.get(job_id)
            if redirect_job_id and scheduler_self._jobs.get(redirect_job_id):
                original_job = scheduler_self._jobs.get(job_id)
                if original_job and original_job.get("running"):
                    return cls._original_scheduler_start(
                        scheduler_self, job_id, *args, **kwargs
                    )
                job_id = redirect_job_id
            alias_job_id = cls._plugin_job_aliases.get(job_id)
            if alias_job_id:
                with scheduler_self._lock:
                    cls._running_redirects[alias_job_id] = (
                        cls._running_redirects.get(alias_job_id, 0) + 1
                    )
                    alias_job = scheduler_self._jobs.get(alias_job_id)
                    if alias_job and not alias_job.get("pid"):
                        alias_job["running"] = True
            try:
                return cls._original_scheduler_start(scheduler_self, job_id, *args, **kwargs)
            finally:
                if alias_job_id:
                    with scheduler_self._lock:
                        running_count = cls._running_redirects.get(alias_job_id, 0) - 1
                        if running_count > 0:
                            cls._running_redirects[alias_job_id] = running_count
                        else:
                            cls._running_redirects.pop(alias_job_id, None)
                            alias_job = scheduler_self._jobs.get(alias_job_id)
                            if alias_job and not alias_job.get("pid"):
                                alias_job["running"] = False

        cls._original_scheduler_start = original
        Scheduler.start = _wrapped_start

    @classmethod
    def _uninstall_start_hook(cls):
        if cls._original_scheduler_start:
            Scheduler.start = cls._original_scheduler_start
            cls._original_scheduler_start = None

    @classmethod
    def _install_init_hook(cls):
        if cls._original_scheduler_init:
            return
        original = Scheduler.init

        @wraps(original)
        def _wrapped_init(scheduler_self, *args, **kwargs):
            previous_scheduler = cls._scheduler_context
            cls._scheduler_context = scheduler_self
            try:
                result = cls._original_scheduler_init(scheduler_self, *args, **kwargs)
                instance = cls._active_instance
                if instance and instance.get_state():
                    try:
                        instance._apply_takeover(scheduler=scheduler_self)
                    except Exception as e:
                        logger.warning(f"服务管理插件接管失败：{str(e)}")
                return result
            finally:
                cls._scheduler_context = previous_scheduler

        cls._original_scheduler_init = original
        Scheduler.init = _wrapped_init

    @classmethod
    def _uninstall_init_hook(cls):
        if cls._original_scheduler_init:
            Scheduler.init = cls._original_scheduler_init
            cls._original_scheduler_init = None
