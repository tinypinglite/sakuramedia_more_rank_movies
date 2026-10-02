from threading import Event
from types import SimpleNamespace

from sakuramedia_more_rank_movies.progress import RankingProgress


def test_progress_reports_start_updates_and_cumulative_finish():
    events = []
    progress = RankingProgress(
        SimpleNamespace(progress_callback=events.append),
        total=3,
        heartbeat_seconds=60,
    )

    progress.start()
    progress.callback(
        {
            "current": 1,
            "total": 3,
            "summary_patch": {
                "total_targets": 3,
                "success_targets": 1,
                "failed_targets": 0,
                "fetched_numbers": 100,
            },
        }
    )
    progress.finish(
        {
            "total_targets": 3,
            "success_targets": 2,
            "failed_targets": 1,
            "fetched_numbers": 280,
            "skipped_movies": 4,
        }
    )

    assert [(event["current"], event["total"]) for event in events] == [
        (0, 3),
        (1, 3),
        (3, 3),
    ]
    assert all(event["text"].startswith("阶段 1/1 · 同步排行榜周期") for event in events)
    assert "成功 2 · 失败 1 · 待处理 0" in events[-1]["text"]
    assert events[-1]["summary_patch"] == {
        "processed": 3,
        "succeeded": 2,
        "skipped": 4,
        "failed": 1,
        "pending": 0,
        "retried": 0,
        "total_targets": 3,
        "fetched_numbers": 280,
        "skipped_movies": 4,
    }


def test_progress_failure_marks_attempted_unit_failed():
    events = []
    progress = RankingProgress(
        SimpleNamespace(progress_callback=events.append),
        total=1,
        heartbeat_seconds=60,
    )

    progress.start()
    progress.fail()

    assert events[-1]["current"] == events[-1]["total"] == 1
    assert "任务中止" in events[-1]["text"]
    assert events[-1]["summary_patch"]["processed"] == 1
    assert events[-1]["summary_patch"]["failed"] == 1
    assert events[-1]["summary_patch"]["pending"] == 0


def test_progress_emits_heartbeat_while_waiting():
    events = []
    heartbeat_seen = Event()

    def callback(payload):
        events.append(payload)
        if len(events) >= 2:
            heartbeat_seen.set()

    progress = RankingProgress(
        SimpleNamespace(progress_callback=callback),
        total=3,
        heartbeat_seconds=0.01,
    )

    progress.start()
    assert heartbeat_seen.wait(1)
    progress.finish({"total_targets": 3, "success_targets": 3, "failed_targets": 0})

    assert any("正在等待宿主处理当前周期" in event["text"] for event in events)
