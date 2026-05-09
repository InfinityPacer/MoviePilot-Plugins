from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional

from ruamel.yaml import YAML, YAMLError

from app.log import logger


@dataclass
class BaseConfig:
    """
    基础配置类，定义所有配置项的结构。
    """
    ratio_upper_limit: Optional[float] = None  # 分享率的上限
    ratio_lower_limit: Optional[float] = None  # 分享率的下限

    remove_from_subscription_if_below: Optional[bool] = False  # 分享率低于下限时，是否从订阅站点中移除
    remove_from_search_if_below: Optional[bool] = False  # 分享率低于下限时，是否从搜索站点中移除
    enable_auto_brush_if_below: Optional[bool] = False  # 分享率低于下限时，是否开启自动刷流
    send_alert_if_below: Optional[bool] = False  # 分享率低于下限时，是否发送预警消息

    add_to_subscription_if_above: Optional[bool] = False  # 分享率高于上限时，是否增加到订阅站点
    add_to_search_if_above: Optional[bool] = False  # 分享率高于上限时，是否增加到搜索站点
    disable_auto_brush_if_above: Optional[bool] = False  # 分享率高于上限时，是否关闭自动刷流

    def __post_init__(self):
        # 将输入转换为适当的类型
        self.ratio_upper_limit = convert_type(self.ratio_upper_limit, float)
        self.ratio_lower_limit = convert_type(self.ratio_lower_limit, float)


@dataclass
class TrafficConfig(BaseConfig):
    """
    全局配置类，继承自基础配置类，添加全局特有的配置项。
    """
    enabled: Optional[bool] = False  # 启用插件
    sites: List[int] = field(default_factory=list)  # 站点列表
    site_infos: dict = None  # 站点信息字典
    onlyonce: Optional[bool] = False  # 立即运行一次
    notify: Optional[bool] = False  # 发送通知
    cron: Optional[str] = None  # 执行周期
    brush_plugin: Optional[str] = None  # 站点刷流插件
    statistic_plugin: Optional[str] = "SiteStatistic"  # 站点数据统计插件
    enable_site_config: Optional[bool] = False  # 启用站点独立配置
    site_config_str: Optional[str] = None  # 站点独立配置的 YAML 字符串
    site_configs: Dict[str, BaseConfig] = field(default_factory=dict)  # 解析后的站点独立配置

    def __post_init__(self):
        """
        初始化全局配置，并在启用时解析站点独立配置。
        """
        super().__post_init__()
        self.__process_site_configs()

    def __process_site_configs(self):
        """
        校验并解析站点独立配置，解析失败时自动关闭站点独立配置。
        """
        if not self.enable_site_config:
            self.site_configs = {}
            return

        if not self.site_config_str:
            logger.warning("已启用站点独立配置，但未提供配置字符串，站点独立配置已禁用")
            self.enable_site_config = False
            self.site_configs = {}
            return

        site_configs = self.__parse_yaml_config(self.site_config_str)
        if not site_configs:
            logger.error("YAML解析失败，站点独立配置已禁用")
            self.enable_site_config = False
            self.site_configs = {}
            return

        self.site_configs = {
            site_name: merge_configs(global_config=self, site_config=site_config)
            for site_name, site_config in site_configs.items()
        }

    @staticmethod
    def __parse_yaml_config(yaml_str: str) -> Optional[Dict[str, "SiteConfig"]]:
        """
        将 YAML 字符串解析为按站点名称索引的站点配置。
        """
        yaml = YAML(typ="safe")
        try:
            data = yaml.load(yaml_str) or []
            site_configs = {}
            for item in data:
                if not isinstance(item, dict):
                    logger.error(f"站点独立配置项无效，忽略该配置：{item}")
                    continue
                site_name = item.get("site_name")
                if not site_name:
                    logger.error(f"站点独立配置缺少 site_name，忽略该配置：{item}")
                    continue
                try:
                    site_configs[site_name] = SiteConfig(**item)
                except Exception as err:
                    logger.error(f"站点 {site_name} 无效，忽略该站点配置，{err}")
            return site_configs
        except YAMLError as err:
            logger.error(f"无法获取站点独立配置信息，YAML解析错误: {err}")
            return None

    def get_site_config(self, site_name: str) -> BaseConfig:
        """
        获取指定站点的最终流量配置；未配置站点时返回全局配置。
        """
        if self.enable_site_config:
            site_config = self.site_configs.get(site_name)
            if site_config:
                return site_config
        return merge_configs(global_config=self, site_config=None)


@dataclass
class SiteConfig(BaseConfig):
    """
    站点配置类，继承自基础配置类，添加站点特有的标识属性。
    """
    ratio_upper_limit: Optional[float] = None  # 站点分享率的上限，未配置时继承全局配置
    ratio_lower_limit: Optional[float] = None  # 站点分享率的下限，未配置时继承全局配置
    remove_from_subscription_if_below: Optional[bool] = None  # 低于下限时是否移出订阅站点
    remove_from_search_if_below: Optional[bool] = None  # 低于下限时是否移出搜索站点
    enable_auto_brush_if_below: Optional[bool] = None  # 低于下限时是否开启自动刷流
    send_alert_if_below: Optional[bool] = None  # 低于下限时是否发送预警
    add_to_subscription_if_above: Optional[bool] = None  # 高于上限时是否加入订阅站点
    add_to_search_if_above: Optional[bool] = None  # 高于上限时是否加入搜索站点
    disable_auto_brush_if_above: Optional[bool] = None  # 高于上限时是否关闭自动刷流
    site_name: Optional[str] = None  # 站点名称

    def __post_init__(self):
        """
        初始化站点配置，仅转换显式填写的数值，保留空值用于继承全局配置。
        """
        if self.ratio_upper_limit is not None:
            self.ratio_upper_limit = convert_type(self.ratio_upper_limit, float)
        if self.ratio_lower_limit is not None:
            self.ratio_lower_limit = convert_type(self.ratio_lower_limit, float)


def convert_type(value, target_type):
    """
    将给定值转换为指定的目标类型。如果转换失败，则返回该类型的自然默认值。
    """
    try:
        if target_type == float:
            return float(value)
        if target_type == int:
            return int(value)
        # 可以根据需要添加其他类型
    except (ValueError, TypeError):
        # 如果转换失败，则返回类型的自然默认值
        if target_type == float:
            return 0.0
        if target_type == int:
            return 0
        return None  # 未指定类型的默认值


def merge_configs(global_config: TrafficConfig, site_config: Optional[SiteConfig]) -> BaseConfig:
    """
    根据全局配置和站点配置合并得到最终的配置对象。
    站点配置将覆盖全局配置中的相应项。
    """
    final_config = {
        field_info.name: getattr(global_config, field_info.name)
        for field_info in fields(BaseConfig)
    }
    if site_config:
        # 遍历站点配置，覆盖全局配置
        for key, value in {
            field_info.name: getattr(site_config, field_info.name)
            for field_info in fields(BaseConfig)
        }.items():
            if value is not None:
                final_config[key] = value
    return BaseConfig(**final_config)
