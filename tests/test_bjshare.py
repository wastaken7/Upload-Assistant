import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from src.meta import Meta
from src.trackers.GAZELLE.bjshare import BJShare


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


def audio_search(category, upload_audio, header_html, *, season=1, tv_pack=True):
    tracker = object.__new__(BJShare)
    response = FakeResponse()
    response.text = (
        '<a href="logout.php?auth=abcdef"></a><div class="main_column">'
        f'<table class="torrent_table details">{header_html}'
        '<tr id="torrent123" data-torrentname="Fictional.Adventure.S01.1080p-Example">'
        '<td class="number_column nobr">1 GiB</td></tr></table></div>'
    )
    tracker.session = FakeSession(response)
    tracker.cookie_validator = FakeCookieValidator()
    meta = SimpleNamespace(
        category=category,
        title="Fictional Adventure",
        imdb_tt="tt999999999",
        tmdb_id="",
        language_checked=True,
        audio_languages={
            "Legendado": ["English"],
            "Dublado": ["Portuguese"],
            "Dual Áudio": ["English", "Portuguese"],
            "Nacional": ["Portuguese"],
        }[upload_audio],
        original_language="pt" if upload_audio == "Nacional" else "en",
        season_int=season,
        tv_pack=tv_pack,
        episode_int=0 if tv_pack else 2,
        skipping=None,
    )
    return tracker, meta


def audio_header(category, audio, *, season_class="season_01"):
    label = audio if category == "TV" else {"Dual Áudio": "Torrents Dual Áudios", "Legendado": "Torrents Legendados", "Dublado": "Torrents Dublados"}[audio]
    return f'<tr><td class="audio_header {season_class}"><strong>{label}</strong></td></tr>'


@pytest.mark.parametrize("category", ["MOVIE", "TV"])
@pytest.mark.parametrize("upload_audio", ["Legendado", "Dublado", "Dual Áudio", "Nacional"])
@pytest.mark.parametrize("existing_audio", ["Dual Áudio", "Legendado", "Dublado"])
def test_search_existing_audio_rules(category, upload_audio, existing_audio):
    tracker, meta = audio_search(category, upload_audio, audio_header(category, existing_audio))

    dupes = asyncio.run(tracker.search_existing(meta))

    blocked = (upload_audio == "Legendado" and existing_audio in ("Dual Áudio", "Dublado")) or (upload_audio == "Dublado" and existing_audio in ("Dual Áudio", "Legendado"))
    assert meta.skipping == ("BJSHARE" if blocked else None)  # noqa: S101
    assert [dupe["id"] for dupe in dupes] == ([] if blocked else ["123"])  # noqa: S101


@pytest.mark.parametrize("tv_pack", [True, False])
@pytest.mark.parametrize("season, season_class, blocked", [(1, "season_01", True), (2, "season_01", False), (None, "season_01", False), (1, "", False), (0, "season_00", True)])
def test_search_existing_audio_rules_match_season(season, season_class, blocked, tv_pack):
    tracker, meta = audio_search("TV", "Legendado", audio_header("TV", "Dual Áudio", season_class=season_class), season=season, tv_pack=tv_pack)

    dupes = asyncio.run(tracker.search_existing(meta))

    assert meta.skipping == ("BJSHARE" if blocked else None)  # noqa: S101
    assert bool(dupes) is not blocked  # noqa: S101


@pytest.mark.parametrize("category", ["MOVIE", "TV"])
@pytest.mark.parametrize(
    "header_html", ["", '<tr><td class="audio_header season_01">Desconhecido</td></tr>', "<tr><td>Dual Áudio Torrents Dual Áudios Dublado Legendado</td></tr>"]
)
def test_search_existing_audio_rules_ignore_missing_or_unrelated_labels(category, header_html):
    header_html += (
        '<tr><td><blockquote>Dual Áudio Torrents Dual Áudios Dublado Legendado</blockquote><div class="forum_post">Torrents Dublados Torrents Legendados</div></td></tr>'
    )
    tracker, meta = audio_search(category, "Legendado", header_html)

    dupes = asyncio.run(tracker.search_existing(meta))

    assert meta.skipping is None  # noqa: S101
    assert len(dupes) == 1  # noqa: S101


@pytest.mark.parametrize("category", ["MOVIE", "TV"])
def test_search_existing_audio_rules_normalize_case_and_whitespace(category):
    label = "Dual Áudio" if category == "TV" else "Torrents Dual Áudios"
    header = audio_header(category, "Dual Áudio").replace(label, "  " + "\n  ".join(label.upper().split()) + "  ")
    tracker, meta = audio_search(category, "Legendado", header)

    assert asyncio.run(tracker.search_existing(meta)) == []  # noqa: S101
    assert meta.skipping == "BJSHARE"  # noqa: S101


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
            <blockquote>Uma personagem inventada chega a uma cidade fictícia...</blockquote>
            <blockquote class="center"><iframe class="youtube" src="http://example.com"></iframe></blockquote>
        </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    tracker = object.__new__(BJShare)
    overview = tracker.get_database_overview(soup)
    assert overview == "Uma personagem inventada chega a uma cidade fictícia..."  # noqa: S101


def test_get_database_credits_extracts_creator_and_cast():
    soup = BeautifulSoup(
        '<div class="box"><div class="head">InformaÃ§Ãµes</div><table>'
        "<tr><td><b>Criador:</b></td><td>Creator Example</td></tr>"
        "<tr><td><b>Elenco:</b></td><td>Actor One, Actor Two</td></tr>"
        "</table></div>",
        "html.parser",
    )
    tracker = object.__new__(BJShare)

    assert tracker.get_database_credits(soup, "creator") == "Creator Example"  # noqa: S101
    assert tracker.get_database_credits(soup, "cast") == "Actor One, Actor Two"  # noqa: S101


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
    meta = Meta(
        {
            "language_checked": True,
            "subtitle_languages": ["Portuguese"],
            "hardcoded_subs": True,
        }
    )

    result = asyncio.run(tracker.get_subtitle(meta))
    assert result == "Queimada no vídeo"  # noqa: S101


def test_get_subtitle_embedded_portuguese():
    tracker = object.__new__(BJShare)
    tracker.tracker = "BJSHARE"
    meta = Meta(
        {
            "language_checked": True,
            "subtitle_languages": ["Portuguese"],
            "hardcoded_subs": False,
        }
    )

    result = asyncio.run(tracker.get_subtitle(meta))
    assert result == "Embutida"  # noqa: S101


def test_get_subtitle_no_portuguese():
    tracker = object.__new__(BJShare)
    tracker.tracker = "BJSHARE"
    meta = Meta(
        {
            "language_checked": True,
            "subtitle_languages": ["English"],
            "hardcoded_subs": False,
        }
    )

    result = asyncio.run(tracker.get_subtitle(meta))
    assert result == "Nenhuma"  # noqa: S101
