from pathlib import Path

import pytest
from pydantic import ValidationError
from sakuramedia_more_rank_movies.boards import MINNANO_SOURCE_KEY
from sakuramedia_more_rank_movies.sync_jobs import SyncBoardParams, build_jobs

from src.plugins import PluginContext


def _context() -> PluginContext:
    return PluginContext(
        plugin_id="sakuramedia_more_rank_movies",
        settings={},
        data_dir=Path("/tmp/more-rank-movies-test"),
    )


def test_build_jobs_declares_cron_and_manual_task():
    jobs = build_jobs(_context(), prepare_run=lambda: None, full_sync_total=3)
    assert [job.task_key for job in jobs] == [
        "sakuramedia_more_rank_movies_sync",
        "sakuramedia_more_rank_movies_sync_board",
    ]
    assert jobs[0].default_cron == "45 1 * * *"
    assert jobs[0].handler is not None
    assert jobs[1].manual_only is True
    assert jobs[1].params_schema is SyncBoardParams


def test_sync_board_params_validation():
    params = SyncBoardParams(
        source_key="minnano_av", board_key="minnano_av", period="daily"
    )
    assert params.source_key == "minnano_av"
    assert params.period == "daily"
    with pytest.raises(ValidationError):
        SyncBoardParams(board_key="minnano_av")
    with pytest.raises(ValidationError):
        SyncBoardParams(source_key="Bad-Key", board_key="minnano_av")
    with pytest.raises(ValidationError):
        SyncBoardParams(source_key="minnano_av", board_key="Bad-Key")


def test_job_declarations_expose_english_cli_help():
    jobs = build_jobs(_context(), prepare_run=lambda: None, full_sync_total=3)

    assert jobs[0].cli_help_i18n == {
        "zh-CN": "同步更多影片榜单（Minnano AV、JavLibrary）",
        "en": "Sync More Movie Rankings (Minnano AV, JavLibrary)",
    }
    assert jobs[1].cli_help_i18n["en"] == (
        "Manually sync a single board from More Movie Rankings"
    )


def test_sync_board_params_schema_exposes_localized_options():
    properties = SyncBoardParams.model_json_schema()["properties"]

    assert properties["board_key"]["title_i18n"]["en"] == "Board"
    board_options = {
        option["const"]: option for option in properties["board_key"]["oneOf"]
    }
    assert board_options["javlibrary_mostwanted"]["title_i18n"] == {
        "zh-CN": "JavLibrary 最想要",
        "en": "JavLibrary Most Wanted",
    }
    assert board_options["javlibrary_bestrated"]["x-when"] == ["javlibrary"]

    period_options = {
        option["const"]: option for option in properties["period"]["oneOf"]
    }
    assert period_options["daily"]["x-when"] == ["minnano_av"]
    assert period_options["all"]["title_i18n"]["en"] == "All"
    assert properties["period"]["x-options-by"] == "board_key"


def test_sync_all_handler_prepares_run_and_passes_progress():
    calls = []
    context = _context()
    object.__setattr__(
        context,
        "sync_ranking_sources",
        lambda **kwargs: calls.append(kwargs) or {"ok": 1},
    )
    prepared = []
    jobs = build_jobs(
        context,
        prepare_run=lambda: prepared.append(1),
        full_sync_total=3,
    )

    class Reporter:
        progress_callback = staticmethod(lambda _payload: None)

    jobs[0].handler(Reporter(), {})

    assert prepared == [1]
    assert list(calls[0]) == ["progress_callback"]


def test_sync_board_handler_uses_params_source_key():
    calls = []
    context = _context()
    object.__setattr__(
        context,
        "sync_ranking_board",
        lambda **kwargs: calls.append(kwargs) or {"ok": 1},
    )
    prepared = []
    jobs = build_jobs(
        context,
        prepare_run=lambda: prepared.append(1),
        full_sync_total=3,
    )

    jobs[1].handler(
        type("Reporter", (), {"progress_callback": staticmethod(lambda _payload: None)})(),
        {"source_key": "minnano_av", "board_key": "minnano_av", "period": "monthly"},
    )

    assert prepared == [1]
    assert calls == [
        {
            "source_key": MINNANO_SOURCE_KEY,
            "board_key": "minnano_av",
            "period": "monthly",
        }
    ]
