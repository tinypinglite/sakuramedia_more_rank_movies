"""按任务运行隔离排行榜站点 client。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class PerRunProviderHolder:
    """同一任务运行复用 client，不同线程/运行使用新实例。"""

    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._local = threading.local()

    def fresh_for_current_thread(self) -> Any:
        provider = self._factory()
        self._local.provider = provider
        return provider

    def get(self) -> Any:
        provider = getattr(self._local, "provider", None)
        if provider is None:
            provider = self.fresh_for_current_thread()
        return provider
