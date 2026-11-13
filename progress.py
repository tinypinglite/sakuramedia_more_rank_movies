"""排行榜任务进度适配：周期级 current/total + 全局累计摘要。"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from .translations import runtime_text


class RankingProgress:
    """把宿主排行榜同步结果转换成规范的可读进度。

    宿主同步接口的最小可观察单元是一个 board+period，因此这里不伪造影片级
    进度；current/total 表示已完成/总周期数，summary_patch 始终是累计值。
    """

    def __init__(
        self,
        reporter,
        *,
        total: int,
        heartbeat_seconds: float = 2,
        i18n: Any = None,
    ):
        if total < 1:
            raise ValueError("排行榜进度 total 必须大于 0")
        self.reporter = reporter
        self.total = total
        self.current = 0
        self.heartbeat_seconds = heartbeat_seconds
        self.i18n = i18n
        self._succeeded = 0
        self._failed = 0
        self._skipped = 0
        self._metrics: dict[str, int] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    @staticmethod
    def _as_nonnegative_int(value, default: int = 0) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    def _callback(self):
        return getattr(self.reporter, "progress_callback", None)

    def _summary_locked(self) -> dict[str, int]:
        processed = self._succeeded + self._failed
        summary = {
            "processed": processed,
            "succeeded": self._succeeded,
            "skipped": self._skipped,
            "failed": self._failed,
            "pending": max(self.total - processed, 0),
            "retried": self._metrics.get("retried", 0),
        }
        summary.update(self._metrics)
        return summary

    def _text_locked(self, action_key: str) -> str:
        summary = self._summary_locked()
        params = {
            "action": runtime_text(self.i18n, action_key),
            "current": self.current,
            "total": self.total,
            "succeeded": summary["succeeded"],
            "failed": summary["failed"],
            "pending": summary["pending"],
            "skipped": summary["skipped"],
        }
        key = "progress.text_with_skipped" if summary["skipped"] else "progress.text"
        return runtime_text(self.i18n, key, **params)[:255]

    def _emit_locked(self, action_key: str) -> None:
        callback = self._callback()
        if callback is None:
            return
        callback(
            {
                "current": self.current,
                "total": self.total,
                "text": self._text_locked(action_key),
                "summary_patch": self._summary_locked(),
            }
        )

    def _apply_stats_locked(
        self,
        stats: Mapping,
        *,
        assume_success: bool = False,
    ) -> None:
        has_target_counts = "success_targets" in stats or "failed_targets" in stats
        if has_target_counts:
            self._succeeded = self._as_nonnegative_int(stats.get("success_targets"))
            self._failed = self._as_nonnegative_int(stats.get("failed_targets"))
        elif assume_success:
            self._succeeded = max(self._succeeded, self.total)
        self._skipped = self._as_nonnegative_int(
            stats.get("skipped_movies"), self._skipped
        )
        for key in (
            "total_targets",
            "fetched_numbers",
            "imported_movies",
            "local_hit_movies",
            "skipped_movies",
            "stored_items",
            "retried",
        ):
            if key in stats:
                self._metrics[key] = self._as_nonnegative_int(stats.get(key))

    def start(self) -> None:
        """阶段开始立即上报，并启动无数量变化时的心跳。"""
        with self._lock:
            self._emit_locked("progress.action.waiting_first")
        if self._callback() is not None and self.heartbeat_seconds > 0:
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat,
                name="more-rank-movies-progress",
                daemon=True,
            )
            self._heartbeat_thread.start()

    def callback(self, payload: Mapping | None) -> None:
        """接收宿主周期级进度并立即转发为规范文本。"""
        payload = payload if isinstance(payload, Mapping) else {}
        raw_total = self._as_nonnegative_int(payload.get("total"))
        raw_current = self._as_nonnegative_int(payload.get("current"))
        stats = payload.get("summary_patch")
        with self._lock:
            if raw_total:
                self.total = raw_total
            self.current = min(max(self.current, raw_current), self.total)
            if isinstance(stats, Mapping):
                self._apply_stats_locked(stats)
            if self.current >= self.total:
                action_key = "progress.action.all_done"
            elif self.current:
                action_key = "progress.action.cycle_done"
            else:
                action_key = "progress.action.waiting_first"
            self._emit_locked(action_key)

    def finish(self, result: Mapping | None = None) -> None:
        """阶段完成，current 到 total，摘要保留宿主返回的最终累计值。"""
        self._stop_heartbeat()
        with self._lock:
            if isinstance(result, Mapping):
                raw_total = self._as_nonnegative_int(result.get("total_targets"))
                if raw_total:
                    self.total = raw_total
                self._apply_stats_locked(result, assume_success=True)
            self.current = self.total
            self._emit_locked("progress.action.finished")

    def fail(self) -> None:
        """任务级异常时收口进度，不掩盖原异常。"""
        self._stop_heartbeat()
        with self._lock:
            self.current = min(self.current + 1, self.total)
            self._failed += 1
            self._emit_locked("progress.action.aborted")

    def _heartbeat(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            with self._lock:
                if self.current >= self.total:
                    return
                self._emit_locked("progress.action.waiting_host")

    def _stop_heartbeat(self) -> None:
        self._stop.set()
        thread = self._heartbeat_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.2)
