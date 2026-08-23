import asyncio
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup
from PIL import Image

from src.meta import Meta
from src.trackers.bjshare import BJShare


class FakeResponse:
    url = "https://bj-share.info/series.php?id=1"
    text = '<a href="logout.php?auth=abcdef"></a><div class="main_column"></div>'

    def raise_for_status(self):
        pass


class FakeSearchResponse(FakeResponse):
    text = '<a href="logout.php?auth=abcdef"></a><table id="torrent_table"></table>'


def test_get_screenshots_converts_webp_to_png(tmp_path: Path) -> None:
    screenshots = tmp_path / "tmp" / "release" / "screenshots"
    screenshots.mkdir(parents=True)
    Image.new("RGB", (2, 2), "red").save(screenshots / "Release-0.webp", format="WEBP")
    uploaded: list[tuple[bytes, str]] = []
    tracker = object.__new__(BJShare)

    async def fake_img_host(image_bytes: bytes, filename: str) -> str:
        uploaded.append((image_bytes, filename))
        return "https://img.example/release-0.png"

    tracker.img_host = fake_img_host
    result = asyncio.run(tracker.get_screenshots(Meta({"base_dir": str(tmp_path), "uuid": "release"})))

    assert result == ["https://img.example/release-0.png"]  # noqa: S101
    assert uploaded[0][1] == "Release-0.png"  # noqa: S101
    assert uploaded[0][0].startswith(b"\x89PNG\r\n\x1a\n")  # noqa: S101


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


def test_search_existing_queries_only_media_identifiers():
    tracker = object.__new__(BJShare)
    tracker.session = FakeSession()
    tracker.cookie_validator = FakeCookieValidator()
    tracker.base_url = "https://bj-share.info"
    tracker.tracker = "BJSHARE"
    meta = SimpleNamespace(category="TV", title="Example", imdb_tt="tt1234567", tmdb_id="76543")

    asyncio.run(tracker.search_existing(meta))

    assert tracker.session.calls == [{"searchstr": "tt1234567"}, {"searchstr": "tv/76543"}]  # noqa: S101


def test_search_existing_does_not_query_title_without_media_identifiers():
    tracker = object.__new__(BJShare)
    tracker.session = FakeSession(FakeSearchResponse())
    tracker.cookie_validator = FakeCookieValidator()
    tracker.base_url = "https://bj-share.info"
    tracker.tracker = "BJSHARE"
    meta = SimpleNamespace(category="TV", title="Example", imdb_tt="", tmdb_id="")

    asyncio.run(tracker.search_existing(meta))

    assert tracker.session.calls == []  # noqa: S101


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


def test_get_database_credits_extracts_creator_and_cast():
    soup = BeautifulSoup(
        '<div class="box"><div class="head">InformaÃ§Ãµes</div><table>'
        '<tr><td><b>Criador:</b></td><td>Ron Howard</td></tr>'
        '<tr><td><b>Elenco:</b></td><td>Russell Crowe, RenÃ©e Zellweger</td></tr>'
        "</table></div>",
        "html.parser",
    )
    tracker = object.__new__(BJShare)

    assert tracker.get_database_credits(soup, "creator") == "Ron Howard"  # noqa: S101
    assert tracker.get_database_credits(soup, "cast") == "Russell Crowe, RenÃ©e Zellweger"  # noqa: S101


def test_get_overview_returns_database_overview_when_already_has_the_info():
    tracker = object.__new__(BJShare)
    tracker.main_tmdb_data = {}
    BJShare.already_has_the_info = True
    BJShare.database_overview = "Sinopse do site BJ-Share"

    result = asyncio.run(tracker.get_overview())
    assert result == "Sinopse do site BJ-Share"  # noqa: S101


def test_get_subtitle_hardcoded_portuguese():
    tracker = object.__new__(BJShare)
    tracker.tracker = "BJSHARE"
    meta = Meta({
        "language_checked": True,
        "subtitle_languages": ["Portuguese"],
        "hardcoded_subs": True,
    })

    result = asyncio.run(tracker.get_subtitle(meta))
    assert result == "Queimada no vídeo"  # noqa: S101


def test_get_subtitle_embedded_portuguese():
    tracker = object.__new__(BJShare)
    tracker.tracker = "BJSHARE"
    meta = Meta({
        "language_checked": True,
        "subtitle_languages": ["Portuguese"],
        "hardcoded_subs": False,
    })

    result = asyncio.run(tracker.get_subtitle(meta))
    assert result == "Embutida"  # noqa: S101


def test_get_subtitle_no_portuguese():
    tracker = object.__new__(BJShare)
    tracker.tracker = "BJSHARE"
    meta = Meta({
        "language_checked": True,
        "subtitle_languages": ["English"],
        "hardcoded_subs": False,
    })

    result = asyncio.run(tracker.get_subtitle(meta))
    assert result == "Nenhuma"  # noqa: S101

