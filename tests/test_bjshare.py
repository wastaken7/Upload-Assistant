import asyncio
from types import SimpleNamespace

from bs4 import BeautifulSoup

from src.trackers.bjshare import BJShare


class FakeResponse:
    url = "https://bj-share.info/series.php?id=1"
    text = '<a href="logout.php?auth=abcdef"></a><div class="main_column"></div>'

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.calls: list[dict[str, str]] = []
        self.cookies = None

    async def get(self, _url, *, params, follow_redirects):
        assert follow_redirects  # noqa: S101
        self.calls.append(params)
        return FakeResponse()


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
