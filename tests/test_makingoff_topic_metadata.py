import asyncio
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from src.trackers.makingoff import MakingOff


def tracker():
    return MakingOff({"TRACKERS": {"MAKINGOFF": {}}})


def meta(**overrides):
    values = {
        "name": "Example Movie 2026 WEB-DL",
        "basename_no_ext": "Example Movie 2026 WEB-DL",
        "source": "WEB",
        "type": "WEBDL",
        "is_disc": "",
        "filelist": [],
        "year": 2026,
        "video_width": 1920,
        "video_height": 1080,
        "resolution": "1080p",
        "origin_country": ["US"],
        "production_countries": [],
        "original_language": "en",
        "original_title": "Original Title",
        "title": "Original Title",
        "uuid": "example",
    }
    values.update(overrides)
    if "name" in overrides and "basename_no_ext" not in overrides:
        values["basename_no_ext"] = overrides["name"]
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("overrides", "release_format", "prefix"),
    [
        ({"name": "Movie BluRay REMUX", "type": "REMUX"}, "Blu-ray Remux", "Blu-ray"),
        ({"name": "Movie WEB-DL", "type": "WEBDL"}, "WEB-DL", "WEB"),
        ({"name": "Movie", "type": "DISC", "is_disc": "DVD"}, "DVD Full", "DVD"),
        ({"name": "Movie SATRip", "type": "SATRIP"}, "SATRip", "TV"),
        ({"name": "Movie VHSRip", "type": "VHSRIP"}, "VHSRip", "VHS"),
        ({"name": "Movie Unknown", "type": "UNKNOWN"}, "Indefinido", "OUTRO"),
    ],
)
def test_release_format_selects_the_required_topic_prefix(overrides, release_format, prefix):
    site = tracker()
    movie = meta(**overrides)

    assert site._localizer_video_quality(movie) == release_format  # noqa: S101
    assert site._topic_prefix_category(movie) == prefix  # noqa: S101


def test_prefix_ids_are_discovered_from_the_current_forum_form():
    soup = BeautifulSoup(
        """
        <select name="prefix_id">
          <option value="0">(Sem prefixo)</option>
          <option value="41">Blu-ray</option>
          <option value="42">WEB</option>
        </select>
        <label for="prefix-dvd">DVD</label><input id="prefix-dvd" name="prefix_id" value="43">
        """,
        "html.parser",
    )

    assert MakingOff._parse_prefix_ids(soup) == {"blu-ray": "41", "web": "42", "dvd": "43"}  # noqa: S101


def test_topic_payload_contains_required_prefix_and_index_tags():
    site = tracker()
    movie = meta()
    post_body = "[ANO]2026[/ANO][TAG=director]Director Name[/TAG][TAG=country]Estados Unidos[/TAG][TAG=genre]Drama[/TAG]"
    topic_tags = site._topic_tags(movie, post_body)

    fields = site.get_topic_fields(
        forum_id=26,
        csrf_token="token",  # noqa: S106
        attachment_hash="hash",
        attachment_hash_combined="combined",
        topic_title="Título / Original Title (2026)",
        post_body=post_body,
        prefix_id="42",
        topic_tags=topic_tags,
    )

    assert fields["prefix_id"] == "42"  # noqa: S101
    assert fields["tags"] == "2026, Director Name, Estados Unidos, Drama"  # noqa: S101
    assert fields["title"] == "Título / Original Title (2026)"  # noqa: S101


def test_topic_title_no_longer_uses_the_legacy_hidef_prefix():
    site = tracker()
    movie = meta()

    async def display_title(_meta):
        return "Título"

    site._resolve_display_title = display_title

    assert asyncio.run(site.get_name(movie)) == "Título / Original Title (2026)"  # noqa: S101


def test_automatic_trailer_prefers_official_brazilian_youtube_video():
    pt_br = {
        "videos": {
            "results": [
                {"site": "YouTube", "type": "Trailer", "key": "unofficial", "name": "Trailer"},
                {
                    "site": "YouTube",
                    "type": "Trailer",
                    "key": "official-br",
                    "name": "Trailer Oficial",
                    "official": True,
                    "iso_3166_1": "BR",
                    "iso_639_1": "pt",
                },
            ]
        }
    }
    en_us = {"videos": {"results": [{"site": "YouTube", "type": "Trailer", "key": "official-en", "name": "Official Trailer", "official": True}]}}

    assert MakingOff._tmdb_youtube_trailer(pt_br, en_us) == "https://www.youtube.com/watch?v=official-br"  # noqa: S101
