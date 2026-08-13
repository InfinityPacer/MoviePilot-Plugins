"""订阅生命周期编排接口。"""

from .coordinator import (
    DownloadPendingLifecycleAdapter,
    LifecycleResult,
    SubscribeLifecycleCoordinator,
)

__all__ = [
    "DownloadPendingLifecycleAdapter",
    "LifecycleResult",
    "SubscribeLifecycleCoordinator",
]
