from dataclasses import dataclass, field
from typing import List, Optional


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


@dataclass
class SiteConfig(BaseConfig):
    """
    站点配置类，继承自基础配置类，添加站点特有的标识属性。
    """
    site_name: Optional[str] = None  # 站点名称


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
    final_config = vars(global_config).copy()  # 复制全局配置
    if site_config:
        # 遍历站点配置，覆盖全局配置
        for key, value in vars(site_config).items():
            if value is not None:
                final_config[key] = value
    return BaseConfig(**final_config)  # 返回新的 BaseConfig 实例
