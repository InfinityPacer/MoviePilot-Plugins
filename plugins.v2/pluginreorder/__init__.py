from typing import Any, List, Dict, Tuple, Optional

from app.core.event import eventmanager, Event
from app.core.plugin import PluginManager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType


class PluginReOrder(_PluginBase):
    # 插件名称
    plugin_name = "插件自定义排序"
    # 插件描述
    plugin_desc = "支持将插件按自定义顺序排序。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/reorder.png"
    # 插件版本
    plugin_version = "1.1"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "pluginreorder_"
    # 加载顺序
    plugin_order = 10000
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    # 启用插件
    _enabled = None
    # 系统配置
    _sys_plugin_config = None
    # 用户配置
    _user_plugin_config = None

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._user_plugin_config = config.get("user_plugin_config", "")
        self._sys_plugin_config = self.__get_sys_plugin_config()
        self.__update_config()
        self.__update_plugin_order()

    def get_state(self):
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # plugin_options = self.__get_local_plugin_options()

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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
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
                                    "cols": 6,
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'sys_plugin_config',
                                            'label': '默认插件顺序配置',
                                            'rows': 10,
                                            'no-resize': True,
                                            'readonly': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    "cols": 6,
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'user_plugin_config',
                                            'label': '自定义插件顺序配置',
                                            'rows': 10,
                                            'no-resize': True,
                                            'placeholder': '每一行一个插件顺序配置项，格式为：'
                                                           '\n插件ID#插件名称#插件顺序'
                                                           '\n参考如下：'
                                                           '\nBrushFlow#站点刷流#21'
                                                           '\nPlexLocalization#Plex本地中文化#30'
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
                                            'text': '注意：请在自定义插件顺序配置中填写，只需要填写希望调整的插件，'
                                                    '配置格式与默认插件顺序配置一致'
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
                                            'text': '注意：默认插件顺序配置不全时，可保存后重新打开后查看'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "sys_plugin_config": self._sys_plugin_config if self._sys_plugin_config else self.__get_sys_plugin_config()
        }

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        pass

    def __update_config(self):
        """保存配置"""
        config_mapping = {
            "enabled": self._enabled,
            "sys_plugin_config": self._sys_plugin_config,
            "user_plugin_config": self._user_plugin_config
        }
        self.update_config(config_mapping)

    @staticmethod
    def __get_sys_plugin_config() -> str:
        """
        获取系统预置插件顺序
        """
        # 获取本地插件实例
        local_plugins = PluginManager().get_local_plugins()
        # 获取已经安装的插件实例
        # installed_plugins = [plugin for plugin in local_plugins if
        #                      plugin.installed and plugin.id != "PluginReOrder"]
        installed_plugins = [plugin for plugin in local_plugins if plugin.installed]
        # 对已安装的插件排序
        installed_plugins.sort(key=lambda x: x.plugin_order)
        # 创建格式化字符串
        formatted_str = "插件ID#插件名称#插件顺序"
        for plugin in installed_plugins:
            formatted_str += f"\n{plugin.id}#{plugin.plugin_name}#{plugin.plugin_order}"

        return formatted_str

    def __update_plugin_order(self, plugin_id: Optional[str] = None):
        """
        根据用户配置更新插件顺序
        """
        if not self._enabled:
            return

        if not self._user_plugin_config:
            return

        logger.info("准备开始调整用户自定义插件顺序")

        # 解析用户配置，每行一个插件配置
        user_plugin_config = self._user_plugin_config.strip().split('\n')
        local_plugins = getattr(PluginManager(), '_plugins', {})

        if not local_plugins:
            logger.error("没有获取到本地插件实例，请尝试重启MoviePilot")
            return

        # 标记是否处理了指定的插件
        plugin_processed = False

        for user_plugin in user_plugin_config:
            parts = user_plugin.strip().split('#')

            if len(parts) < 3:
                logger.warn(f"跳过无效条目：{user_plugin}")
                continue

            current_plugin_id, plugin_name, plugin_order_str = parts[0], parts[1], parts[2]

            # 如果指定了 plugin_id 且当前插件不是目标插件，则跳过
            if plugin_id and current_plugin_id != plugin_id:
                continue

            if not plugin_order_str.isdigit():
                logger.warn(f"插件顺序无效，跳过条目：{user_plugin}")
                continue

            plugin_order = int(plugin_order_str)

            # 查找并更新本地插件
            found_plugin = local_plugins.get(current_plugin_id)
            if found_plugin:
                logger.info(
                    f"更新插件 {found_plugin.plugin_name} 的顺序，从 {found_plugin.plugin_order} 更改为 {plugin_order}"
                )
                found_plugin.plugin_order = plugin_order
                plugin_processed = True
            else:
                logger.warn(f"未找到ID为 {current_plugin_id}#{plugin_name} 的插件")

            # 如果指定了 plugin_id，处理完后即可退出循环
            if plugin_id:
                break

        if plugin_id:
            if plugin_processed:
                logger.info(f"已完成插件ID {plugin_id} 的顺序调整")
            else:
                logger.warn(f"在用户配置中未找到插件ID: {plugin_id}")
        else:
            logger.info("已完成用户自定义插件顺序调整")

    @eventmanager.register(EventType.PluginReload)
    def plugin_reload(self, event: Event):
        """
        插件重载
        """
        if not event:
            return
        event_data = event.event_data or {}
        plugin_id = event_data.get("plugin_id")
        self.__update_plugin_order(plugin_id=plugin_id)
