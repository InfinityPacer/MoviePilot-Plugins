import copy
import threading
from typing import Any, Dict, List, Tuple, Optional

from jinja2 import Template

from app.core.event import Event, eventmanager
from app.core.meta.customization import CustomizationMatcher
from app.core.meta.words import WordsMatcher
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
    plugin_version = "1.3"
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
    # 默认分隔符
    _separator: Optional[str] = None
    # 分隔符适用范围
    _separator_types: Optional[list] = None
    # 各字段的分隔符字典，按需配置不同字段的分隔符
    _field_separators: Optional[Dict[str, str]] = None
    # 自定义替换词
    _word_replacements: Optional[list] = []
    # 自定义占位符分隔符
    _custom_separator: Optional[str] = "@"

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled") or False
        self._separator = config.get("separator")
        self._separator_types = config.get("separator_types")
        self._word_replacements = self.__parse_replacement_rules(config.get("word_replacements"))
        self._custom_separator = config.get("custom_separator") or "@"
        CustomizationMatcher().custom_separator = self._custom_separator

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
                                            'model': 'separator',
                                            'label': '默认分隔符',
                                            'hint': '请输入默认分隔符，如：. - _ 空格',
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
                                            'model': 'custom_separator',
                                            'label': '自定义占位符分隔符',
                                            'hint': '请输入 customization 的分隔符，如：. - _ 空格，默认为 @',
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
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'separator_types',
                                            'label': '分隔符适用范围',
                                            'items': [
                                                {'title': 'title', 'value': 'title'},
                                                {'title': 'en_title', 'value': 'en_title'},
                                                {'title': 'original_title', 'value': 'original_title'},
                                                {'title': 'name', 'value': 'name'},
                                                {'title': 'en_name', 'value': 'en_name'},
                                                {'title': 'original_name', 'value': 'original_name'},
                                                {'title': 'resourceType', 'value': 'resourceType'},
                                                {'title': 'effect', 'value': 'effect'},
                                                {'title': 'edition', 'value': 'edition'},
                                                {'title': 'videoFormat', 'value': 'videoFormat'},
                                                {'title': 'videoCodec', 'value': 'videoCodec'},
                                                {'title': 'audioCodec', 'value': 'audioCodec'},
                                            ],
                                            'hint': '请选择分隔符适用范围',
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
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'word_replacements',
                                            'label': '自定义替换词',
                                            'rows': 5,
                                            "placeholder": "每行输入一条替换规则，格式：被替换词 => 替换词",
                                            'hint': '定义替换规则，重命名后会自动进行词语替换',
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
            "enabled": False,
            "custom_separator": "@",
            "word_replacements": """(?i)(?<=[\W_])BluRay.REMUX(?=[\W_]) => REMUX
(?i)(?<=[\W_])HDR.DV(?=[\W_]) => DoVi.HDR
(?i)(?<=[\W_])DV(?=[\W_]) => DoVi
(?i)(?<=[\W_])H264(?=[\W_]) => x264
(?i)(?<=[\W_])h265(?=[\W_]) => x265
(?i)(?<=[\W_])NF(?=[\W_]) => Netflix
(?i)(?<=[\W_])AMZN(?=[\W_]) => Amazon"""
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
            logger.debug(f"开始智能重命名处理，原始值：{event_data.render_str}")
            updated_str = self.rename(template_string=event_data.template_string,
                                      rename_dict=copy.deepcopy(event_data.rename_dict)) or event_data.render_str

            # 调用替换词
            if self._word_replacements:
                updated_str, apply_words = WordsMatcher().prepare(title=updated_str,
                                                                  custom_words=self._word_replacements)
                logger.debug(f"完成词语替换，应用的替换词: {apply_words}，替换后字符串：{updated_str}")

            # 仅在智能重命名有实际更新时，标记更新状态
            if updated_str and updated_str != event_data.render_str:
                event_data.updated_str = updated_str
                event_data.updated = True
                event_data.source = self.__class__.__name__
                logger.info(f"重命名完成，{event_data.render_str} -> {updated_str}")
            else:
                logger.debug(f"重命名结果与原始值相同，跳过更新")
        except Exception as e:
            logger.error(f"重命名发生未知异常: {e}", exc_info=True)

    def rename(self, template_string: str, rename_dict: dict) -> Optional[str]:
        """
        智能重命名
        :param template_string: Jinja2 模板字符串
        :param rename_dict: 渲染上下文，用于替换模板中的变量
        :return: 生成的完整字符串
        """
        if not self._separator_types or not self._separator:
            return None

        logger.debug(f"Initial rename_dict: {rename_dict}")

        # 检查并更新
        updated = False
        # 遍历所有字段，根据需要修改
        for field, value in rename_dict.items():
            if field not in self._separator_types:
                continue
            updated_value = self.modify_field(field, value, self._separator_types)

            if updated_value is not None and updated_value != value:
                rename_dict[field] = updated_value
                updated = True
                logger.debug(f"字段 {field} : {value} -> {updated_value}")

        # 如果没有任何字段被修改，直接返回 None
        if not updated:
            return None

        # 创建 jinja2 模板对象
        template = Template(template_string)
        # 渲染生成的字符串
        return template.render(rename_dict)

    def modify_field(self, field: str, value: str, separator_types: list) -> Optional[str]:
        """
        修改字段内容，使用指定的分隔符进行合并
        :param field: 字段名
        :param value: 字段的原始值
        :param separator_types: 需要处理的分隔符类型列表
        :return: 修改后的字段值或 None（如果不处理）
        """
        if not value or not separator_types:
            return None

        if isinstance(value, str):
            parts = value.split()

            # 如果字段不在 separator_types 中，则不做任何修改
            if field not in separator_types:
                return None

            # 如果存在该字段的特定分隔符，则使用该分隔符进行处理
            separator = self._field_separators.get(field,
                                                   self._separator) if self._field_separators else self._separator

            # 使用选定的分隔符类型进行字段值修改
            updated_value = separator.join(parts) if separator else value

            # 如果修改后的值与原值不同，返回更新后的值
            return updated_value if updated_value != value else None

        return None

    @staticmethod
    def __parse_replacement_rules(replacement_str: str) -> Optional[list]:
        """
        将替换规则字符串解析为列表，按行分割
        """
        try:
            if replacement_str:
                # 将字符串按行分割，并去除空行
                return [line.strip() for line in replacement_str.splitlines() if line.strip()]
            return []
        except Exception as e:
            # 记录异常信息并返回空列表
            logger.error(f"Error parsing replacement rules: {e}")
            return []
