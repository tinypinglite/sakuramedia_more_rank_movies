"""SakuraMedia 更多影片排行榜插件入口。"""

from __future__ import annotations

import json
from pathlib import Path

from src.plugins import (
    HOST_API_VERSION,
    RANKING_SOURCE_EXTENSION_KEY,
    PluginContext,
    PluginExtension,
    PluginRegistration,
)

from .boards import build_ranking_sources
from .javlibrary import JavLibraryClient
from .minnano import MinnanoAvClient
from .providers import PerRunProviderHolder
from .sync_jobs import build_jobs
from .translations import text_map

__version__ = json.loads(
    Path(__file__).with_name("manifest.json").read_text(encoding="utf-8")
)["version"]
PLUGIN_ID = "sakuramedia_more_rank_movies"
DISPLAY_NAME = "SakuraMedia 更多影片榜单"
DISPLAY_NAME_I18N = text_map("manifest.display_name")


def register(context: PluginContext) -> PluginRegistration:
    """声明榜单来源与同步任务，不在插件加载阶段发起网络请求。"""
    # 每个任务运行新建 client；client 内部错误会作为任务失败原因展示，
    # 因此把当前语言的翻译器一并注入。
    minnano_holder = PerRunProviderHolder(
        factory=lambda: MinnanoAvClient(i18n=context.i18n)
    )
    javlibrary_holder = PerRunProviderHolder(
        factory=lambda: JavLibraryClient(i18n=context.i18n)
    )
    sources = build_ranking_sources(
        minnano_holder=minnano_holder,
        javlibrary_holder=javlibrary_holder,
    )
    full_sync_total = sum(
        len(board.supported_periods) or 1
        for source in sources
        for board in source.boards
    )

    def prepare_run() -> None:
        minnano_holder.fresh_for_current_thread()
        javlibrary_holder.fresh_for_current_thread()

    return PluginRegistration(
        plugin_id=PLUGIN_ID,
        display_name=DISPLAY_NAME,
        display_name_i18n=DISPLAY_NAME_I18N,
        version=__version__,
        host_api_version=HOST_API_VERSION,
        extensions=tuple(
            PluginExtension(key=RANKING_SOURCE_EXTENSION_KEY, data=source)
            for source in sources
        ),
        jobs=build_jobs(
            context,
            prepare_run=prepare_run,
            full_sync_total=full_sync_total,
        ),
    )
