"""みんなのAV 排行榜 HTML 适配。"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import httpx
from loguru import logger

MINNANO_AV = "https://www.minnano-av.com"
MINNANO_RANKING_URLS = {
    "daily": f"{MINNANO_AV}/ranking_av.php?daily",
    "weekly": f"{MINNANO_AV}/ranking_av.php",
    "monthly": f"{MINNANO_AV}/ranking_av.php?monthly",
}
MINNANO_PERIODS = tuple(MINNANO_RANKING_URLS)
_DMM_HOSTS = {"al.dmm.co.jp", "www.dmm.co.jp"}
_MINNANO_HOST = "www.minnano-av.com"
_CID_PATTERN = re.compile(r"(?:^|[/?&])cid=([^/?&#]+)", re.IGNORECASE)
_PRODUCT_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,127}")


class MinnanoRankingError(RuntimeError):
    """Minnano AV 请求或页面结构异常。"""


class MinnanoProductCodeMissingError(MinnanoRankingError):
    """Minnano 作品详情页没有正式品番。"""


@dataclass(frozen=True)
class _Link:
    href: str
    text: str
    is_title: bool


@dataclass(frozen=True)
class MinnanoRankingEntry:
    """榜单条目：DMM CID 只用于溯源，正式番号来自作品详情页。"""

    detail_url: str
    dmm_cid: str


class _RankingTableParser(HTMLParser):
    """只提取榜单表格中作品标题链接和「動画を見る」链接。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_found = False
        self.rows: list[tuple[_Link, ...]] = []
        self._table_depth = 0
        self._row: list[_Link] | None = None
        self._title_depth = 0
        self._anchor: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if tag == "table":
            classes = set(attributes.get("class", "").split())
            if self._table_depth == 0 and {"tbllist", "av"} <= classes:
                self.table_found = True
                self._table_depth = 1
            elif self._table_depth:
                self._table_depth += 1
            return
        if not self._table_depth:
            return
        if tag == "tr":
            self._finish_row()
            self._row = []
            return
        if self._row is None:
            return
        if tag == "h4" and "ttl" in set(attributes.get("class", "").split()):
            self._title_depth += 1
        if tag == "a" and attributes.get("href") and self._anchor is None:
            self._anchor = {
                "href": attributes["href"],
                "text": [],
                "is_title": self._title_depth > 0,
            }

    def handle_endtag(self, tag: str):
        if not self._table_depth:
            return
        if tag == "a" and self._anchor is not None:
            self._finish_anchor()
            return
        if tag == "h4" and self._title_depth:
            self._title_depth -= 1
            return
        if tag == "tr":
            self._finish_row()
            return
        if tag == "table":
            self._finish_row()
            self._table_depth -= 1

    def handle_data(self, data: str):
        if self._anchor is not None:
            self._anchor["text"].append(data)

    def _finish_anchor(self):
        if self._row is None or self._anchor is None:
            return
        self._row.append(
            _Link(
                href=str(self._anchor["href"]),
                text=" ".join("".join(self._anchor["text"]).split()),
                is_title=bool(self._anchor["is_title"]),
            )
        )
        self._anchor = None

    def _finish_row(self):
        if self._anchor is not None:
            self._finish_anchor()
        if self._row:
            self.rows.append(tuple(self._row))
        self._row = None
        self._title_depth = 0


def _extract_dmm_cid(href: str) -> str:
    """从 Minnano 的 DMM 联盟链接或直接 DMM 链接中提取 CID。"""
    try:
        absolute = urljoin(MINNANO_AV + "/", html.unescape(href))
        parts = urlsplit(absolute)
    except ValueError:
        return ""
    if parts.scheme != "https" or (parts.hostname or "").lower() not in _DMM_HOSTS:
        return ""

    candidates = [*parse_qs(parts.query).get("lurl", []), absolute]
    for candidate in candidates:
        match = _CID_PATTERN.search(unquote(html.unescape(candidate)))
        if not match:
            continue
        cid = match.group(1).strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,127}", cid):
            return cid
    return ""


def _extract_minnano_detail_url(href: str) -> str:
    try:
        absolute = urljoin(MINNANO_AV + "/", html.unescape(href))
        parts = urlsplit(absolute)
    except ValueError:
        return ""
    if parts.scheme != "https" or (parts.hostname or "").lower() != _MINNANO_HOST:
        return ""
    return absolute


def _parse_ranking_entries(content: str) -> list[MinnanoRankingEntry]:
    parser = _RankingTableParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise MinnanoRankingError("Minnano AV 榜单 HTML 解析失败") from exc
    if not parser.table_found:
        raise MinnanoRankingError("Minnano AV 榜单表格不存在")

    entries: list[MinnanoRankingEntry] = []
    seen: set[str] = set()
    for links in parser.rows:
        title_link = next((link for link in links if link.is_title), None)
        if title_link is None:
            continue
        video_link = next(
            (link for link in links if "動画を見る" in link.text),
            None,
        )
        dmm_cid = _extract_dmm_cid(video_link.href) if video_link else ""
        detail_url = _extract_minnano_detail_url(title_link.href)
        if dmm_cid and detail_url and dmm_cid not in seen:
            seen.add(dmm_cid)
            entries.append(MinnanoRankingEntry(detail_url=detail_url, dmm_cid=dmm_cid))
    if not entries:
        raise MinnanoRankingError("Minnano AV 榜单没有可用 DMM 番号")
    return entries


def parse_minnano_ranking_entries(content: str) -> list[MinnanoRankingEntry]:
    """解析榜单条目及其 Minnano 作品详情链接。"""
    return _parse_ranking_entries(content)


def parse_minnano_ranking(content: str) -> list[str]:
    """解析榜单中的 DMM CID，保留旧的解析接口。"""
    return [entry.dmm_cid for entry in _parse_ranking_entries(content)]


class _ProductCodeParser(HTMLParser):
    """从 Minnano 作品详情页的「品番」行提取正式番号。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.product_code = ""
        self._row: list[list[str]] | None = None
        self._cell: list[str] | None = None
        self._data_code = ""

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if tag == "tr":
            self._finish_row()
            self._row = []
            self._data_code = ""
            return
        if tag == "td" and self._row is not None:
            self._cell = []
            return
        if tag == "span" and self._cell is not None:
            classes = set(attributes.get("class", "").split())
            if "product-code-copy" in classes:
                self._data_code = attributes.get("data-code", "") or ""

    def handle_endtag(self, tag: str):
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
            return
        if tag == "tr":
            self._finish_row()

    def handle_data(self, data: str):
        if self._cell is not None:
            self._cell.append(data)

    def _finish_row(self):
        if self._row is None:
            return
        if self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
        cells = [" ".join(cell).strip() for cell in self._row]
        if cells and cells[0] == "品番":
            candidate = self._data_code or (cells[1] if len(cells) > 1 else "")
            match = _PRODUCT_CODE_PATTERN.search(candidate)
            if match:
                self.product_code = match.group(0).upper()
        self._row = None
        self._data_code = ""


def parse_minnano_product_code(content: str) -> str:
    """解析 Minnano 作品详情页中的正式番号。"""
    parser = _ProductCodeParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise MinnanoRankingError("Minnano AV 作品详情页解析失败") from exc
    if not parser.product_code:
        raise MinnanoProductCodeMissingError("Minnano AV 作品详情页没有可用正式番号")
    return parser.product_code


class MinnanoAvClient:
    """读取 Minnano AV 日/周/月榜单。"""

    def __init__(
        self,
        timeout_seconds: float = 20,
        *,
        transport=None,
        request_interval_seconds: float = 1,
    ):
        self.request_interval_seconds = request_interval_seconds
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
                "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
                "Referer": f"{MINNANO_AV}/",
            },
        )
        self._product_code_cache: dict[str, str] = {}

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
            raise MinnanoRankingError(f"Minnano AV {page_name}请求失败") from exc
        finally:
            self._last_request_at = time.monotonic()

        if response.status_code != 200:
            raise MinnanoRankingError(
                f"Minnano AV {page_name}返回 HTTP {response.status_code}"
            )
        if response.url.host != _MINNANO_HOST:
            raise MinnanoRankingError(f"Minnano AV {page_name}发生未知跳转")
        return response.text

    def _get_product_code(self, detail_url: str) -> str:
        cached = self._product_code_cache.get(detail_url)
        if cached is not None:
            return cached
        product_code = parse_minnano_product_code(
            self._request_page(detail_url, page_name="作品详情页")
        )
        self._product_code_cache[detail_url] = product_code
        return product_code

    def get_rank_numbers(self, period: str) -> list[str]:
        normalized_period = period.strip().lower()
        url = MINNANO_RANKING_URLS.get(normalized_period)
        if url is None:
            raise ValueError(f"不支持的 Minnano AV 榜单周期: {period}")

        entries = parse_minnano_ranking_entries(
            self._request_page(url, page_name="榜单")
        )
        numbers: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            try:
                product_code = self._get_product_code(entry.detail_url)
            except MinnanoProductCodeMissingError as exc:
                logger.warning(
                    "Minnano AV 作品没有正式番号，跳过 dmm_cid={} detail_url={} detail={}",
                    entry.dmm_cid,
                    entry.detail_url,
                    exc,
                )
                continue
            if product_code not in seen:
                seen.add(product_code)
                numbers.append(product_code)
        if not numbers:
            raise MinnanoRankingError("Minnano AV 榜单没有可用正式番号")
        return numbers
