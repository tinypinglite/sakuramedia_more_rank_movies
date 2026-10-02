"""同步任务声明：定时全量同步 + 手动单榜同步。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from src.plugins import PluginContext
from src.scheduler.contracts import JobDefinition

from .progress import RankingProgress


class SyncBoardParams(BaseModel):
    """手动单榜同步参数。"""

    source_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    board_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    period: str | None = Field(default=None, max_length=32)


def build_jobs(
    context: PluginContext,
    *,
    prepare_run: Callable[[], Any],
    full_sync_total: int,
) -> tuple[JobDefinition, ...]:
    """返回本插件的任务声明；执行体只调用宿主同步入口。"""
    if full_sync_total < 1:
        raise ValueError("full_sync_total 必须大于 0")

    def run_sync_all(reporter, _params):
        prepare_run()
        progress = RankingProgress(reporter, total=full_sync_total)
        progress.start()
        try:
            result = context.sync_ranking_sources(
                progress_callback=progress.callback,
            )
        except Exception:
            progress.fail()
            raise
        progress.finish(result)
        return result

    def run_sync_board(reporter, params):
        prepare_run()
        progress = RankingProgress(reporter, total=1)
        progress.start()
        try:
            result = context.sync_ranking_board(
                source_key=params["source_key"],
                board_key=params["board_key"],
                period=params.get("period"),
            )
        except Exception:
            progress.fail()
            raise
        progress.finish(result)
        return result

    return (
        JobDefinition(
            task_key="sakuramedia_more_rank_movies_sync",
            log_name="more-rank-movies-sync",
            cli_name="sync-more-rank-movies",
            cli_help="同步更多影片榜单（Minnano AV、JavLibrary）",
            default_cron="45 1 * * *",
            handler=run_sync_all,
        ),
        JobDefinition(
            task_key="sakuramedia_more_rank_movies_sync_board",
            log_name="more-rank-movies-sync-board",
            cli_name="sync-more-rank-movies-board",
            cli_help="手动同步更多影片榜单中的一个榜单",
            manual_only=True,
            params_schema=SyncBoardParams,
            handler=run_sync_board,
        ),
    )
