import asyncio
from types import SimpleNamespace

from bs4 import BeautifulSoup

from src.trackers.bjshare import BJShare


class FakeResponse:
    url = "https://bj-share.info/series.php?id=1"
    text = '<a href="logout.php?auth=abcdef"></a><div class="main_column"></div>'

    def raise_for_status(self):
        pass


class FakeSearchResponse(FakeResponse):
    text = '<a href="logout.php?auth=abcdef"></a><table id="torrent_table"></table>'


class FakeSession:
    def __init__(self, response=None):
        self.calls: list[dict[str, str]] = []
        self.cookies = None
        self.response = response or FakeResponse()

    async def get(self, _url, *, params, follow_redirects):
        assert follow_redirects  # noqa: S101
        self.calls.append(params)
        return self.response


class FakeCookieValidator:
    async def load_session_cookies(self, _meta, _tracker):
        return None


def test_get_database_identifier_returns_imdb_id():
    soup = BeautifulSoup(
        '<div class="box"><div class="head">Informações</div><table><tr>'
        '<td><b>Nota IMDB:</b></td><td><a href="https://href.li/?https://www.imdb.com/title/tt999999999">IMDb</a></td>'
        "</tr></table></div>",
        "html.parser",
    )

    assert BJShare.get_database_identifier(object.__new__(BJShare), soup) == "tt999999999"  # noqa: S101


def test_get_database_identifier_returns_tmdb_id():
    soup = BeautifulSoup(
        '<div class="box"><div class="head">Informações</div><table><tr>'
        '<td><b>TMDB:</b></td><td><a href="https://href.li/?https://www.themoviedb.org/tv/999999999">TMDB</a></td>'
        "</tr></table></div>",
        "html.parser",
    )

    assert BJShare.get_database_identifier(object.__new__(BJShare), soup) == "tv/999999999"  # noqa: S101


def test_search_existing_queries_both_media_identifiers_before_title_fallback():
    tracker = object.__new__(BJShare)
    tracker.session = FakeSession()
    tracker.cookie_validator = FakeCookieValidator()
    tracker.base_url = "https://bj-share.info"
    tracker.tracker = "BJSHARE"
    meta = SimpleNamespace(category="TV", title="Example", imdb_info={"imdbID": "tt1234567"}, tmdb_id="76543")

    asyncio.run(tracker.search_existing(meta))

    assert tracker.session.calls == [{"searchstr": "tt1234567"}, {"searchstr": "tv/76543"}]  # noqa: S101


def test_search_existing_queries_title_once_without_media_identifiers():
    tracker = object.__new__(BJShare)
    tracker.session = FakeSession(FakeSearchResponse())
    tracker.cookie_validator = FakeCookieValidator()
    tracker.base_url = "https://bj-share.info"
    tracker.tracker = "BJSHARE"
    meta = SimpleNamespace(category="TV", title="Example", imdb_info={}, tmdb_id="")

    asyncio.run(tracker.search_existing(meta))

    assert tracker.session.calls == [{"searchstr": "Example"}]  # noqa: S101


def test_get_database_overview_extracts_synopsis():
    html = """
    <div class="box torrent_description">
        <div class="body">
            <blockquote>Em busca de uma vida melhor, Lu Xiao Fan deixa o interior...</blockquote>
            <blockquote class="center"><iframe class="youtube" src="http://example.com"></iframe></blockquote>
        </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    tracker = object.__new__(BJShare)
    overview = tracker.get_database_overview(soup)
    assert overview == "Em busca de uma vida melhor, Lu Xiao Fan deixa o interior..."  # noqa: S101


def test_get_overview_returns_database_overview_when_already_has_the_info():
    tracker = object.__new__(BJShare)
    tracker.main_tmdb_data = {}
    BJShare.already_has_the_info = True
    BJShare.database_overview = "Sinopse do site BJ-Share"

    result = asyncio.run(tracker.get_overview())
    assert result == "Sinopse do site BJ-Share"  # noqa: S101
