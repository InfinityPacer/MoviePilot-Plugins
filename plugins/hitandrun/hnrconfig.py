from dataclasses import dataclass, field, fields
from typing import Optional, List, Dict, Any

from ruamel.yaml import YAML, YAMLError

from app.log import logger


@dataclass
class BaseConfig:
    """
    基础配置类，定义所有配置项的结构。
    """
    hr_duration: Optional[float] = None  # H&R时间（小时）
    additional_seed_time: Optional[float] = None  # 附加做种时间（小时）
    ratio: Optional[float] = None  # 分享率
    hr_active: Optional[bool] = False  # H&R激活

    def __post_init__(self):
        pass

    @property
    def seed_time(self) -> Optional[float]:
        """
        做种时间（小时）
        """
        return (self.hr_duration or 0.0) + (self.additional_seed_time or 0.0)


@dataclass
class SiteConfig(BaseConfig):
    """
    站点配置类，继承自基础配置类，添加站点特有的标识属性。
    """
    site_name: Optional[str] = None  # 站点名称


@dataclass
class HNRConfig(BaseConfig):
    """
    全局配置类，继承自基础配置类，添加全局特有的配置项。
    """
    enabled: Optional[bool] = False  # 启用插件
    check_period: Optional[int] = 5  # 检查周期
    sites: List[int] = field(default_factory=list)  # 站点列表
    site_infos: Dict = field(default_factory=dict)  # 站点信息字典
    onlyonce: Optional[bool] = False  # 立即运行一次
    notify: Optional[str] = "always"  # 发送通知
    brush_plugin: Optional[str] = None  # 站点刷流插件
    auto_monitor: Optional[bool] = False  # 自动监控（实验性功能）
    downloader: Optional[str] = None  # 下载器
    hit_and_run_tag: Optional[str] = None  # 种子标签
    enable_site_config: Optional[bool] = False  # 启用站点独立配置
    site_config_str: Optional[str] = None  # 站点独立配置的字符串
    site_configs: Optional[Dict[str, SiteConfig]] = field(default_factory=dict)  # 站点独立配置（根据配置字符串解析后的字典）

    def __post_init__(self):
        super().__post_init__()
        self.check_period = convert_type(self.check_period, int, default_value=5)
        self.hr_duration = convert_type(self.hr_duration, float)
        self.additional_seed_time = convert_type(self.additional_seed_time, float)
        self.ratio = convert_type(self.ratio, float)
        if self.enable_site_config:
            if self.site_config_str:
                self.site_configs = self.__parse_yaml_config(self.site_config_str)
                if self.site_configs is None:
                    logger.error("YAML解析失败，站点独立配置已禁用")
                    self.enable_site_config = False
                else:
                    for site_name, site_config in self.site_configs.items():
                        self.site_configs[site_name] = self.__merge_site_config(site_config)
            else:
                logger.warn("已启用站点独立配置，但未提供配置字符串，站点独立配置已禁用")
                self.enable_site_config = False

    @staticmethod
    def __parse_yaml_config(yaml_str: str) -> Optional[Dict[str, SiteConfig]]:
        """
        解析YAML字符串为站点配置字典
        """
        yaml = YAML(typ="safe")
        site_configs = {}
        try:
            data = yaml.load(yaml_str)
            site_config_fields = {site_field.name for site_field in fields(SiteConfig)}
            for item in data:
                site_name = item.get("site_name")
                if not site_name:
                    continue
                site_config_data = {k: v for k, v in item.items() if k in site_config_fields}
                site_config = SiteConfig(**site_config_data)
                site_configs[site_name] = site_config
            return site_configs
        except YAMLError as e:
            logger.error(f"无法获取站点独立配置信息，YAML解析错误: {e}")
            return None

    def __merge_site_config(self, site_config: SiteConfig) -> SiteConfig:
        """
        使用默认配置值更新站点配置
        """
        for site_field in fields(SiteConfig):
            if getattr(site_config, site_field.name) is None:
                setattr(site_config, site_field.name, getattr(self, site_field.name, None))
        return site_config

    def get_site_config(self, site_name: str) -> SiteConfig:
        """
        根据站点名称返回合并后的配置
        """
        site_config = self.site_configs.get(site_name)
        if site_config:
            return site_config
        else:
            base_config_attrs = {site_field.name: getattr(self, site_field.name) for site_field in fields(BaseConfig)}
            return SiteConfig(**base_config_attrs, site_name=site_name)


def convert_type(value, target_type, default_value: Optional[Any] = None):
    """
    将给定值转换为指定的目标类型。如果转换失败，则返回指定的默认值或类型的自然默认值
    """
    try:
        return target_type(value)
    except (ValueError, TypeError):
        # 如果传入了默认值，则使用传入的默认值
        if default_value is not None:
            return default_value
        # 使用目标类型的默认构造函数来获取类型的自然默认值
        try:
            return target_type()
        except (TypeError, ValueError):
            return None
