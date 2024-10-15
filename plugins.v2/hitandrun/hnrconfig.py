import json
from enum import Enum
from typing import Optional, List, Dict

from pydantic import BaseModel, root_validator, validator
from ruamel.yaml import YAML, YAMLError

from app.log import logger


class NotifyMode(Enum):
    NONE = "none"  # 不发送
    ON_ERROR = "on_error"  # 仅异常时发送
    ALWAYS = "always"  # 发送所有通知


class BaseConfig(BaseModel):
    """
    基础配置类，定义所有配置项的结构
    """
    hr_duration: Optional[float] = None  # H&R时间（小时）
    additional_seed_time: Optional[float] = None  # 附加做种时间（小时）
    hr_ratio: Optional[float] = None  # H&R分享率
    hr_active: Optional[bool] = False  # H&R激活
    hr_deadline_days: Optional[float] = None  # H&R满足要求的期限（天数）

    # 模型配置
    class Config:
        extra = "ignore"
        arbitrary_types_allowed = True

        @staticmethod
        def json_dumps(v, *, default):
            return json.dumps(v, ensure_ascii=False, default=default)

    def to_dict(self, **kwargs):
        """
        返回字典
        """
        config_json = self.json(**kwargs)
        config_mapping = json.loads(config_json)
        return config_mapping

    @property
    def hr_seed_time(self) -> Optional[float]:
        """
        H&R做种时间（小时）
        """
        return (self.hr_duration or 0.0) + (self.additional_seed_time or 0.0)


class SiteConfig(BaseConfig):
    """
    站点配置类，继承自基础配置类，添加站点特有的标识属性
    """
    site_name: Optional[str] = None  # 站点名称


class HNRConfig(BaseConfig):
    """
    全局配置类，继承自基础配置类，添加全局特有的配置项
    """
    enabled: Optional[bool] = False  # 启用插件
    check_period: int = 5  # 检查周期
    sites: List[int] = []  # 站点列表
    site_infos: Dict = {}  # 站点信息字典
    onlyonce: Optional[bool] = False  # 立即运行一次
    notify: NotifyMode = NotifyMode.ALWAYS  # 发送通知的模式
    brush_plugin: Optional[str] = None  # 站点刷流插件
    auto_monitor: Optional[bool] = False  # 自动监控（实验性功能）
    downloader: Optional[str] = None  # 下载器
    hit_and_run_tag: Optional[str] = None  # 种子标签
    auto_cleanup_days: float = 7  # 自动清理已删除或满足H&R要求的任务
    enable_site_config: Optional[bool] = False  # 启用站点独立配置
    site_config_str: Optional[str] = None  # 站点独立配置的字符串
    site_configs: Dict[str, SiteConfig] = {}  # 站点独立配置（根据配置字符串解析后的字典）

    @root_validator(pre=True, allow_reuse=True)
    def __check_enums(cls, values):
        """校验枚举值"""
        # 处理 notify 字段
        notify_value = values.get("notify")
        all_values = {member.value for member in NotifyMode}
        if notify_value not in all_values:
            values["notify"] = NotifyMode.ALWAYS
        return values

    @validator("*", pre=True, allow_reuse=True)
    def __empty_string_to_float(cls, v, values, field):
        """
        校验空字符
        """
        if field.type_ is float and not v:
            return 0.0
        return v

    @validator("auto_cleanup_days", pre=True, allow_reuse=True)
    def set_default_auto_cleanup_days(cls, v):
        """
        当 auto_cleanup_days 为 None 时，设置为 7
        """
        if v is None:
            return 7
        return v

    def __init__(self, **data):
        super().__init__(**data)
        self.__post_init__()

    def __post_init__(self):
        """
        初始化完成
        """
        self.__process_site_configs()

    def __process_site_configs(self):
        """
        校验并解析站点独立配置
        """
        if self.enable_site_config:
            if self.site_config_str:
                self.site_configs = self.__parse_yaml_config(self.site_config_str)
                if self.site_configs:
                    for site_name, site_config in self.site_configs.items():
                        self.site_configs[site_name] = self.__merge_site_config(site_config=site_config)
                else:
                    logger.error("YAML解析失败，站点独立配置已禁用")
                    self.enable_site_config = False
            else:
                logger.warn("已启用站点独立配置，但未提供配置字符串，站点独立配置已禁用")
                self.enable_site_config = False

    @staticmethod
    def __parse_yaml_config(yaml_str: str) -> Optional[Dict[str, SiteConfig]]:
        """
        解析YAML字符串为站点配置字典
        """
        yaml = YAML(typ="safe")
        try:
            data = yaml.load(yaml_str)
            site_configs = {}
            for item in data:
                site_name = item.get("site_name")
                if site_name:
                    try:
                        site_configs[site_name] = SiteConfig(**item)
                    except Exception as e:
                        logger.error(f"站点 {site_name} 无效，忽略该站点配置，{e}")
            return site_configs
        except YAMLError as e:
            logger.error(f"无法获取站点独立配置信息，YAML解析错误: {e}")
            return None

    def __merge_site_config(self, site_config: SiteConfig) -> SiteConfig:
        """
        合并站点配置
        """
        for field_name, field_info in SiteConfig.__fields__.items():
            # 获取当前 site_config 对象中的字段值
            current_value = getattr(site_config, field_name, None)
            # 如果当前字段值为 None，则尝试从 HNRConfig 实例中获取同名字段的默认值
            if current_value is None:
                # 尝试从 HNRConfig 实例获取默认值，如果不存在则使用 Pydantic 字段的默认值
                default_value = getattr(self, field_name, field_info.default)
                # 设置 site_config 对象的字段值
                setattr(site_config, field_name, default_value)

        return site_config

    def get_site_config(self, site_name: str) -> SiteConfig:
        """
        根据站点名称返回合并后的配置
        """
        site_config = self.site_configs.get(site_name)
        if site_config:
            return site_config
        else:
            # 使用 __fields__ 获取所有字段并从实例中获取对应值
            base_config_attrs = {field: getattr(self, field) for field in self.__fields__}
            return SiteConfig(**base_config_attrs, site_name=site_name)
