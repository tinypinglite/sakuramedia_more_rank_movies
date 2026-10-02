"""更多影片排行榜来源声明。"""

from __future__ import annotations

from typing import Any

from src.plugins import PluginRankingBoard, PluginRankingSource

from .javlibrary import JAVLIBRARY_PERIODS
from .minnano import MINNANO_PERIODS

MINNANO_SOURCE_KEY = "minnano_av"
JAVLIBRARY_SOURCE_KEY = "javlibrary"


def build_ranking_sources(
    *,
    minnano_holder: Any,
    javlibrary_holder: Any,
) -> tuple[PluginRankingSource, ...]:
    """组装站点来源；每个网站声明一个独立来源。"""
    return (
        PluginRankingSource(
            source_key=MINNANO_SOURCE_KEY,
            name="Minnano AV",
            boards=(
                PluginRankingBoard(
                    key="minnano_av",
                    name="Minnano AV",
                    supported_periods=MINNANO_PERIODS,
                    default_period="daily",
                    fetch_numbers=lambda period: (
                        minnano_holder.get().get_rank_numbers(period)
                    ),
                ),
            ),
        ),
        PluginRankingSource(
            source_key=JAVLIBRARY_SOURCE_KEY,
            name="JavLibrary",
            boards=(
                PluginRankingBoard(
                    key="javlibrary_bestrated",
                    name="JavLibrary 高评价",
                    supported_periods=JAVLIBRARY_PERIODS,
                    default_period="monthly",
                    fetch_numbers=lambda period: (
                        javlibrary_holder.get().get_bestrated_numbers(period)
                    ),
                ),
                PluginRankingBoard(
                    key="javlibrary_mostwanted",
                    name="JavLibrary 最想要",
                    supported_periods=JAVLIBRARY_PERIODS,
                    default_period="monthly",
                    fetch_numbers=lambda period: (
                        javlibrary_holder.get().get_mostwanted_numbers(period)
                    ),
                ),
            ),
        ),
    )
