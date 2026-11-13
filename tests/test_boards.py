from sakuramedia_more_rank_movies.boards import (
    JAVLIBRARY_SOURCE_KEY,
    MINNANO_SOURCE_KEY,
    build_ranking_sources,
)
from sakuramedia_more_rank_movies.providers import PerRunProviderHolder

from src.plugins import PluginRankingSource


class FakeMinnanoProvider:
    def __init__(self):
        self.calls = []

    def get_rank_numbers(self, period):
        self.calls.append(period)
        return [f"MINNANO-{period}"]


class FakeJavLibraryProvider:
    def __init__(self):
        self.bestrated_calls = []
        self.mostwanted_calls = []

    def get_bestrated_numbers(self, period):
        self.bestrated_calls.append(period)
        return [f"BESTRATED-{period}"]

    def get_mostwanted_numbers(self, period):
        self.mostwanted_calls.append(period)
        return [f"MOSTWANTED-{period}"]


def _build_sources():
    minnano = FakeMinnanoProvider()
    javlibrary = FakeJavLibraryProvider()
    sources = build_ranking_sources(
        minnano_holder=PerRunProviderHolder(factory=lambda: minnano),
        javlibrary_holder=PerRunProviderHolder(factory=lambda: javlibrary),
    )
    return sources, minnano, javlibrary


def test_ranking_sources_split_by_site():
    sources, _minnano, _javlibrary = _build_sources()

    assert MINNANO_SOURCE_KEY == "minnano_av"
    assert JAVLIBRARY_SOURCE_KEY == "javlibrary"
    assert all(isinstance(source, PluginRankingSource) for source in sources)
    assert [(source.source_key, source.name) for source in sources] == [
        (MINNANO_SOURCE_KEY, "Minnano AV"),
        (JAVLIBRARY_SOURCE_KEY, "JavLibrary"),
    ]
    assert [(board.key, board.name) for board in sources[0].boards] == [
        ("minnano_av", "Minnano AV"),
    ]
    assert [(board.key, board.name) for board in sources[1].boards] == [
        ("javlibrary_bestrated", "JavLibrary 高评价"),
        ("javlibrary_mostwanted", "JavLibrary 最想要"),
    ]


def test_ranking_sources_declare_english_names():
    sources, _minnano, _javlibrary = _build_sources()

    assert [source.name_i18n["en"] for source in sources] == [
        "Minnano AV",
        "JavLibrary",
    ]
    assert [board.name_i18n["en"] for source in sources for board in source.boards] == [
        "Minnano AV",
        "JavLibrary Top Rated",
        "JavLibrary Most Wanted",
    ]
    assert sources[1].boards[0].name_i18n["zh-CN"] == "JavLibrary 高评价"


def test_minnano_board_periods_and_fetch():
    sources, minnano, _javlibrary = _build_sources()
    board = sources[0].boards[0]

    assert board.supported_periods == ("daily", "weekly", "monthly")
    assert board.default_period == "daily"
    assert board.fetch_numbers("daily") == ["MINNANO-daily"]
    assert board.fetch_numbers("weekly") == ["MINNANO-weekly"]
    assert board.fetch_numbers("monthly") == ["MINNANO-monthly"]
    assert minnano.calls == ["daily", "weekly", "monthly"]


def test_javlibrary_boards_periods_and_fetch():
    sources, _minnano, javlibrary = _build_sources()
    bestrated, mostwanted = sources[1].boards

    for board in (bestrated, mostwanted):
        assert board.supported_periods == ("monthly", "all")
        assert board.default_period == "monthly"

    assert bestrated.fetch_numbers("monthly") == ["BESTRATED-monthly"]
    assert bestrated.fetch_numbers("all") == ["BESTRATED-all"]
    assert mostwanted.fetch_numbers("monthly") == ["MOSTWANTED-monthly"]
    assert mostwanted.fetch_numbers("all") == ["MOSTWANTED-all"]
    assert javlibrary.bestrated_calls == ["monthly", "all"]
    assert javlibrary.mostwanted_calls == ["monthly", "all"]
