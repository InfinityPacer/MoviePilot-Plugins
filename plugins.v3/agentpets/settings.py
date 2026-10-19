"""舞台活动参数范围与默认配置"""

SCALE_RANGE = (0.6, 1.6)
SPEED_RANGE = (0.5, 2.0)
PEEK_ANGLE_RANGE = (0.0, 45.0)
DEFAULT_PEEK_ANGLES = {"bottom": 0.0, "left": 35.0, "right": 35.0}
PEEK_EDGES = ("bottom", "left", "right")
ROAM_MODES = ("surfaces", "floor", "free")
DEFAULT_SETTINGS = {"scale": 1.0, "speed": 1.0, "roam": "surfaces", "movement": "auto"}
