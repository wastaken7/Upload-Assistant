import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from src.trackers.cathoderaytube import CathodeRayTube


def tracker():
    return CathodeRayTube({"DEFAULT": {"full_mediainfo": False}, "TRACKERS": {"CATHODERAYTUBE": {"anon": True}}})


def meta(**overrides):
    values = {
        "category": "MOVIE",
        "name": "Example Movie (2010)",
        "title": "Example Movie",
        "year": "2010",
        "edition": "",
        "imdb_id": "1234567",
        "imdb_tt": "tt1234567",
        "tmdb": 123,
        "tmdb_id": None,
        "tvdb": None,
        "steam_url": "",
        "release_url": "",
        "genres": ["Drama", "Mystery"],
        "genre": "",
        "resolution": "1080p",
        "sd": False,
        "source": "BluRay",
        "type": "REMUX",
        "video_codec": "AVC",
        "audio": "AC-3 5.1",
        "channels": "5.1",
        "audio_languages": ["English"],
        "subtitle_languages": ["English"],
        "scene": False,
        "is_disc": "",
        "three_d": "",
        "extras": False,
        "has_commentary": False,
        "overview": "",
        "overview_meta": "",
        "description": "",
        "description_file_content": "",
        "description_link_content": "",
        "image_list": [],
        "menu_images": [],
        "spectrograms_images": [],
        "screens": 6,
        "base_dir": ".",
        "uuid": "test",
        "mediainfo": {},
        "discs": [],
        "ua_signature": "Upload-Assistant",
        "debug": False,
        "adult_media": False,
        "tmdb_adult_media": False,
        "nsfw": False,
        "anon": False,
        "filelist": ["Example.Movie.2010.mkv"],
        "season": 0,
        "episode": "",
        "platform": "",
        "tmdb_poster": "",
        "poster": "",
        "covers": [],
    }
    values.update(overrides)
    result = SimpleNamespace(**values)
    result.get = lambda key, default=None: values.get(key, default)
    return result


def test_maps_categories_and_builds_description():
    site = tracker()
    assert asyncio.run(site.get_upload_data(meta(), "csrf")) == {  # noqa: S101
        "submit": "true",
        "auth": "csrf",
        "category": "1",
        "MAX_FILE_SIZE": "2097152",
        "title": "Example Movie (2010)",
        "taglist": "movies, 2010, 2010s, drama, mystery, 1080p, bluray, remux, h.264, ac3, 5.1, english.audio, english.sub",
        "image": "",
        "desc": "[info]\nhttps://www.imdb.com/title/tt1234567/\nhttps://www.themoviedb.org/movie/123\n[/info]\n\n[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]Upload-Assistant[/size][/url][/align]",
        "anonymous": "1",
    }
    assert asyncio.run(site.get_upload_data(meta(category="TV"), "csrf"))["category"] == "2"  # noqa: S101
    assert asyncio.run(site.get_upload_data(meta(category="GAME"), "csrf"))["category"] == "13"  # noqa: S101


def test_formats_titles_to_crt_conventions():
    site = tracker()
    assert asyncio.run(site.get_name(meta(edition="Director's Cut"))) == "Example Movie (2010) Director's Cut"  # noqa: S101
    tv_name = asyncio.run(site.get_name(meta(category="TV", title="Example Show", season="S01", year="2001")))
    assert tv_name == "Example Show - Season 1 (2001)"  # noqa: S101
    assert asyncio.run(site.get_name(meta(category="TV", title="Example Show", season="S00", year="2001"))) == "Example Show - Specials (2001)"  # noqa: S101
    assert asyncio.run(site.get_name(meta(category="GAME", title="Example Game", year="1998", platform="PlayStation"))) == "Example Game (1998) PlayStation"  # noqa: S101


def test_uses_the_image_hosts_approved_by_crt():
    site = tracker()
    assert site.approved_image_hosts == ("ptpimg", "catbox", "imgbb", "postimages", "freeimage", "imgbox")  # noqa: S101
    assert site.image_host_mapping["catbox.moe"] == "catbox"  # noqa: S101
    assert site.image_host_mapping["postimg.cc"] == "postimages"  # noqa: S101


def test_builds_common_category_tags_from_meta():
    site = tracker()
    assert (  # noqa: S101
        site.get_tags(meta(category="TV", year="1993", source="WEB-DL", type="", video_codec="HEVC", audio="AAC Stereo", channels="2.0"))
        == "tv, 1993, 1990s, drama, mystery, 1080p, webdl, h.265, aac, stereo, english.audio, english.sub"
    )
    assert (  # noqa: S101
        site.get_tags(meta(category="GAME", year="1997", platform="Windows PC", genres=["Action", "Science Fiction"], scene=True))
        == "games, 1997, 1990s, action, scifi, pc, windows, scene"
    )


def test_renders_crt_category_description_templates():
    site = tracker()
    movie = meta(
        overview="A spoiler-free plot.",
        description="Release-specific note.",
        image_list=[{"raw_url": "https://iili.io/one.png"}],
        is_disc="BDMV",
        discs=[{"summary": "Disc Title: EXAMPLE"}],
    )
    assert asyncio.run(site.generate_description(movie)) == (  # noqa: S101
        "[info]\nhttps://www.imdb.com/title/tt1234567/\nhttps://www.themoviedb.org/movie/123\n[/info]\n"
        "[plot]\nA spoiler-free plot.\n[/plot]\n"
        "[notes]\nRelease-specific note.\n[/notes]\n"
        "[screens]\nhttps://iili.io/one.png\n[/screens]\n"
        "[details]\n[mediainfo]\nDisc Title: EXAMPLE\n[/mediainfo]\n[/details]\n\n"
        "[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]Upload-Assistant[/size][/url][/align]"
    )
    game = meta(
        category="GAME", imdb_tt="", tmdb=None, tmdb_id=None, steam_url="https://store.steampowered.com/app/1", release_url="https://example.com/game", overview="Game plot"
    )
    assert asyncio.run(site.generate_description(game)) == (  # noqa: S101
        "[info]\nhttps://store.steampowered.com/app/1\n[/info]\n[plot]\nGame plot\n[/plot]\n\n"
        "[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]Upload-Assistant[/size][/url][/align]"
    )


def test_builds_simple_advanced_search_params():
    assert tracker().get_search_params(meta()) == {  # noqa: S101
        "action": "advanced",
        "filter_cat[1]": "1",
        "title": "Example Movie",
    }
    tv_params = tracker().get_search_params(meta(category="TV", season="1", episode="2", imdb_id=0, genres=[]))
    assert tv_params["filter_cat[2]"] == "1"  # noqa: S101
    assert tv_params["title"] == "Example Movie"  # noqa: S101
    assert tracker().get_imdb_search_params(meta()) == {"action": "advanced", "searchtext": "tt1234567"}  # noqa: S101


def test_search_existing_uses_advanced_results_table():
    async def run_search():
        original_auth_token = CathodeRayTube.auth_token
        try:
            CathodeRayTube.auth_token = ""
            site = tracker()
            site.cookie_validator.load_session_cookies = AsyncMock(return_value=httpx.Cookies({"session": "test"}))
            search_html = """
            <script>var authkey = 'search-csrf-token';</script>
            <table id="torrent_table"><tbody>
              <tr class="torrent row0"><td><a href="/torrents.php?id=1">Matching Release</a></td><td class="nobr">1.25 GiB</td><td><a href="torrents.php?action=download&amp;id=1&amp;authkey=auth&amp;torrent_pass=pass">DL</a></td></tr>
              <tr class="torrent row1"><td><a href="/torrents.php?id=2">Ignored Result</a></td></tr>
            </tbody></table>
            """
            detail_html = """
            <div id="files_1"><table>
              <tr class="smallhead"><td colspan="2">/Release.Directory/</td></tr>
              <tr><td>file.mkv</td><td>1.25 GiB</td></tr>
            </table></div>
            <div class="section-details">Disc Title: RELEASE DISC<br>Disc Size: 25,000,000,000 bytes<br>Video: MPEG-4 AVC Video / 1080p<br>Audio: English / DTS-HD Master Audio</div>
            """

            requests: list[httpx.Request] = []

            async def handler(request):
                requests.append(request)
                html = detail_html if request.url.params.get("id") == "1" else search_html
                return httpx.Response(200, text=html, request=request)

            site.session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            results = await site.search_existing(meta(is_disc="BDMV"))
            assert len(requests) == 3  # noqa: S101
            assert dict(requests[0].url.params) == {"action": "advanced", "filter_cat[1]": "1", "title": "Example Movie"}  # noqa: S101
            assert str(requests[1].url) == "https://www.cathode-ray.tube/torrents.php?id=1"  # noqa: S101
            assert dict(requests[2].url.params) == {"action": "advanced", "searchtext": "tt1234567"}  # noqa: S101
            assert CathodeRayTube.auth_token == "search-csrf-token"  # noqa: S101, S105
            await site.session.aclose()
            return results
        finally:
            CathodeRayTube.auth_token = original_auth_token

    assert asyncio.run(run_search()) == [  # noqa: S101
        {
            "name": "Release.Directory",
            "size": "1.25 GiB",
            "link": "https://www.cathode-ray.tube/torrents.php?id=1",
            "download": "https://www.cathode-ray.tube/torrents.php?action=download&id=1&authkey=auth&torrent_pass=pass",
            "bd_info": "Disc Title: RELEASE DISC\nDisc Size: 25,000,000,000 bytes\nVideo: MPEG-4 AVC Video / 1080p\nAudio: English / DTS-HD Master Audio",
        }
    ]


def test_content_name_uses_the_file_for_single_file_torrents():
    html = """
    <div id="files_22000"><table>
      <tr class="smallhead"><td colspan="2">/</td></tr>
      <tr class="rowa"><td><strong>File Name</strong></td><td><strong>Size</strong></td></tr>
      <tr><td>The.Abominable.DrPhibes.1971.mkv</td><td>23.90 GiB</td></tr>
    </table></div>
    """
    assert CathodeRayTube._content_name(html) == "The.Abominable.DrPhibes.1971.mkv"  # noqa: S101


def test_enforces_known_archive_rules():
    assert asyncio.run(tracker().get_additional_checks(meta()))  # noqa: S101
    assert not asyncio.run(tracker().get_additional_checks(meta(filelist=["Example.iso"])))  # noqa: S101
    assert asyncio.run(tracker().get_additional_checks(meta(filelist=["Example.iso"], three_d="3D")))  # noqa: S101
    assert asyncio.run(tracker().get_additional_checks(meta(category="GAME", filelist=["Game.7z"])))  # noqa: S101


def test_enforces_crt_upload_rules():
    site = tracker()

    # 10-Year rule: release from 2024 (under 10 years old) fails unless edition/re-release is set
    assert not asyncio.run(site.get_additional_checks(meta(year="2024")))  # noqa: S101
    assert not asyncio.run(site.get_additional_checks(meta(category="MOVIE", release_date="2024-05-10")))  # noqa: S101
    assert not asyncio.run(site.get_additional_checks(meta(category="TV", year="2000", last_air_date="2024-05-10")))  # noqa: S101
    assert asyncio.run(site.get_additional_checks(meta(category="MOVIE", release_date="2010-05-10")))  # noqa: S101
    assert asyncio.run(site.get_additional_checks(meta(category="TV", last_air_date="2010-05-10")))  # noqa: S101
    assert asyncio.run(site.get_additional_checks(meta(year="2024", edition="Remastered")))  # noqa: S101
    assert asyncio.run(site.get_additional_checks(meta(year="1995")))  # noqa: S101

    # English requirement: must have English audio or subtitles for MOVIE/TV
    assert not asyncio.run(site.get_additional_checks(meta(audio_languages=["Japanese"], subtitle_languages=["French"])))  # noqa: S101
    assert asyncio.run(site.get_additional_checks(meta(audio_languages=["Japanese"], subtitle_languages=["English"])))  # noqa: S101

    # Sports and News forbidden in TV category
    assert not asyncio.run(site.get_additional_checks(meta(category="TV", genres=["Sports"])))  # noqa: S101
    assert not asyncio.run(site.get_additional_checks(meta(category="TV", genres=["News"])))  # noqa: S101

    # Screenshots check: minimum 6 screenshots for video content
    assert not asyncio.run(site.get_additional_checks(meta(screens=3)))  # noqa: S101

    # MediaInfo validity check
    assert not asyncio.run(site.get_additional_checks(meta(valid_mi=False)))  # noqa: S101


def test_extracts_successful_upload_url():
    request = httpx.Request("POST", "https://www.cathode-ray.tube/torrents.php?id=123&torrentid=456")
    response = httpx.Response(200, request=request)
    assert CathodeRayTube._uploaded_torrent_url(response).endswith("id=123&torrentid=456")  # noqa: S101
