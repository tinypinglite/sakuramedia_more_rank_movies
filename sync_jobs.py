"""同步任务声明：定时全量同步 + 手动单榜同步。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from src.plugins import PluginContext
from src.scheduler.contracts import JobDefinition

from .javlibrary import JAVLIBRARY_PERIODS
from .minnano import MINNANO_PERIODS
from .progress import RankingProgress
from .translations import text, text_map

# 手动任务参数在任务中心渲染为下拉：oneOf 的 const/title 提供提交值与中文标签，
# x-options-by 声明下级选项随上级联动，x-when 标注选项适用的上级取值。
_SOURCE_KEYS = ("minnano_av", "javlibrary")
_BOARDS_BY_SOURCE = {
    "minnano_av": ("minnano_av",),
    "javlibrary": ("javlibrary_bestrated", "javlibrary_mostwanted"),
}
_PERIODS_BY_BOARD = {
    "minnano_av": MINNANO_PERIODS,
    "javlibrary_bestrated": JAVLIBRARY_PERIODS,
    "javlibrary_mostwanted": JAVLIBRARY_PERIODS,
}


def _schema_option(
    value: str,
    title: str,
    when: tuple[str, ...] = (),
    *,
    title_i18n: dict[str, str] | None = None,
) -> dict[str, Any]:
    option: dict[str, Any] = {"const": value, "title": title}
    if when:
        option["x-when"] = list(when)
    if title_i18n is not None:
        option["title_i18n"] = title_i18n
    return option


def _source_key_options() -> list[dict[str, Any]]:
    return [
        _schema_option(
            key,
            text(f"source.{key}.name"),
            title_i18n=text_map(f"source.{key}.name"),
        )
        for key in _SOURCE_KEYS
    ]


def _board_key_options() -> list[dict[str, Any]]:
    return [
        _schema_option(
            board_key,
            text(f"boards.{board_key}"),
            (source_key,),
            title_i18n=text_map(f"boards.{board_key}"),
        )
        for source_key, board_keys in _BOARDS_BY_SOURCE.items()
        for board_key in board_keys
    ]


def _period_options() -> list[dict[str, Any]]:
    boards_by_period: dict[str, list[str]] = {}
    for board_key, periods in _PERIODS_BY_BOARD.items():
        for period in periods:
            boards_by_period.setdefault(period, []).append(board_key)
    return [
        _schema_option(
            period,
            text(f"periods.{period}"),
            tuple(board_keys),
            title_i18n=text_map(f"periods.{period}"),
        )
        for period, board_keys in boards_by_period.items()
    ]


class SyncBoardParams(BaseModel):
    """手动单榜同步参数。"""

    source_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        title=text("jobs.sync_board.params.source_key.title"),
        description=text("jobs.sync_board.params.source_key.description"),
        json_schema_extra={
            "oneOf": _source_key_options(),
            "title_i18n": text_map("jobs.sync_board.params.source_key.title"),
            "description_i18n": text_map(
                "jobs.sync_board.params.source_key.description"
            ),
        },
    )
    board_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        title=text("jobs.sync_board.params.board_key.title"),
        description=text("jobs.sync_board.params.board_key.description"),
        json_schema_extra={
            "oneOf": _board_key_options(),
            "x-options-by": "source_key",
            "title_i18n": text_map("jobs.sync_board.params.board_key.title"),
            "description_i18n": text_map(
                "jobs.sync_board.params.board_key.description"
            ),
        },
    )
    period: str | None = Field(
        default=None,
        max_length=32,
        title=text("jobs.sync_board.params.period.title"),
        description=text("jobs.sync_board.params.period.description"),
        json_schema_extra={
            "oneOf": _period_options(),
            "x-options-by": "board_key",
            "title_i18n": text_map("jobs.sync_board.params.period.title"),
            "description_i18n": text_map(
                "jobs.sync_board.params.period.description"
            ),
        },
    )


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
        progress = RankingProgress(
            reporter,
            total=full_sync_total,
            i18n=context.i18n,
        )
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
        progress = RankingProgress(reporter, total=1, i18n=context.i18n)
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
            cli_help=text("jobs.sync.cli_help"),
            cli_help_i18n=text_map("jobs.sync.cli_help"),
            default_cron="45 1 * * *",
            handler=run_sync_all,
        ),
        JobDefinition(
            task_key="sakuramedia_more_rank_movies_sync_board",
            log_name="more-rank-movies-sync-board",
            cli_name="sync-more-rank-movies-board",
            cli_help=text("jobs.sync_board.cli_help"),
            cli_help_i18n=text_map("jobs.sync_board.cli_help"),
            manual_only=True,
            params_schema=SyncBoardParams,
            handler=run_sync_board,
        ),
    )
