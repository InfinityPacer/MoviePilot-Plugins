import threading
from typing import Any, Dict, List, Tuple, Optional

from jinja2 import Template

from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.event import TransferRenameEventData
from app.schemas.types import ChainEventType

lock = threading.Lock()


class SmartRename(_PluginBase):
    # 插件名称
    plugin_name = "智能重命名"
    # 插件描述
    plugin_desc = "自定义适配多场景重命名。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/smartrename.png"
    # 插件版本
    plugin_version = "1.1"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "smartrename_"
    # 加载顺序
    plugin_order = 43
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    # 是否开启
    _enabled = False
    # 分隔符
    _edition_separator: Optional[str] = None

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled") or False
        self._edition_separator = config.get("edition_separator")

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
        edition_options = [
            {"title": "默认", "value": None},
            {"title": "空格", "value": " "},
            {"title": "点 (.)", "value": "."},
            {"title": "横杠 (-)", "value": "-"},
            {"title": "下划线 (_)", "value": "_"}
        ]

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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'edition_separator',
                                            'label': 'EDITION 分隔符',
                                            'hint': '请输入 EDITION 分隔符，如：. - _ 空格',
                                            'persistent-hint': True
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
            "kwargs": {} # 定时器参数
        }]
        """
        pass

    def stop_service(self):
        """
        退出插件
        """
        pass

    @eventmanager.register(ChainEventType.TransferRename)
    def handle_transfer_rename(self, event: Event):
        """
        处理 TransferRename 事件
        :param event: 事件数据
        """
        if not event or not event.event_data:
            return

        event_data: TransferRenameEventData = event.event_data

        logger.info(f"处理 TransferRename 事件 - {event_data}")

        if event_data.updated:
            logger.debug(f"该事件已被其他事件处理器处理，跳过后续操作")
            return

        try:
            # 调用智能重命名方法
            updated_str = self.rename(template_string=event_data.template_string, rename_dict=event_data.rename_dict)
            # 仅在智能重命名有实际更新时，标记更新状态
            if updated_str and updated_str != event_data.render_str:
                event_data.updated_str = updated_str
                event_data.updated = True
                event_data.source = self.__class__.__name__
        except Exception as e:
            logger.error(f"重命名发生未知异常: {e}", exc_info=True)

    def rename(self, template_string: str, rename_dict: dict) -> Optional[str]:
        """
        智能重命名
        :param template_string: Jinja2 模板字符串
        :param rename_dict: 渲染上下文，用于替换模板中的变量
        :return: 生成的完整字符串
        """
        # 检查并更新
        updated = False

        # 修改 edition 并判断是否有实际更新
        if "edition" in rename_dict:
            original_edition = rename_dict["edition"]
            updated_edition = self.modify_edition(original_edition)

            # 如果 modify_edition 没有更新 edition，保持原值
            if updated_edition is not None and updated_edition != original_edition:
                rename_dict["edition"] = updated_edition
                updated = True

        # 如果没有任何字段被修改，直接返回 None
        if not updated:
            return None

        # 创建jinja2模板对象
        template = Template(template_string)
        # 渲染生成的字符串
        return template.render(rename_dict)

    def modify_edition(self, edition: str) -> Optional[str]:
        """
        修改 edition 字段，使用指定分隔符进行合并
        :param edition: 原始 edition 字段
        :return: 修改后的 edition 或 None（如果不处理）
        """
        if not edition or not self._edition_separator:
            return None
        if isinstance(edition, str):
            parts = edition.split()
            updated_edition = self._edition_separator.join(parts)
            return updated_edition if updated_edition != edition else None
        return None
