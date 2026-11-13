# ruff: noqa: S101
import asyncio
import runpy
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from src import uploadscreens
from src.clients import Clients
from src.description_review import save_review
from src.meta import Meta
from src.trackers.LUMINANCE import Luminance, normalize_tag
from src.trackers.LUMINANCE.happyfappy import HappyFappy
from src.trackers.LUMINANCE.kufirc import Kufirc
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, get_tracker_framework, tracker_class_map

SCENE = {
    "provider": "tpdb",
    "kind": "scenes",
    "id": "1",
    "title": "Afternoon Lesson",
    "date": "2026-03-04",
    "year": 2026,
    "studio": "Fakestudio",
    "performers": ["Jane Example", "Mock Performer"],
    "tags": ["Blowjob", "Big Tits", "Cowgirl"],
    "description": "Jane and Mock spend the afternoon together.",
}


def config(**default: Any) -> dict[str, Any]:
    return {"DEFAULT": dict(default), "TRACKERS": {"HAPPYFAPPY": {"announce_url": "https://tracker.example/a/announce", "anon": False}, "KUFIRC": {"announce_url": "http://tracker.example:1/b/announce", "anon": True}}}


def scene_meta(**values: Any) -> Meta:
    defaults: dict[str, Any] = {
        "category": "XXX",
        "basename_no_ext": "Fakestudio.26.03.04.Jane.Example.Afternoon.Lesson.XXX.1080p",
        "name": "Fakestudio 26 03 04 Jane Example Afternoon Lesson XXX 1080p",
        "resolution": "1080p",
        "container": "mp4",
        "filelist": ["/media/Fakestudio.26.03.04.Jane.Example.Afternoon.Lesson.XXX.1080p.mp4"],
        "xxx_match": dict(SCENE),
        "publisher": "Fakestudio",
        "cast": ["Jane Example", "Mock Performer"],
        "keywords": ["Blowjob", "Big Tits", "Cowgirl"],
        "overview": "Jane and Mock spend the afternoon together.",
        "source_size": 1024 * 1024 * 1000,
    }
    defaults.update(values)
    return Meta(**defaults)


def test_registration_and_example_config() -> None:
    example = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["HAPPYFAPPY"] is HappyFappy
    assert tracker_class_map["KUFIRC"] is Kufirc
    assert STATIC_AUTH_TYPES["HAPPYFAPPY"] == STATIC_AUTH_TYPES["KUFIRC"] == "cookies"
    assert get_tracker_framework("KUFIRC") == "LUMINANCE"
    assert example["TRACKERS"]["HAPPYFAPPY"]["cli_alias"] == "HF"
    assert example["TRACKERS"]["KUFIRC"]["cli_alias"] == "KUF"
    assert "luminapix_api" in example["DEFAULT"]


@pytest.mark.parametrize(("category", "kept"), [("XXX", True), ("MOVIE", False)])
def test_only_xxx_is_supported(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["HAPPYFAPPY", "KUFIRC"])
    TrackerSetup(config()).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["HAPPYFAPPY", "KUFIRC"]) is kept


def test_name_follows_studio_performer_title_order() -> None:
    name = asyncio.run(HappyFappy(config()).get_name(scene_meta()))
    assert name == "[Fakestudio] Jane Example, Mock Performer - Afternoon Lesson (2026-03-04) [1080p]"


def test_name_skips_performers_in_title_and_labels_vr_by_width() -> None:
    release = {**SCENE, "title": "Jane Example Rides Again"}
    meta = scene_meta(xxx_match=release, keywords=["VR"], resolution="4320p", video_width=5760, cast=["Jane Example"])
    assert asyncio.run(HappyFappy(config()).get_name(meta)) == "[Fakestudio] Jane Example Rides Again (2026-03-04) [6K VR]"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        # A scene-style file name is kept as it is.
        ({}, "Fakestudio.26.03.04.Jane.Example.Afternoon.Lesson.XXX.1080p"),
        # A verified scene name wins over the file name.
        ({"scene_name": "Fakestudio.26.03.04.Jane.Example.Afternoon.Lesson.XXX.1080p.MP4-FAKEGRP"}, "Fakestudio.26.03.04.Jane.Example.Afternoon.Lesson.XXX.1080p.MP4-FAKEGRP"),
        # Without a scene name the shared title format is used.
        ({"basename_no_ext": "jane example afternoon lesson"}, "[Fakestudio] Jane Example, Mock Performer - Afternoon Lesson (2026-03-04) [1080p]"),
        ({"manual_name": "Custom Title"}, "Custom Title"),
    ],
)
def test_kufirc_uses_the_scene_name_when_there_is_one(values: dict[str, Any], expected: str) -> None:
    assert asyncio.run(Kufirc(config()).get_name(scene_meta(**values))) == expected


def test_happyfappy_keeps_its_title_format_for_scene_names() -> None:
    meta = scene_meta(scene_name="Fakestudio.26.03.04.Jane.Example.Afternoon.Lesson.XXX.1080p.MP4-FAKEGRP")
    assert asyncio.run(HappyFappy(config()).get_name(meta)) == "[Fakestudio] Jane Example, Mock Performer - Afternoon Lesson (2026-03-04) [1080p]"


def test_name_without_a_match_keeps_the_release_name_and_manual_name_wins() -> None:
    site = HappyFappy(config())
    assert asyncio.run(site.get_name(scene_meta(xxx_match=None))) == "Fakestudio 26 03 04 Jane Example Afternoon Lesson XXX 1080p"
    assert asyncio.run(site.get_name(scene_meta(manual_name=" Custom Title "))) == "Custom Title"


def test_tags_are_dotted_and_space_separated() -> None:
    tags = HappyFappy(config()).get_tags(scene_meta()).split()
    assert tags == ["jane.example", "mock.performer", "fakestudio", "blowjob", "big.tits", "cowgirl", "1080p", "mp4", "2026"]
    assert normalize_tag("Rock & Roll's Best") == "rock.and.rolls.best"
    # Accented names keep their letters.
    assert normalize_tag("Éva Júlia") == "eva.julia"
    assert normalize_tag("Zoë Rock" + chr(0x2019) + "n") == "zoe.rockn"


def test_validation_saves_the_loaded_cookie_jar(tmp_path: Path) -> None:
    """The site can rotate its session cookie; the jar it was written into must be saved."""
    import http.cookiejar

    async def run() -> tuple[Any, Any]:
        site = Kufirc(config())
        jar = http.cookiejar.MozillaCookieJar(str(tmp_path / "KUFIRC.txt"))
        site.cookie_validator.load_session_cookies = AsyncMock(return_value=jar)
        save = AsyncMock()
        site.cookie_validator.save_session_cookies = save
        site.session = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text='<form id="upload_table"><input name="auth" value="tok"></form>', request=request))
        )
        try:
            assert await site.validate_credentials(scene_meta())
        finally:
            await site.session.aclose()
        return save.await_args.args[1], jar

    saved, jar = asyncio.run(run())
    assert saved is jar


@pytest.mark.parametrize(
    ("values", "hf", "kufirc"),
    [
        ({}, "Pron", "Hardcore"),
        ({"basename_no_ext": "Fakestudio.Pack.XXX.1080p"}, "Packs", "Megapack"),
        ({"basename_no_ext": "Fakestudio.SiteRip.XXX.1080p"}, "Packs", "Siterip"),
        ({"keywords": ["VR"]}, "VR", "VR"),
        ({"xxx_match": {**SCENE, "kind": "jav", "code": "ABC-123"}}, "Asian", "Asian"),
        ({"keywords": ["Lesbian", "Kissing"], "xxx_match": {**SCENE, "tags": ["Lesbian"]}}, "Lesbian", "Lesbian"),
        ({"basename_no_ext": "Fakestudio.Interracial.Scene.XXX.1080p"}, "Interracial", "Interracial"),
        ({"xxx_match": {**SCENE, "studio": "OnlyFans: Jane"}}, "Fansite", "Hardcore"),
        ({"basename_no_ext": "Fakestudio.Big.Tits.Teacher.XXX.1080p"}, "Pron", "Big Tits"),
        ({"xxx_match": {**SCENE, "kind": "movies", "year": 1985}, "year": 1985}, "Retro", "Classic"),
        ({"xxx_match": {**SCENE, "kind": "movies", "year": 2020}}, "Pron", "Feature"),
        ({"filelist": ["/media/set/001.jpg", "/media/set/002.jpg"], "basename_no_ext": "Fakestudio.Pics"}, "Pics", "Image"),
        ({"filelist": ["/media/game/Game.exe"]}, "Games", "XXX Games"),
    ],
)
def test_categories(values: dict[str, Any], hf: str, kufirc: str) -> None:
    meta = scene_meta(**values)
    assert HappyFappy(config()).category_name(meta) == hf
    assert Kufirc(config()).category_name(meta) == kufirc
    assert HappyFappy(config()).get_category_id(meta) == HappyFappy.category_ids[hf]


def test_category_edit_has_no_release_category_advice() -> None:
    """The site category is a genre within XXX; changing it in the Web UI rebuilds nothing else."""
    preview = asyncio.run(Kufirc(config()).get_payload_preview(scene_meta()))
    category = preview.find("category")
    assert category is not None
    assert category.role == ""


def test_kufirc_never_offers_the_animal_category() -> None:
    assert "5" not in Kufirc.category_ids.values()


def test_search_queries_and_result_parsing() -> None:
    site = HappyFappy(config())
    assert site.get_title_query(scene_meta()) == {"action": "advanced", "title": "Afternoon Lesson"}
    assert site.get_title_query(scene_meta(xxx_match={**SCENE, "kind": "jav", "code": "ABC-123"})) == {"action": "advanced", "title": "ABC-123"}
    assert site.get_size_query(scene_meta()) == {"action": "advanced", "sizeall": "1000.00", "sizetype": "mb", "sizerange": "0.01"}
    assert site.get_size_query(scene_meta(source_size=0)) == {}
    html = """
    <table id="torrent_table"><tr class="colhead"><td></td><td>Name</td></tr>
      <tr class="torrent rowb"><td class="cats_col"></td><td><a href="/torrents.php?action=download&amp;id=7&amp;authkey=x">DL</a>
        <a href="/torrents.php?id=7">[Fakestudio] Jane Example - Afternoon Lesson [1080p]</a></td>
        <td class="center">1</td><td class="center">0</td><td class="nobr">1 hour ago</td><td class="nobr">1000.00 MiB</td><td>1</td><td>2</td><td>0</td><td>anon</td></tr>
    </table>"""
    assert Luminance.parse_search_results(html, "https://site.example") == [
        {
            "id": "7",
            "name": "[Fakestudio] Jane Example - Afternoon Lesson [1080p]",
            "size": "1000.00 MiB",
            "file_count": 1,
            "files": [],
            "link": "https://site.example/torrents.php?id=7",
        }
    ]


def test_search_existing_merges_both_searches() -> None:
    async def run() -> tuple[list[dict[str, Any]], list[httpx.Request]]:
        site = Kufirc(config())
        site.cookie_validator.load_session_cookies = AsyncMock(return_value=httpx.Cookies({"sid": "test"}))
        requests: list[httpx.Request] = []
        same = '<tr class="torrent"><td></td><td><a href="/torrents.php?id=3">Same Release</a></td><td>1</td><td>0</td><td>now</td><td>1000 MiB</td></tr>'
        # Same size but a different number of files: not the same release.
        other = '<tr class="torrent"><td></td><td><a href="/torrents.php?id=4">Other Pack</a></td><td>12</td><td>0</td><td>now</td><td>1000 MiB</td></tr>'

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            rows = same + other if "sizeall" in request.url.params else same
            return httpx.Response(200, text=f'<table id="torrent_table">{rows}</table>', request=request)

        site.session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await site.search_existing(scene_meta()), requests
        finally:
            await site.session.aclose()

    results, requests = asyncio.run(run())
    assert len(requests) == 2
    assert [result["link"] for result in results] == ["https://kufirc.com/torrents.php?id=3"]


def test_finds_the_personal_download_link_of_an_upload() -> None:
    html = (
        '<a href="/torrents.php?action=download&amp;id=71&amp;authkey=a&amp;torrent_pass=p">other</a>'
        '<a href="/torrents.php?action=download&amp;id=7&amp;authkey=a&amp;torrent_pass=p">DL</a>'
    )
    url = Luminance.find_download_url(html, "https://site.example/torrents.php?id=7", "7")
    assert url == "https://site.example/torrents.php?action=download&id=7&authkey=a&torrent_pass=p"
    assert Luminance.find_download_url("<p>none</p>", "https://site.example/torrents.php?id=7", "7") == ""


def test_auth_token_and_login_detection() -> None:
    assert Luminance.extract_auth_token('<form id="upload_table"><input type="hidden" name="auth" value="abc123"></form>') == "abc123"
    assert Luminance.extract_auth_token("<html>no form</html>") == ""


def test_upload_posts_the_luminance_form(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> dict[str, Any]:
        site = HappyFappy(config(img_host_1="imgbox"))
        site.cookie_validator.load_session_cookies = AsyncMock(return_value=httpx.Cookies({"sid": "test"}))
        site.session = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text='<form id="upload_table"><input name="auth" value="tok"></form>', request=request))
        )
        monkeypatch.setattr(site, "host_cover", AsyncMock(return_value="https://images2.imgbox.com/aa/bb/cover_o.png"))
        monkeypatch.setattr(site, "generate_description", AsyncMock(return_value="Description"))
        monkeypatch.setattr(site, "get_mediainfo", AsyncMock(return_value="General"))
        handle_upload = AsyncMock(return_value=True)
        monkeypatch.setattr(site.cookie_auth_uploader, "handle_upload", handle_upload)
        meta = scene_meta(tracker_status={}, rehosted_artwork_url="https://images2.imgbox.com/aa/bb/cover_o.png")
        try:
            assert await site.upload(meta)
        finally:
            await site.session.aclose()
        return handle_upload.call_args.kwargs

    kwargs = asyncio.run(run())
    data = kwargs["data"]
    assert kwargs["torrent_field_name"] == "file_input"
    assert kwargs["upload_url"] == "https://www.happyfappy.net/upload.php"
    assert data["auth"] == "tok"
    assert data["category"] == "1"
    assert data["image"] == "https://images2.imgbox.com/aa/bb/cover_o.png"
    assert data["mediainfo"] == "General"
    assert data["anonymous"] == "0"
    assert data["taglist"].startswith("jane.example ")


CORRECTED_UPLOAD_PAGE = """<html><head><title>Warning :: Site</title></head><body>
<a href="/torrents.php?type=seeding&amp;userid=1">Up</a>
<div id="content"><h2>Warning</h2><div class="box pad shadow">
Your torrent has been uploaded however, it has been corrected to resolve the following issues:
<ul><li>The source tag was not set</li></ul>
You <span class="red">must</span> download the torrent file from <a href="torrents.php?id=4242">here</a> before you can start seeding.
</div></div></body></html>"""


@pytest.mark.parametrize("downloaded", [True, False])
def test_upload_corrected_by_the_site_counts_and_seeds_the_site_copy(monkeypatch: pytest.MonkeyPatch, downloaded: bool) -> None:
    """The site can accept an upload but rewrite its .torrent; the app must report success and seed the site's copy."""

    async def run() -> tuple[bool, dict[str, Any], AsyncMock]:
        site = HappyFappy(config())
        site.cookie_validator.load_session_cookies = AsyncMock(return_value=httpx.Cookies({"sid": "test"}))
        site.session = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text='<form id="upload_table"><input name="auth" value="tok"></form>', request=request))
        )
        monkeypatch.setattr(site, "host_cover", AsyncMock(return_value=""))
        monkeypatch.setattr(site, "generate_description", AsyncMock(return_value="Description"))
        monkeypatch.setattr(site, "get_mediainfo", AsyncMock(return_value="General"))
        download = AsyncMock(return_value=downloaded)
        monkeypatch.setattr(site, "download_site_torrent", download)
        uploader = site.cookie_auth_uploader
        monkeypatch.setattr(uploader, "load_torrent_file", AsyncMock(return_value={"file_input": ("x.torrent", b"d4:infode", "application/x-bittorrent")}))
        monkeypatch.setattr(uploader.common, "create_torrent_ready_to_seed", AsyncMock(return_value=None))

        real_client = httpx.AsyncClient

        def post_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=CORRECTED_UPLOAD_PAGE, request=request)

        monkeypatch.setattr("src.cookie_auth.httpx.AsyncClient", lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(post_handler), **kwargs))
        meta = scene_meta(tracker_status={}, debug=False)
        try:
            uploaded = await site.upload(meta)
        finally:
            await site.session.aclose()
        return uploaded, meta.tracker_status["HAPPYFAPPY"], download

    uploaded, status, download = asyncio.run(run())
    assert uploaded is True
    assert status["torrent_id"] == "4242"
    download.assert_awaited_once()
    assert download.await_args.args[1] == "4242"
    if downloaded:
        assert status["status_message"] == "Torrent uploaded successfully."
        assert "skip_client_injection" not in status
    else:
        assert "https://www.happyfappy.net/torrents.php?id=4242" in status["status_message"]
        # The local copy may not match the site's, so it must not reach the torrent client.
        assert status["skip_client_injection"] is True


def test_kufirc_puts_mediainfo_in_the_description_and_converts_alignment(monkeypatch: pytest.MonkeyPatch) -> None:
    site = Kufirc(config())
    monkeypatch.setattr(
        "src.trackers.LUMINANCE.DescriptionBuilder.general_description_generator",
        AsyncMock(return_value="[center][b]Studio:[/b] Fakestudio[/center]\n[h2]Title[/h2]"),
    )
    monkeypatch.setattr(site, "get_mediainfo", AsyncMock(return_value="General\nFormat : MPEG-4"))
    description = asyncio.run(site.generate_description(scene_meta()))
    assert "[center]" not in description
    assert "[align=center][b]Studio:[/b] Fakestudio[/align]" in description
    assert description.endswith("[spoiler=MediaInfo][code]General\nFormat : MPEG-4[/code][/spoiler]")
    assert "mediainfo" not in asyncio.run(site.get_data(scene_meta(), "tok", preview=True))


def test_rule_checks() -> None:
    hf = HappyFappy(config())
    assert hf.rule_warnings(scene_meta(filelist=["/media/scene.rar"])) == ["Archived video files are not allowed: .rar."]
    assert hf.rule_warnings(scene_meta()) == []
    assert hf.rule_notes(scene_meta()) == []
    notes = hf.rule_notes(scene_meta(overview="", xxx_match=None, keywords=[], cast=[], publisher="", container=""))
    assert any("at least 5 tag" in note for note in notes)
    assert any("English text description" in note for note in notes)

    kufirc = Kufirc(config())
    assert any("luminapix.eu" in warning for warning in kufirc.rule_warnings(scene_meta()))
    assert Kufirc(config(img_host_1="luminapix", luminapix_api="key")).rule_warnings(scene_meta()) == []

    # Images already on luminapix.eu need no upload key.
    hosted = scene_meta(
        rehosted_artwork_url="https://luminapix.eu/images/2026/01/01/cover.png",
        image_list=[dict.fromkeys(("img_url", "raw_url", "web_url"), "https://luminapix.eu/images/2026/01/01/sheet.png")],
    )
    assert not any("luminapix.eu" in warning for warning in kufirc.rule_warnings(hosted))
    half_hosted = scene_meta(
        rehosted_artwork_url="https://luminapix.eu/images/2026/01/01/cover.png",
        image_list=[dict.fromkeys(("img_url", "raw_url", "web_url"), "https://img.example/sheet.png")],
    )
    assert any("luminapix.eu" in warning for warning in kufirc.rule_warnings(half_hosted))

    # Failures are only reported; the tracker status check asks whether to upload anyway.
    assert asyncio.run(kufirc.get_additional_checks(scene_meta())) is False
    assert asyncio.run(hf.get_additional_checks(scene_meta())) is True


def test_only_rendered_text_counts_as_a_description() -> None:
    """A provider description that is not in the upload (no synopsis) does not satisfy HappyFappy."""
    meta = scene_meta(overview="", xxx_match={**SCENE, "description": "Only on the provider."})
    assert any("English text description" in note for note in HappyFappy(config()).rule_notes(meta))


def test_description_saved_in_the_webui_editor_counts_as_text(tmp_path: Path) -> None:
    meta = scene_meta(overview="", xxx_match=None, base_dir=str(tmp_path), uuid="release")
    temp_dir = tmp_path / "tmp" / "release"
    temp_dir.mkdir(parents=True)
    hf = HappyFappy(config())
    assert any("English text description" in note for note in hf.rule_notes(meta))

    save_review(temp_dir, "[center]Jane and Mock spend the afternoon together.[/center]")
    assert not any("English text description" in note for note in hf.rule_notes(meta))

    # A draft made only of images is still no description.
    save_review(temp_dir, "[img]https://img.example/sheet.png[/img]", expected_version=1)
    assert any("English text description" in note for note in hf.rule_notes(meta))


def test_hf_rejects_picture_sets_bundled_with_video(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.write_bytes(b"0")
    images = [tmp_path / f"{index:03}.jpg" for index in range(20)]
    for image in images:
        image.write_bytes(b"0")
    warnings = HappyFappy(config()).rule_warnings(scene_meta(filelist=[str(video), *map(str, images)]))
    assert any("picture set" in warning for warning in warnings)


def test_cover_must_come_from_an_approved_host() -> None:
    site = Kufirc(config())
    assert site.get_cover(scene_meta(artwork_url="https://cdn.example/poster.jpg")) == ""
    assert site.get_cover(scene_meta(rehosted_artwork_url="https://luminapix.eu/images/2026/01/01/cover.png")) == "https://luminapix.eu/images/2026/01/01/cover.png"


def test_hosts_local_cover_on_an_approved_host(tmp_path: Path) -> None:
    async def run() -> tuple[str, Meta]:
        site = HappyFappy(config(img_host_1="imgbb", img_host_2="pixhost"))
        cover = tmp_path / "POSTER.png"
        cover.write_bytes(b"cover")
        site.rehost_images_manager.uploadscreens_manager.upload_screens = AsyncMock(return_value=([{"raw_url": "https://img1.pixhost.to/images/1/cover.png"}], 1))
        meta = scene_meta(artwork_path=str(cover))
        return await site.host_cover(meta), meta

    url, meta = asyncio.run(run())
    assert url == "https://img1.pixhost.to/images/1/cover.png"
    assert meta.rehosted_artwork_url == url


def test_client_comment_ids() -> None:
    clients = Clients(config())
    ids = clients._extract_tracker_ids_from_comment("https://www.happyfappy.net/torrents.php?id=1001 https://kufirc.com/torrents.php?id=2002")
    assert ids == {"happyfappy": "1001", "kufirc": "2002"}


def test_luminapix_upload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "sheet.png"
    image.write_bytes(b"png")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = {"status_code": 200, "image": {"url": "https://luminapix.eu/images/2026/01/01/sheet.png", "url_viewer": "https://luminapix.eu/image/abc"}}
        return httpx.Response(200, json=body, request=request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(uploadscreens.httpx, "AsyncClient", lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(uploadscreens.upload_luminapix(str(image), {"DEFAULT": {"luminapix_api": "key"}}, 30))
    assert result["status"] == "success"
    assert result["raw_url"] == "https://luminapix.eu/images/2026/01/01/sheet.png"
    assert result["web_url"] == "https://luminapix.eu/image/abc"
    assert captured[0].headers["X-API-Key"] == "key"
    assert asyncio.run(uploadscreens.upload_luminapix(str(image), {"DEFAULT": {}}, 30))["status"] == "failed"
