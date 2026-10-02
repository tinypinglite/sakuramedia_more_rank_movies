import httpx
import pytest
from sakuramedia_more_rank_movies.minnano import (
    MinnanoAvClient,
    MinnanoRankingError,
    parse_minnano_product_code,
    parse_minnano_ranking,
    parse_minnano_ranking_entries,
)

RANKING_HTML = """
<table class="tbllist av">
  <tr><th>順位</th><th>作品名</th></tr>
  <tr>
    <td class="rnkno">1</td>
    <td><h4 class="ttl"><a href="av001.html">第一部</a></h4></td>
    <td><a href="https://al.dmm.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2Fdigital%2Fvideoa%2F-%2Fdetail%2F%3D%2Fcid%3Dh_086hthd00242%2F&amp;af_id=minav1-001">動画を見る</a></td>
  </tr>
  <tr>
    <td class="rnkno">2</td>
    <td><h4 class="ttl"><a href="av002.html">第二部</a></h4></td>
    <td><a href="https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=ABC-002/">動画を見る</a></td>
  </tr>
  <tr>
    <td class="rnkno">3</td>
    <td><h4 class="ttl"><a href="av003.html">重复第一部</a></h4></td>
    <td><a href="https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=h_086hthd00242/">動画を見る</a></td>
  </tr>
  <tr>
    <td class="rnkno">4</td>
    <td><h4 class="ttl"><a href="av004.html">无商品链接</a></h4></td>
    <td><a href="av004.html">作品情報</a></td>
  </tr>
</table>
"""

DETAIL_HTML = {
    "/av001.html": """
    <table class="prof-table">
      <tr><td>作品名</td><td>第一部</td></tr>
      <tr><td>品番</td><td><span class="product-code-copy" data-code="HTHD-242">HTHD-242</span></td></tr>
    </table>
    """,
    "/av002.html": """
    <table class="prof-table">
      <tr><td>品番</td><td>ABC-002</td></tr>
    </table>
    """,
}


def test_parse_minnano_ranking_extracts_cids_in_rank_order():
    assert parse_minnano_ranking(RANKING_HTML) == [
        "h_086hthd00242",
        "ABC-002",
    ]


def test_parse_minnano_ranking_entries_keeps_detail_urls():
    entries = parse_minnano_ranking_entries(RANKING_HTML)

    assert [(entry.detail_url, entry.dmm_cid) for entry in entries] == [
        ("https://www.minnano-av.com/av001.html", "h_086hthd00242"),
        ("https://www.minnano-av.com/av002.html", "ABC-002"),
    ]


def test_parse_minnano_product_code_reads_product_code_row():
    assert parse_minnano_product_code(DETAIL_HTML["/av001.html"]) == "HTHD-242"
    assert parse_minnano_product_code(DETAIL_HTML["/av002.html"]) == "ABC-002"

    with pytest.raises(MinnanoRankingError, match="正式番号"):
        parse_minnano_product_code(
            "<table class='prof-table'><tr><td>作品名</td></tr></table>"
        )


def test_parse_minnano_ranking_rejects_missing_or_empty_table():
    with pytest.raises(MinnanoRankingError, match="表格"):
        parse_minnano_ranking("<html><body>blocked</body></html>")
    with pytest.raises(MinnanoRankingError, match="可用 DMM 番号"):
        parse_minnano_ranking(
            '<table class="tbllist av"><tr><td>没有商品</td></tr></table>'
        )


def test_client_uses_daily_weekly_monthly_urls():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path != "/ranking_av.php":
            return httpx.Response(
                200,
                text=DETAIL_HTML[request.url.path],
                request=request,
            )
        return httpx.Response(200, text=RANKING_HTML, request=request)

    with MinnanoAvClient(
        transport=httpx.MockTransport(handler),
        request_interval_seconds=0,
    ) as client:
        for period in ("daily", "weekly", "monthly"):
            assert client.get_rank_numbers(period) == ["HTHD-242", "ABC-002"]

    assert [str(request.url) for request in requests] == [
        "https://www.minnano-av.com/ranking_av.php?daily",
        "https://www.minnano-av.com/av001.html",
        "https://www.minnano-av.com/av002.html",
        "https://www.minnano-av.com/ranking_av.php",
        "https://www.minnano-av.com/ranking_av.php?monthly",
    ]


def test_client_skips_entries_without_product_code_but_rejects_empty_result():
    def handler(request):
        if request.url.path == "/ranking_av.php":
            return httpx.Response(200, text=RANKING_HTML, request=request)
        if request.url.path == "/av001.html":
            return httpx.Response(
                200,
                text=DETAIL_HTML["/av001.html"],
                request=request,
            )
        return httpx.Response(
            200,
            text="<table class='prof-table'><tr><td>作品名</td></tr></table>",
            request=request,
        )

    with MinnanoAvClient(
        transport=httpx.MockTransport(handler),
        request_interval_seconds=0,
    ) as client:
        assert client.get_rank_numbers("daily") == ["HTHD-242"]

    def empty_handler(request):
        if request.url.path == "/ranking_av.php":
            return httpx.Response(200, text=RANKING_HTML, request=request)
        return httpx.Response(
            200,
            text="<table class='prof-table'><tr><td>作品名</td></tr></table>",
            request=request,
        )

    with (
        MinnanoAvClient(
            transport=httpx.MockTransport(empty_handler),
            request_interval_seconds=0,
        ) as client,
        pytest.raises(MinnanoRankingError, match="可用正式番号"),
    ):
        client.get_rank_numbers("daily")


def test_client_surfaces_http_errors():
    def handler(request):
        return httpx.Response(503, request=request)

    with (
        MinnanoAvClient(
            transport=httpx.MockTransport(handler),
            request_interval_seconds=0,
        ) as client,
        pytest.raises(MinnanoRankingError, match="HTTP 503"),
    ):
        client.get_rank_numbers("daily")


def test_client_rejects_unknown_period():
    with (
        MinnanoAvClient(request_interval_seconds=0) as client,
        pytest.raises(ValueError, match="不支持"),
    ):
        client.get_rank_numbers("yearly")
