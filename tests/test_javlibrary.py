from pathlib import Path

import httpx
import pytest
from sakuramedia_more_rank_movies.javlibrary import (
    JAVLIBRARY_BASE,
    JavLibraryClient,
    JavLibraryRankingError,
    parse_javlibrary_ranking,
)

from src.i18n.locale import LanguageState, reset_language_state, set_language_state
from src.plugins.i18n import PluginI18n

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

RANKING_HTML = """
<div class="videothumblist">
<div class="videos">
<div class="video" id="vid_a"><a href="./a.html" title="A"><div class="id">SNOS-145</div><img src="x.jpg" /><div class="title" >A</div></a><div class="toolbar"></div></div>
<div class="video" id="vid_b"><a href="./b.html" title="B"><div class="id">SAVR-01185</div><div class="title" >B</div></a></div>
<div class="video" id="vid_c"><a href="./c.html" title="C"><div class="title" >无番号</div></a></div>
<div class="video" id="vid_d"><a href="./d.html" title="D"><div class="id">SNOS-145</div><div class="title" >重复</div></a></div>
</div>
</div>
"""


def _page(*codes):
    blocks = "".join(
        f'<div class="video" id="vid_{i}"><a href="./{i}.html">'
        f'<div class="id">{code}</div><div class="title">t</div></a></div>'
        for i, code in enumerate(codes)
    )
    return f'<div class="videos">{blocks}</div>'


def test_parse_javlibrary_ranking_keeps_order_and_skips_missing_id():
    assert parse_javlibrary_ranking(RANKING_HTML) == [
        "SNOS-145",
        "SAVR-01185",
        "SNOS-145",
    ]


def test_parse_javlibrary_ranking_without_video_returns_empty():
    assert parse_javlibrary_ranking("<html><body>blocked</body></html>") == []


def test_client_uses_mode_and_path_for_each_board_and_period():
    first_page_urls = []

    def handler(request):
        if request.url.params["page"] == "1":
            first_page_urls.append(str(request.url))
            return httpx.Response(200, text=_page("CODE-1"), request=request)
        return httpx.Response(200, text="<html></html>", request=request)

    with JavLibraryClient(
        transport=httpx.MockTransport(handler),
        request_interval_seconds=0,
    ) as client:
        assert client.get_bestrated_numbers("monthly") == ["CODE-1"]
        assert client.get_bestrated_numbers("all") == ["CODE-1"]
        assert client.get_mostwanted_numbers("monthly") == ["CODE-1"]
        assert client.get_mostwanted_numbers("all") == ["CODE-1"]

    assert [url.split("?")[1] for url in first_page_urls] == [
        "&mode=1&page=1",
        "&mode=2&page=1",
        "&mode=1&page=1",
        "&mode=2&page=1",
    ]
    assert [url.split("?")[0] for url in first_page_urls] == [
        f"{JAVLIBRARY_BASE}/cn/vl_bestrated.php",
        f"{JAVLIBRARY_BASE}/cn/vl_bestrated.php",
        f"{JAVLIBRARY_BASE}/cn/vl_mostwanted.php",
        f"{JAVLIBRARY_BASE}/cn/vl_mostwanted.php",
    ]


def test_client_paginates_and_dedups_until_empty_page():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(
                200,
                text=_page("AAA-001", "BBB-002"),
                request=request,
            )
        if page == 2:
            return httpx.Response(
                200,
                text=_page("BBB-002", "CCC-003"),
                request=request,
            )
        return httpx.Response(200, text="<html></html>", request=request)

    with JavLibraryClient(
        transport=httpx.MockTransport(handler),
        request_interval_seconds=0,
    ) as client:
        assert client.get_bestrated_numbers("all") == [
            "AAA-001",
            "BBB-002",
            "CCC-003",
        ]

    assert [url.split("page=")[1] for url in requests] == ["1", "2", "3"]


def test_client_rejects_empty_result():
    def handler(request):
        return httpx.Response(200, text="<html></html>", request=request)

    with (
        JavLibraryClient(
            transport=httpx.MockTransport(handler),
            request_interval_seconds=0,
        ) as client,
        pytest.raises(JavLibraryRankingError, match="可用番号"),
    ):
        client.get_bestrated_numbers("monthly")


def test_client_surfaces_http_errors():
    def handler(request):
        return httpx.Response(503, request=request)

    with (
        JavLibraryClient(
            transport=httpx.MockTransport(handler),
            request_interval_seconds=0,
        ) as client,
        pytest.raises(JavLibraryRankingError, match="HTTP 503"),
    ):
        client.get_bestrated_numbers("monthly")


def test_client_rejects_unknown_period():
    with (
        JavLibraryClient(request_interval_seconds=0) as client,
        pytest.raises(ValueError, match="不支持"),
    ):
        client.get_bestrated_numbers("yearly")


def test_client_errors_follow_english_language():
    def handler(request):
        return httpx.Response(200, text="<html></html>", request=request)

    i18n = PluginI18n("sakuramedia_more_rank_movies", PLUGIN_ROOT)
    token = set_language_state(LanguageState(header_language="en"))
    try:
        with (
            JavLibraryClient(
                transport=httpx.MockTransport(handler),
                request_interval_seconds=0,
                i18n=i18n,
            ) as client,
            pytest.raises(
                JavLibraryRankingError,
                match=r"JavLibrary ranking has no usable movie numbers",
            ),
        ):
            client.get_bestrated_numbers("monthly")

        with (
            JavLibraryClient(request_interval_seconds=0, i18n=i18n) as client,
            pytest.raises(
                ValueError,
                match=r"Unsupported JavLibrary ranking period: yearly",
            ),
        ):
            client.get_bestrated_numbers("yearly")
    finally:
        reset_language_state(token)
