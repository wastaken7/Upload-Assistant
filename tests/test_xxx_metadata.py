# ruff: noqa: S101
"""ThePornDB and BLVCKOUT lookups for XXX releases (fictional data only)."""

import asyncio
import struct
from pathlib import Path
from typing import Any

import httpx
import pytest

from src import blvckout, tpdb
from src.meta import Meta
from src.xxx_lookup import apply_release, generated_release_name, is_scene_style_name, lookup_xxx_metadata
from src.xxx_match import (
    ReleaseFacts,
    XxxRelease,
    build_release_name,
    confident_choice,
    oshash,
    performers_from_name,
    rank,
    search_title,
    title_similarity,
)

SCENE_ID = "00000000-0000-4000-8000-000000000001"
OTHER_ID = "00000000-0000-4000-8000-000000000002"
CONFIG = {"DEFAULT": {"tpdb_api_key": "tpdb-test-key", "blvckout_api_key": ""}}


def _scene(identity: str = SCENE_ID, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "_id": identity,
        "id": 1,
        "type": "Scene",
        "title": "Sunny Afternoon",
        "date": "2026-08-21",
        "description": "<p>First line.</p><p>Second &amp; last.</p><script>ignored()</script>",
        "duration": 1830,
        "url": "https://example-studio.test/scenes/sunny-afternoon",
        "site": {"id": 5, "name": "Example Studio", "parent_id": 4, "network_id": 3, "network": {"name": "Example Network"}},
        "performers": [
            {"name": "Jane E", "parent": {"name": "Jane Example"}},
            {"name": "Mary Sample"},
        ],
        "tags": [{"name": "Outdoor"}, {"name": "Romance"}, {"name": "outdoor"}],
        "poster": "https://cdn.example.test/poster/abc?sig=123",
        "background": {"large": "https://cdn.example.test/background/abc-large.jpg", "full": "https://cdn.example.test/background/abc.jpg"},
    }
    row.update(overrides)
    return row


def _mock(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return requests


def _meta(tmp_path: Path, name: str, **values: Any) -> Meta:
    video = tmp_path / "media" / f"{name}.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"\x00" * 1024)
    meta = Meta(category="XXX", basename_no_ext=name, base_dir=str(tmp_path), path=str(video), filelist=[str(video)], unattended=True)
    for key, value in values.items():
        setattr(meta, key, value)
    return meta


# --- Provider records ------------------------------------------------------------


def test_tpdb_record_is_normalized() -> None:
    release = tpdb.normalize(_scene(), "scenes")

    assert release is not None
    assert release.ref == f"scenes/{SCENE_ID}"
    assert release.studio == "Example Studio"
    assert release.network == "Example Network"
    # A performer's canonical (parent) name wins over the alias the scene credits.
    assert release.performers == ["Jane Example", "Mary Sample"]
    assert release.tags == ["Outdoor", "Romance"]
    assert release.description == "First line.\n\nSecond & last."
    assert release.duration_minutes == 30
    assert release.year == 2026
    # A scene's "poster" is a cropped, watermarked thumbnail; the original background is used.
    assert release.poster_url == "https://cdn.example.test/background/abc-large.jpg"
    assert release.banner_url == "https://cdn.example.test/background/abc.jpg"


def test_tpdb_movie_studio_drops_catalogue_suffix_and_rejects_bad_urls() -> None:
    release = tpdb.normalize(_scene(type="Movie", site={"name": "Example Pictures (Example Store)"}, url="javascript:alert(1)", poster="http://insecure.test/a.jpg"), "scenes")

    assert release is not None
    assert release.kind == "movies"
    assert release.studio == "Example Pictures"
    assert release.url == ""
    assert release.poster_url == "https://cdn.example.test/background/abc-large.jpg"
    assert release.banner_url == ""


def test_blvckout_record_is_normalized() -> None:
    release = blvckout.normalize(
        {
            "id": "4242",
            "title": "Example Feature Vol. 3",
            "release_date": "2025-02-03",
            "production_year": 2024,
            "runtime_minutes": 125,
            "studio": "Example Pictures",
            "performers": ["Jane Example", {"name": "Mary Sample"}],
            "genres": ["Feature", "Couples"],
            "front_cover": "https://covers.example.test/front.jpg",
            "back_cover": "https://covers.example.test/back.jpg",
            "notes": "A <b>fictional</b> movie.",
        }
    )

    assert release is not None
    assert release.ref == "4242"
    assert release.year == 2024
    assert release.duration_minutes == 125
    assert release.performers == ["Jane Example", "Mary Sample"]
    assert release.poster_url == "https://covers.example.test/front.jpg"
    assert release.description == "A fictional movie."


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (f"scenes/{SCENE_ID}", ("scenes", SCENE_ID)),
        (f"movie/{SCENE_ID}", ("movies", SCENE_ID)),
        (SCENE_ID, ("scenes", SCENE_ID)),
        ("https://theporndb.net/movies/example-feature-3", ("movies", "example-feature-3")),
        ("scenes/../../etc", None),
        ("books/123", None),
    ],
)
def test_tpdb_reference(value: str, expected: tuple[str, str] | None) -> None:
    assert tpdb.parse_reference(value) == expected


def test_blvckout_reference() -> None:
    assert blvckout.parse_reference("https://blvckout.foo/releases/4242") == "4242"
    assert blvckout.parse_reference("42 42") is None


# --- Matching --------------------------------------------------------------------


def test_title_similarity_penalizes_other_volumes() -> None:
    assert title_similarity("Example Feature 3", "Example Feature 3") == 1.0
    assert title_similarity("Example Feature 3", "Example Feature 2") == pytest.approx(1 / 3)
    assert title_similarity("Example Feature", "Example Feature Hardcut") < 1.0


def test_confident_needs_title_and_date_or_studio() -> None:
    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    facts = ReleaseFacts(title="Sunny Afternoon", studio="ExampleStudio", date="2026-08-21")

    best = confident_choice(rank([release], facts))
    assert best is not None and best.release is release

    assert confident_choice(rank([release], ReleaseFacts(title="Sunny Afternoon", studio="ExampleStudio", date="2026-08-22"))) is None
    assert confident_choice(rank([release], ReleaseFacts(title="Sunny Afternoon"))) is None


def test_two_equally_good_results_are_not_confident() -> None:
    first = tpdb.normalize(_scene(), "scenes")
    second = tpdb.normalize(_scene(OTHER_ID), "scenes")
    assert first is not None and second is not None

    assert confident_choice(rank([first, second], ReleaseFacts(title="Sunny Afternoon", studio="ExampleStudio", date="2026-08-21"))) is None


def test_hash_match_is_confident_even_without_name_facts() -> None:
    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    release.via_hash = True

    best = confident_choice(rank([release], ReleaseFacts(title="clip 0001")))
    assert best is not None


def test_oshash_matches_reference_algorithm(tmp_path: Path) -> None:
    data = bytes(range(256)) * 1024
    path = tmp_path / "video.bin"
    path.write_bytes(data)
    expected = len(data)
    for block in (data[:65536], data[-65536:]):
        for (number,) in struct.iter_unpack("<Q", block):
            expected = (expected + number) % 2**64

    assert oshash(path) == f"{expected:016x}"
    small = tmp_path / "small.bin"
    small.write_bytes(b"0" * 100)
    assert oshash(small) is None


def test_search_title_drops_technical_tags() -> None:
    assert search_title("Example.Studio.26.08.21.Sunny.Afternoon.XXX.1080p.WEB-DL.MP4-EXAMPLEGRP") == "Example Studio 26 08 21 Sunny Afternoon"


def test_performers_from_dated_name() -> None:
    assert performers_from_name("ExampleStudio.26.08.21.Jane.Example.And.Mary.Sample.Sunny.Afternoon.XXX.1080p.MP4-GRP") == ["Jane Example", "Mary Sample"]
    # Content tags right after the date are a title, not a performer.
    assert performers_from_name("ExampleStudio.26.08.21.Big.Tits.Sunny.Day.XXX.1080p.MP4-GRP") == []
    assert performers_from_name("ExampleStudio.Sunny.Afternoon.XXX.1080p.MP4-GRP") == []


def test_release_names() -> None:
    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    assert build_release_name(release, resolution="1080p", container="mp4") == "ExampleStudio.26.08.21.Jane.Example.And.Mary.Sample.Sunny.Afternoon.XXX.1080p.MP4"

    movie = XxxRelease(provider="blvckout", kind="movies", id="1", title="Example Feature: Part 3", year=2024)
    assert build_release_name(movie, resolution="720p") == "Example.Feature.Part.3.2024.XXX.720p"

    assert is_scene_style_name("ExampleStudio.26.08.21.Sunny.Afternoon.XXX.1080p.MP4-GRP")
    assert not is_scene_style_name("clip_0001")
    assert not is_scene_style_name("Sunny Afternoon XXX (2026)")


# --- The lookup --------------------------------------------------------------------


def test_hash_match_fills_metadata_without_asking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tpdb-test-key"
        if request.url.path == "/scenes" and request.url.params.get("hashType") == "OSHASH":
            return httpx.Response(200, json={"data": [_scene()]})
        if request.url.path == f"/scenes/{SCENE_ID}":
            return httpx.Response(200, json={"data": _scene()})
        return httpx.Response(404)

    requests = _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "clip_0001", keywords=["outdoor"], resolution="1080p", container="mp4")
    Path(meta.filelist[0]).write_bytes(b"\x01" * 200_000)

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    # Search results carry the full record, so no detail request follows.
    assert [request.url.path for request in requests] == ["/scenes"]
    assert meta.tpdb_id == f"scenes/{SCENE_ID}"
    assert meta.title == "Sunny Afternoon"
    assert meta.publisher == "Example Studio"
    assert meta.release_date == "2026-08-21"
    assert meta.year == 2026
    assert meta.overview == "First line.\n\nSecond & last."
    assert meta.xxx_performers == ["Jane Example", "Mary Sample"]
    assert meta.keywords == ["outdoor", "Romance"]
    assert meta.artwork_url == "https://cdn.example.test/background/abc-large.jpg"
    assert meta.artwork_download_url == ""
    assert meta.artwork_banner_url == "https://cdn.example.test/background/abc.jpg"
    assert meta.xxx_source_url == "https://example-studio.test/scenes/sunny-afternoon"
    # A non-scene filename is renamed from the match.
    assert generated_release_name(meta) == "ExampleStudio.26.08.21.Jane.Example.And.Mary.Sample.Sunny.Afternoon.XXX.1080p.MP4"


def test_name_search_with_matching_date_and_studio_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/scenes" and "parse" in request.url.params:
            assert request.url.params["parse"] == "examplestudio.2026-08-21.Sunny Afternoon"
            return httpx.Response(200, json={"data": [_scene(), _scene(OTHER_ID, title="Rainy Morning", date="2025-01-01")]})
        if request.url.path == f"/scenes/{SCENE_ID}":
            return httpx.Response(200, json={"data": _scene()})
        return httpx.Response(404)

    _mock(monkeypatch, handler)
    name = "ExampleStudio.26.08.21.Sunny.Afternoon.XXX.1080p.MP4-EXAMPLEGRP"
    meta = _meta(tmp_path, name, publisher="ExampleStudio", release_date="2026-08-21", year=2026, title="Sunny Afternoon")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert meta.tpdb_id == f"scenes/{SCENE_ID}"
    # Scene-style names are kept.
    assert meta.xxx_rename is False
    assert generated_release_name(meta) == ""


def test_ambiguous_results_are_skipped_unattended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/scenes" and "parse" in request.url.params:
            # The performer matches, but the title does not.
            return httpx.Response(200, json={"data": [_scene(date="2020-01-01", title="Rainy Morning")]})
        return httpx.Response(404)

    _mock(monkeypatch, handler)
    name = "ExampleStudio.Jane.Example.Sunny.Afternoon.XXX.1080p.MP4-EXAMPLEGRP"
    meta = _meta(tmp_path, name, title="Jane Example Sunny Afternoon")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert meta.tpdb_id == ""
    assert meta.title == "Jane Example Sunny Afternoon"
    assert "xxx.match" not in meta.manual_answers


def test_answer_picks_one_of_the_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/scenes" and "parse" in request.url.params:
            # Two results with the same title and nothing else to tell them apart.
            return httpx.Response(200, json={"data": [_scene(date="2020-01-01"), _scene(OTHER_ID, date="2020-01-01", description="Chosen scene.")]})
        return httpx.Response(404)

    _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "ExampleStudio.Sunny.Afternoon.XXX.MP4-GRP", title="Sunny Afternoon", answers={"xxx.match": f"tpdb:scenes/{OTHER_ID}"})

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert meta.tpdb_id == f"scenes/{OTHER_ID}"
    assert meta.overview == "Chosen scene."
    assert meta.manual_answers["xxx.match"] == f"tpdb:scenes/{OTHER_ID}"


def test_given_id_skips_the_search_and_keeps_cli_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/movies/{SCENE_ID}"
        return httpx.Response(200, json={"data": _scene(type="Movie")})

    requests = _mock(monkeypatch, handler)
    meta = _meta(
        tmp_path,
        "custom",
        tpdb_manual=f"movies/{SCENE_ID}",
        book_publisher="Given Studio",
        publisher="Given Studio",
        manual_overview="Given synopsis",
        overview="Given synopsis",
        manual_year=2001,
        year=2001,
        explicit_poster="https://images.example.test/given.jpg",
        manual_name="Given.Name",
    )

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert len(requests) == 1
    assert meta.tpdb_id == f"movies/{SCENE_ID}"
    assert meta.publisher == "Given Studio"
    assert meta.overview == "Given synopsis"
    assert meta.year == 2001
    assert meta.artwork_url == meta.artwork_download_url == ""
    assert generated_release_name(meta) == ""


def test_blvckout_searched_for_movies_tpdb_does_not_know(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    movie = {"id": "4242", "title": "Example Feature 3", "studio": "Example Pictures", "release_date": "2024-05-06", "front_cover": "https://covers.example.test/front.jpg"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.theporndb.net":
            return httpx.Response(200, json={"data": []})
        assert request.url.host == "blvckout.foo"
        assert request.headers["Authorization"] == "Bearer blvckout-test-key"
        if request.url.path == "/api/v1/releases":
            assert request.url.params["q"] == "Example Feature 3"
            return httpx.Response(200, json={"items": [movie]})
        return httpx.Response(200, json=movie)

    _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "Example.Feature.3.XXX.DVDRip.x264-GRP", title="Example Feature 3", publisher="Example Pictures")
    config = {"DEFAULT": {"tpdb_api_key": "tpdb-test-key", "blvckout_api_key": "blvckout-test-key"}}

    asyncio.run(lookup_xxx_metadata(meta, config))

    assert meta.blvckout_id == "4242"
    assert meta.release_date == "2024-05-06"
    assert meta.artwork_url == "https://covers.example.test/front.jpg"


def test_packs_and_missing_keys_make_no_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock(monkeypatch, lambda _request: httpx.Response(500))

    pack = _meta(tmp_path, "ExampleStudio.SiteRip.XXX.1080p.MP4-GRP")
    asyncio.run(lookup_xxx_metadata(pack, CONFIG))
    no_keys = _meta(tmp_path, "ExampleStudio.26.08.21.Jane.Example.Sunny.XXX.MP4-GRP")
    asyncio.run(lookup_xxx_metadata(no_keys, {"DEFAULT": {}}))

    assert requests == []
    # Without a match, performers still come from a dated name.
    assert no_keys.xxx_performers == ["Jane Example"]


def test_rejected_key_stops_further_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock(monkeypatch, lambda _request: httpx.Response(401))
    meta = _meta(tmp_path, "ExampleStudio.Sunny.Afternoon.XXX.MP4-GRP", title="Sunny Afternoon")
    Path(meta.filelist[0]).write_bytes(b"\x01" * 200_000)

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert len(requests) == 1
    assert meta.tpdb_id == ""


def test_results_are_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "parse" in request.url.params:
            return httpx.Response(200, json={"data": [_scene()]})
        return httpx.Response(200, json={"data": _scene()})

    requests = _mock(monkeypatch, handler)
    for _ in range(2):
        meta = _meta(tmp_path, "ExampleStudio.26.08.21.Sunny.Afternoon.XXX.MP4-GRP", publisher="ExampleStudio", release_date="2026-08-21", title="Sunny Afternoon")
        asyncio.run(lookup_xxx_metadata(meta, CONFIG))
        assert meta.tpdb_id == f"scenes/{SCENE_ID}"

    assert len(requests) == 1


def test_apply_release_keeps_existing_artwork(tmp_path: Path) -> None:
    release = tpdb.normalize(_scene(poster="https://cdn.example.test/poster.jpg"), "scenes")
    assert release is not None
    meta = _meta(tmp_path, "clip", artwork_url="https://tracker.example.test/cover.jpg")

    apply_release(meta, release, rename=True)

    assert meta.artwork_url == "https://tracker.example.test/cover.jpg"
    assert meta.artwork_download_url == ""


def test_dirtybytes_sends_runtime_and_generated_name(tmp_path: Path) -> None:
    from src.trackers.dirtybytes import DirtyBytes

    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    meta = _meta(tmp_path, "clip_0001", resolution="1080p", container="mp4", video_duration=31)
    apply_release(meta, release, rename=True)
    meta.populate_cast(limit=100)
    tracker = DirtyBytes({"DEFAULT": {}, "TRACKERS": {"DIRTYBYTES": {"api_key": "x"}}})

    data = asyncio.run(tracker.get_data(meta, attach_screenshots=True, preview=True))

    assert data["runtime_minutes"] == "31"
    assert data["performers"] == "Jane Example, Mary Sample"
    assert data["studio"] == "Example Studio"
    assert asyncio.run(tracker.get_name(meta)).startswith("ExampleStudio.26.08.21.")


def test_shop_labels_and_combined_genres_are_not_tags() -> None:
    release = tpdb.normalize(_scene(tags=[{"name": "Feature"}, {"name": "Outdoor - Romance"}, {"name": "On Sale!"}, {"name": "DVD"}, {"name": "Outdoor"}]), "scenes")

    assert release is not None
    assert release.tags == ["Outdoor"]


# --- Behaviour found with real names (fictional data) -----------------------------


def test_site_and_day_search_finds_a_scene_the_full_name_misses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("parse", "")
        queries.append(query)
        if query == "examplestudio 2026-08-21":
            return httpx.Response(200, json={"data": [_scene(OTHER_ID, title="Another Scene", performers=[{"name": "Other Person"}]), _scene(title="Golden Hour")]})
        return httpx.Response(200, json={"data": []})

    _mock(monkeypatch, handler)
    # The name lists the performers and a different title than the site uses.
    meta = _meta(tmp_path, "ExampleStudio.26.08.21.Jane.Example.And.Mary.Sample.Lazy.Day.XXX.1080p.MP4-GRP", publisher="ExampleStudio", release_date="2026-08-21", title="Jane Example And Mary Sample Lazy Day")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert queries == ["examplestudio.2026-08-21.Jane Example And Mary Sample Lazy Day", "examplestudio 2026-08-21"]
    assert meta.tpdb_id == f"scenes/{SCENE_ID}"
    assert meta.title == "Golden Hour"


def test_dated_names_with_spaces_are_read() -> None:
    from src.xxx_match import dated_name_parts

    assert dated_name_parts("ExampleStudio 26.08.21 Sunny Afternoon (Jane Example) 1080p") == ("ExampleStudio", "2026-08-21", "Sunny Afternoon (Jane Example)")
    assert dated_name_parts("ExampleStudio.26.08.21.Jane.Example.Full-Length.XXX.1080p.MP4-GRP") == ("ExampleStudio", "2026-08-21", "Jane Example Full-Length")
    assert dated_name_parts("ExampleStudio 26.13.40 Not A Date") is None


def test_exact_title_on_the_same_day_matches_an_abbreviated_studio() -> None:
    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None

    # "ES18" is the initials of "Example Studio" (digits ignored).
    assert confident_choice(rank([release], ReleaseFacts(title="Sunny Afternoon", studio="ES18", date="2026-08-21"))) is not None
    # Another site with a scene of the same title that day is not accepted without asking.
    assert confident_choice(rank([release], ReleaseFacts(title="Sunny Afternoon", studio="OtherSite", date="2026-08-21"))) is None


def test_jav_product_code_is_an_exact_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jav = _scene(type="JAV", title="A Long Fictional Title", external_id="abcd-123", date="2021-01-05")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/jav"
        assert request.url.params["parse"] == "ABCD-123"
        return httpx.Response(200, json={"data": [_scene(OTHER_ID, type="JAV", external_id="abcd-124"), jav]})

    _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "ABCD-123")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert meta.tpdb_id == f"jav/{SCENE_ID}"
    assert meta.release_date == "2021-01-05"
    # Product codes are the usual name of these releases; it is kept.
    assert generated_release_name(meta) == ""


def test_creator_platform_prefix_is_not_the_studio() -> None:
    release = tpdb.normalize(_scene(site={"name": "Exampleclips: Jane Example", "short_name": "exampleclipsjaneexample"}), "scenes")

    assert release is not None
    assert (release.studio, release.network) == ("Jane Example", "Exampleclips")
    assert release.aliases == ["exampleclipsjaneexample"]


def test_movie_posters_are_the_front_cover() -> None:
    release = tpdb.normalize(_scene(type="Movie", posters={"large": "https://cdn.example.test/movie/front-large.jpg"}), "movies")

    assert release is not None
    assert release.poster_url == "https://cdn.example.test/movie/front-large.jpg"
    assert release.banner_url == ""


def test_only_a_numbered_unique_movie_title_matches_without_a_year() -> None:
    numbered = XxxRelease(provider="tpdb", kind="movies", id="1", title="Example Feature 13", studio="Example Pictures", year=2025)
    generic = XxxRelease(provider="tpdb", kind="movies", id="2", title="Example Feature", studio="Example Pictures", year=2025)

    assert confident_choice(rank([numbered], ReleaseFacts(title="Example Feature 13"))) is not None
    # A generic title may belong to an older movie with the same name.
    assert confident_choice(rank([generic], ReleaseFacts(title="Example Feature"))) is None
    assert confident_choice(rank([generic], ReleaseFacts(title="Example Feature", year=2025))) is not None


def test_studio_dash_title_names_compare_the_title() -> None:
    from src.xxx_match import score

    movie = XxxRelease(provider="tpdb", kind="movies", id="1", title="Example Feature 5", studio="Example Pictures")

    result = score(movie, ReleaseFacts(title="Example Pictures - Example Feature 5"))

    assert result.title == 1.0
    assert result.studio_match
    assert result.confident


def test_bracketed_year_searches_movies_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/movies":
            assert request.url.params["parse"] == "Example Feature"
            return httpx.Response(200, json={"data": [_scene(type="Movie", title="Example Feature", date="2014-04-21")]})
        return httpx.Response(200, json={"data": []})

    _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "Example Feature (2014)")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert paths == ["/movies"]
    assert meta.tpdb_id == f"movies/{SCENE_ID}"
    assert generated_release_name(meta) == ""


def test_signed_artwork_links_are_only_downloaded(tmp_path: Path) -> None:
    release = XxxRelease(provider="tpdb", kind="movies", id="1", title="Example Feature", poster_url="https://cdn.example.test/front?sig=1")
    meta = _meta(tmp_path, "Example Feature")

    apply_release(meta, release, rename=True)

    assert meta.artwork_url == ""
    assert meta.artwork_download_url == "https://cdn.example.test/front?sig=1"


def test_cached_records_of_an_older_format_are_not_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.metadata_cache import cache_for
    from src.xxx_match import RECORD_VERSION

    stale = XxxRelease(provider="tpdb", kind="scenes", id=SCENE_ID, title="Stale").to_dict()
    asyncio.run(cache_for(str(tmp_path)).set("tpdb", "scenes", SCENE_ID, stale))
    requests = _mock(monkeypatch, lambda _request: httpx.Response(200, json={"data": _scene()}))

    release = asyncio.run(tpdb.TpdbClient("tpdb-test-key", base_dir=str(tmp_path)).detail("scenes", SCENE_ID))

    assert RECORD_VERSION >= 2
    assert release is not None and release.title == "Sunny Afternoon"
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("name", "pack"),
    [
        ("ExampleStudio.2025.36Clips.XXX.HEVC.x265", True),
        ("[SiteRip] Example Studio [2021-2025]", True),
        ("Jane Example PACK 2026 1080p WEB-DL", True),
        ("ExampleStudio.26.08.21.Jane.Example.Clips.XXX.1080p.MP4-GRP", False),
        ("Example Feature XXX WEB-DL x264", False),
    ],
)
def test_pack_names(name: str, pack: bool) -> None:
    from src.xxx_match import is_pack_name

    assert is_pack_name(name) is pack


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("[ExampleStudio] 26.10.26 Jane Example [1080p]", ("ExampleStudio", "2026-10-26", 2026, "Jane Example")),
        ("[ExampleStudio.com / ExampleNetwork.com] Jane Example - Sunny Afternoon 2026 [1080p]", ("ExampleStudio", "", 2026, "Jane Example - Sunny Afternoon")),
        ("[ExampleStudio] Jane Example - Episode 12 2026-11-05 [1080p]", ("ExampleStudio", "2026-11-05", 2026, "Jane Example - Episode 12")),
        ("[ExampleVR.com] Jane Example - Sunny Afternoon (09.20.2025) 8K", ("ExampleVR", "2025-09-20", 2025, "Jane Example - Sunny Afternoon")),
        ("[Oculus Rift / Vive] [ExampleVR.com] Sunny Afternoon", ("ExampleVR", "", None, "Sunny Afternoon")),
        ("[rus] Example Feature", None),
        ("Example Feature (Example Pictures) (Jane Example)", None),
    ],
)
def test_bracketed_site_names(name: str, expected: tuple[str, str, int | None, str] | None) -> None:
    from src.xxx_match import bracketed_site_parts

    assert bracketed_site_parts(name) == expected


def test_bracketed_names_search_by_site_and_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params.get("parse", ""))
        if request.url.params.get("parse") == "examplestudio 2026-08-21":
            return httpx.Response(200, json={"data": [_scene(title="Sunny Afternoon")]})
        return httpx.Response(200, json={"data": []})

    _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "[ExampleStudio] 26.08.21 Jane Example [1080p]")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert "examplestudio 2026-08-21" in queries
    assert meta.tpdb_id == f"scenes/{SCENE_ID}"


def test_xxx_description_section(tmp_path: Path) -> None:
    from src.get_desc import DescriptionBuilder

    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    meta = _meta(tmp_path, "clip_0001", video_duration=31)
    apply_release(meta, release, rename=False)
    meta.populate_cast(limit=100)

    section = DescriptionBuilder("BITPORN", {"DEFAULT": {}, "TRACKERS": {"BITPORN": {}}})._build_xxx_desc_section(meta)

    assert "[b]Studio:[/b] Example Studio" in section
    assert "[b]Network:[/b] Example Network" in section
    assert "[b]Release Date:[/b] 2026-08-21" in section
    assert "[b]Performers:[/b] Jane Example, Mary Sample" in section
    assert "[b]Tags:[/b] Outdoor, Romance" in section
    assert "[b]Duration:[/b] 31 min" in section
    assert "[b]Synopsis[/b]\nFirst line.\n\nSecond & last." in section
    assert DescriptionBuilder("BITPORN", {"DEFAULT": {}, "TRACKERS": {"BITPORN": {}}})._build_xxx_desc_section(_meta(tmp_path, "x", category="MOVIE")) == ""


# --- Review fixes -----------------------------------------------------------------


def test_records_without_a_name_do_not_become_none() -> None:
    movie = blvckout.normalize({"id": "7", "title": "Example Feature", "performers": [{"name": None}, "Jane Example", {}], "genres": [{"name": None}, "Romance"]})
    scene = tpdb.normalize(_scene(tags=[{"name": None}, {"name": "Outdoor"}], performers=[{"name": None, "parent": {"name": None}}, {"name": "Mary Sample"}]), "scenes")

    assert movie is not None and scene is not None
    assert movie.performers == ["Jane Example"]
    assert movie.tags == ["Romance"]
    assert scene.tags == ["Outdoor"]
    assert scene.performers == ["Mary Sample"]


def test_cast_argument_replaces_provider_performers(tmp_path: Path) -> None:
    meta = _meta(tmp_path, "clip", manual_cast=["Given Name"], xxx_performers=["Provider Name"])

    meta.populate_cast(limit=100)

    assert meta.cast == ["Given Name"]


def test_generated_name_uses_cli_corrections(tmp_path: Path) -> None:
    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    meta = _meta(tmp_path, "clip_0001", resolution="1080p", container="mp4", book_publisher="Given Studio", manual_cast=["Given Name"])
    apply_release(meta, release, rename=True)

    assert generated_release_name(meta) == "GivenStudio.26.08.21.Given.Name.Sunny.Afternoon.XXX.1080p.MP4"


def test_a_name_with_only_the_performer_is_not_confident() -> None:
    release = tpdb.normalize(_scene(title="Some Other Scene"), "scenes")
    assert release is not None

    assert confident_choice(rank([release], ReleaseFacts(title="Jane Example"))) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ExampleStudio.26.08.21.Jane.Full-Length", "ExampleStudio.26.08.21.Jane.Full-Length"),
        ("ExampleStudio.26.08.21.Jane.XXX.1080p.MP4-EXAMPLEGRP", "ExampleStudio.26.08.21.Jane.XXX.1080p.MP4"),
        ("Example Feature XXX DVDRip x264-ExGrp", "Example Feature XXX DVDRip x264"),
    ],
)
def test_strip_group_keeps_hyphenated_titles(name: str, expected: str) -> None:
    from src.xxx_match import strip_group

    assert strip_group(name) == expected


def test_several_videos_never_get_one_scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock(monkeypatch, lambda _request: httpx.Response(200, json={"data": [_scene()]}))
    meta = _meta(tmp_path, "ExampleStudio.26.08.21.Sunny.Afternoon.XXX.MP4-GRP", publisher="ExampleStudio", release_date="2026-08-21", title="Sunny Afternoon")
    meta.filelist = [*meta.filelist, str(Path(meta.filelist[0]).with_name("second.mp4"))]

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert requests == []
    assert meta.tpdb_id == ""


def test_match_answer_none_skips_even_a_confident_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock(monkeypatch, lambda _request: httpx.Response(200, json={"data": [_scene()]}))
    meta = _meta(
        tmp_path, "ExampleStudio.26.08.21.Sunny.Afternoon.XXX.MP4-GRP", publisher="ExampleStudio", release_date="2026-08-21", title="Sunny Afternoon", answers={"xxx.match": "none"}
    )

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert requests == []
    assert meta.tpdb_id == ""
    assert meta.manual_answers["xxx.match"] == "none"


def test_match_answer_token_is_fetched_directly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/scenes/{OTHER_ID}"
        return httpx.Response(200, json={"data": _scene(OTHER_ID, title="Chosen Scene")})

    requests = _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "ExampleStudio.26.08.21.Sunny.Afternoon.XXX.MP4-GRP", manual_answers={"xxx.match": f"tpdb:scenes/{OTHER_ID}"})

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert len(requests) == 1
    assert meta.title == "Chosen Scene"


def test_rerun_without_a_result_undoes_the_earlier_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = tpdb.normalize(_scene(), "scenes")
    assert release is not None
    meta = _meta(tmp_path, "clip_0001", title="clip 0001", keywords=["solo"], resolution="1080p")
    apply_release(meta, release, rename=True)
    meta.artwork_path = str(tmp_path / "POSTER.jpg")
    assert generated_release_name(meta)

    _mock(monkeypatch, lambda _request: httpx.Response(200, json={"data": []}))
    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert meta.title == "clip 0001"
    assert meta.keywords == ["solo"]
    assert meta.publisher == meta.overview == meta.release_date == ""
    assert meta.artwork_url == meta.artwork_banner_url == meta.artwork_path == ""
    assert meta.tpdb_id == ""
    assert meta.xxx_match == {}
    assert generated_release_name(meta) == ""


def test_a_new_match_replaces_the_earlier_provider_and_artwork(tmp_path: Path) -> None:
    first = tpdb.normalize(_scene(), "scenes")
    second = blvckout.normalize({"id": "4242", "title": "Example Feature", "front_cover": "https://covers.example.test/front.jpg"})
    assert first is not None and second is not None
    meta = _meta(tmp_path, "clip_0001")

    apply_release(meta, first, rename=True)
    apply_release(meta, second, rename=True)

    assert (meta.tpdb_id, meta.blvckout_id) == ("", "4242")
    assert meta.artwork_url == "https://covers.example.test/front.jpg"
    assert meta.artwork_banner_url == ""
    assert meta.title == "Example Feature"


def test_performers_come_from_the_name_when_the_match_has_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock(monkeypatch, lambda _request: httpx.Response(200, json={"data": _scene(performers=[])}))
    meta = _meta(tmp_path, "ExampleStudio.26.08.21.Jane.Example.Sunny.XXX.MP4-GRP", tpdb_manual=f"scenes/{SCENE_ID}")

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert meta.tpdb_id == f"scenes/{SCENE_ID}"
    assert meta.xxx_performers == ["Jane Example"]


def test_free_word_search_runs_when_results_cannot_be_chosen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "q" in request.url.params:
            return httpx.Response(200, json={"data": [_scene(OTHER_ID, title="Sunny Afternoon", duration=600)]})
        # The site's scene that day is plausible, but its runtime is far from the file's.
        return httpx.Response(200, json={"data": [_scene(title="Sunny Afternoon", duration=3600)]})

    requests = _mock(monkeypatch, handler)
    meta = _meta(
        tmp_path, "ExampleStudio.26.08.21.Sunny.Afternoon.XXX.MP4-GRP", publisher="ExampleStudio", release_date="2026-08-21", title="Sunny Afternoon", video_duration=10
    )

    asyncio.run(lookup_xxx_metadata(meta, CONFIG))

    assert any("q" in request.url.params for request in requests)
    assert meta.tpdb_id == f"scenes/{OTHER_ID}"


def test_restored_blvckout_id_is_looked_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "blvckout.foo"
        assert request.url.path == "/api/v1/releases/4242"
        return httpx.Response(200, json={"id": "4242", "title": "Example Feature", "studio": "Example Pictures"})

    requests = _mock(monkeypatch, handler)
    meta = _meta(tmp_path, "Example Feature XXX WEB-DL", blvckout_manual="4242")

    asyncio.run(lookup_xxx_metadata(meta, {"DEFAULT": {"blvckout_api_key": "blvckout-test-key"}}))

    assert len(requests) == 1
    assert (meta.blvckout_id, meta.publisher) == ("4242", "Example Pictures")



@pytest.mark.parametrize("name", ["ExampleStudio.Sunny.Afternoon.Vol-2", "ExampleStudio.2026-08-21"])
def test_strip_group_keeps_numeric_suffixes(name: str) -> None:
    from src.xxx_match import strip_group

    # Digits are not a release group: a volume or a date's day stays in the name.
    assert strip_group(name) == name
