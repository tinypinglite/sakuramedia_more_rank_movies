"""JavLibrary 排行榜 HTML 适配。"""

from __future__ import annotations

import re
import time
from html.parser import HTMLParser

import httpx

JAVLIBRARY_BASE = "https://www.f101w.com"
JAVLIBRARY_BESTRATED_PATH = "vl_bestrated.php"
JAVLIBRARY_MOSTWANTED_PATH = "vl_mostwanted.php"
# 上个月=1、全部=2，映射到宿主已支持的 period 键。
JAVLIBRARY_MODE_BY_PERIOD = {"monthly": "1", "all": "2"}
JAVLIBRARY_PERIODS = tuple(JAVLIBRARY_MODE_BY_PERIOD)
JAVLIBRARY_MAX_PAGES = 25
_JAVLIBRARY_HOST = "www.f101w.com"
_PRODUCT_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,127}")


class JavLibraryRankingError(RuntimeError):
    """JavLibrary 请求或页面结构异常。"""


class _VideoIdParser(HTMLParser):
    """只提取榜单中每个 ``div.video`` 内的 ``div.id`` 番号。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[str] = []
        self._video_depth = 0
        self._id_captured = False
        self._id_depth = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag != "div":
            return
        classes = set(dict(attrs).get("class", "").split())
        if self._video_depth == 0:
            if "video" in classes:
                self._video_depth = 1
                self._id_captured = False
            return
        self._video_depth += 1
        if "id" in classes and not self._id_captured:
            self._id_captured = True
            self._id_depth = self._video_depth
            self._buffer = []

    def handle_endtag(self, tag: str):
        if tag != "div" or self._video_depth == 0:
            return
        if self._id_depth == self._video_depth:
            self._finish_id()
        self._video_depth -= 1

    def handle_data(self, data: str):
        if self._id_depth:
            self._buffer.append(data)

    def _finish_id(self):
        code = " ".join("".join(self._buffer).split())
        if code and _PRODUCT_CODE_PATTERN.fullmatch(code):
            self.items.append(code)
        self._id_depth = 0
        self._buffer = []


def parse_javlibrary_ranking(content: str) -> list[str]:
    """按榜单顺序解析番号；无 ``div.video`` 或全部缺番号时返回空列表。"""
    parser = _VideoIdParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise JavLibraryRankingError("JavLibrary 榜单 HTML 解析失败") from exc
    return parser.items


class JavLibraryClient:
    """读取 JavLibrary 高评价/最想要榜单的上个月与全部排名。"""

    def __init__(
        self,
        timeout_seconds: float = 20,
        *,
        transport=None,
        request_interval_seconds: float = 1,
        max_pages: int = JAVLIBRARY_MAX_PAGES,
    ):
        self.request_interval_seconds = request_interval_seconds
        self.max_pages = max_pages
        self._last_request_at = 0.0
        self.client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
            trust_env=transport is None,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": f"{JAVLIBRARY_BASE}/cn/",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self.client.close()

    def _request_page(self, url: str, *, page_name: str) -> str:
        delay = self.request_interval_seconds - (
            time.monotonic() - self._last_request_at
        )
        if delay > 0:
            time.sleep(delay)
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise JavLibraryRankingError(
                f"JavLibrary {page_name}请求失败"
            ) from exc
        finally:
            self._last_request_at = time.monotonic()

        if response.status_code != 200:
            raise JavLibraryRankingError(
                f"JavLibrary {page_name}返回 HTTP {response.status_code}"
            )
        if response.url.host != _JAVLIBRARY_HOST:
            raise JavLibraryRankingError(f"JavLibrary {page_name}发生未知跳转")
        return response.text

    def get_bestrated_numbers(self, period: str) -> list[str]:
        return self._get_rank_numbers(JAVLIBRARY_BESTRATED_PATH, period)

    def get_mostwanted_numbers(self, period: str) -> list[str]:
        return self._get_rank_numbers(JAVLIBRARY_MOSTWANTED_PATH, period)

    def _get_rank_numbers(self, path: str, period: str) -> list[str]:
        mode = JAVLIBRARY_MODE_BY_PERIOD.get(period.strip().lower())
        if mode is None:
            raise ValueError(f"不支持的 JavLibrary 榜单周期: {period}")

        numbers: list[str] = []
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            url = f"{JAVLIBRARY_BASE}/cn/{path}?&mode={mode}&page={page}"
            items = parse_javlibrary_ranking(
                self._request_page(url, page_name=f"榜单第 {page} 页")
            )
            if not items:
                break
            for code in items:
                if code not in seen:
                    seen.add(code)
                    numbers.append(code)
        if not numbers:
            raise JavLibraryRankingError("JavLibrary 榜单没有可用番号")
        return numbers
