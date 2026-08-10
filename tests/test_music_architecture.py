"""Regression tests for Orpheus MUSIC release/edition boundaries."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from src.args import Args
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.music.analyzer import MusicReleaseAnalyzer, _clean, _format_for
from src.music.models import AudioTrack, MetadataSource, MusicRelease
from src.music.prep import _apply_music_cli_overrides, _discogs_ids, _find_discogs_release, _music_override_year, enrich_music_from_orpheus
from src.music.sources import DiscogsEnricher, MusicBrainzEnricher, _music_cache_path, _write_music_cache
from src.prep import Prep
from src.trackers.orpheus import Orpheus
from src.uphelper import _music_confirmation_lines
from web_ui.server import _extract_execution_preview


def test_description_builder_renders_music_release_details():
    meta = Meta(
        category="MUSIC",
        music_release={
            "fields": {
                "artists": {"value": ["Artist One", "Artist Two"]},
                "album": {"value": "Example Album"},
                "year": {"value": "1999"},
                "release_year": {"value": "2024"},
                "edition": {"value": "Deluxe Edition"},
                "release_type": {"value": "Album"},
                "media": {"value": "WEB"},
                "release_label": {"value": "Example Records"},
                "release_catalogue_number": {"value": "EX-123"},
                "genres": {"value": ["Rock", "Alternative"]},
                "track_count": {"value": 2},
                "disc_count": {"value": 1},
                "format": {"value": "FLAC"},
            },
            "tracks": [
                {"format": "FLAC", "codec": "FLAC", "bit_depth": 24, "sample_rate": 96000, "channels": 2, "bitrate": 3000000},
                {"format": "FLAC", "codec": "FLAC", "bit_depth": 24, "sample_rate": 96000, "channels": 2, "bitrate": 3100000},
            ],
        },
    )
    builder = DescriptionBuilder("PEERGARDEN", {"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    result = builder._build_music_desc_section(meta)

    assert "[h2]Music Details[/h2]" in result
    assert "Artist One, Artist Two" in result
    assert "Original Release Year" in result and "1999" in result
    assert "Release Year" in result and "2024" in result
    assert "24-bit" in result
    assert "96 kHz" in result
    assert "Stereo" in result
    assert "3000 kbps, 3100 kbps" in result


def test_description_builder_renders_external_music_ids_as_links():
    musicbrainz_release = "c0d17e85-3a36-4dc8-9a88-c188a5e78b0d"
    musicbrainz_group = "3bdb2b21-f6f5-3f8b-a1e0-067f8bb71940"
    meta = Meta(
        category="MUSIC",
        music_release={
            "external_ids": {
                "musicbrainz_release": musicbrainz_release,
                "musicbrainz_release_group": musicbrainz_group,
                "discogs_release": "https://www.discogs.com/release/1791341-example-release",
                "discogs_master": "master/28700",
                "invalid": "ignored",
            },
        },
    )
    builder = DescriptionBuilder("PEERGARDEN", {"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    result = builder._build_music_desc_section(meta)

    assert "External IDs" in result
    assert f"[url=https://musicbrainz.org/release/{musicbrainz_release}]{musicbrainz_release}[/url]" in result
    assert f"[url=https://musicbrainz.org/release-group/{musicbrainz_group}]{musicbrainz_group}[/url]" in result
    assert "[url=https://www.discogs.com/release/1791341]1791341[/url]" in result
    assert "[url=https://www.discogs.com/master/28700]28700[/url]" in result


def test_description_generator_includes_music_release_details():
    meta = Meta(
        category="MUSIC",
        music_release={
            "fields": {
                "artists": {"value": ["Artist One", "Artist Two"]},
                "album": {"value": "Example Album"},
            },
            "tracks": [{"format": "FLAC", "sample_rate": 96000}],
        },
    )
    builder = DescriptionBuilder("PEERGARDEN", {"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    result = asyncio.run(
        builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_header=False,
            custom_signature=False,
            description=False,
            game=False,
            languages=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            tonemapped_header=False,
            tv_info=False,
            ua_signature=False,
            user_description=False,
            music=True,
        )
    )

    assert "[h2]Music Details[/h2]" in result
    assert "Artist One, Artist Two" in result
    assert "Example Album" in result
    assert "96 kHz" in result


def test_description_builder_skips_invalid_music_technical_values():
    meta = Meta(
        category="MUSIC",
        music_release={
            "fields": {"album": {"value": "Example Album"}},
            "tracks": [
                {"format": "FLAC", "sample_rate": 96000},
                {"format": ["invalid"], "sample_rate": "not-a-number"},
            ],
        },
    )
    builder = DescriptionBuilder("PEERGARDEN", {"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    result = builder._build_music_desc_section(meta)

    assert "FLAC" in result
    assert "96 kHz" in result
    assert "not-a-number" not in result


def test_rip_log_establishes_cd_media_without_using_filename_alone(tmp_path):
    log = tmp_path / "release.log"
    log.write_text("Exact Audio Copy V1.6 from 23. October 2020\n", encoding="utf-8")
    release = MusicRelease(root=str(tmp_path))
    release.auxiliary.logs.append(log.name)

    MusicReleaseAnalyzer()._infer_media_from_logs(release)

    assert release.get("media") == "CD"
    assert release.fields["media"].source == MetadataSource.AUXILIARY


def test_external_metadata_does_not_create_file_tag_conflicts():
    release = MusicRelease(root=".")
    release.set_field("album", "Embedded Album", MetadataSource.FILE_TAG, 1.0)
    release.set_field("album", "External Album", MetadataSource.EXTERNAL, 0.8)
    release.set_field("album", "Different Embedded Album", MetadataSource.FILE_TAG, 0.8)

    assert release.get("album") == "Embedded Album"
    assert release.conflicts["album"] == ["Embedded Album", "Different Embedded Album"]


def test_mp4_is_not_an_audio_release_extension(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not-an-audio-release")

    release = MusicReleaseAnalyzer().analyze(video)

    assert not release.tracks


def test_original_group_year_and_explicit_remaster_edition_are_distinct():
    release = MusicRelease(root=".")
    release.tracks.append(
        AudioTrack(
            path="track.flac",
            relative_path="track.flac",
            format="FLAC",
            codec="FLAC",
            artist="Led Zeppelin",
            album_artist="Led Zeppelin",
            album="Led Zeppelin II",
            title="Whole Lotta Love",
            date="2014",
            tags={"albumartist": ["Led Zeppelin"]},
        )
    )

    MusicReleaseAnalyzer()._derive_release_fields(release, "(1969) Led Zeppelin II [2014 Remaster]")

    assert release.get("year") == "1969"
    assert release.get("release_year") == "2014"
    assert release.get("edition_year") == "2014"
    assert release.get("edition") == "Remaster"
    assert "year" not in release.conflicts


def test_edition_only_folder_does_not_promote_edition_year_to_group_year():
    release = MusicRelease(root=".")
    release.tracks.append(
        AudioTrack(
            path="track.flac",
            relative_path="track.flac",
            format="FLAC",
            codec="FLAC",
            artist="Led Zeppelin",
            album_artist="Led Zeppelin",
            album="Coda",
            title="We're Gonna Groove",
            date="2015",
            tags={"albumartist": ["Led Zeppelin"]},
        )
    )

    MusicReleaseAnalyzer()._derive_release_fields(release, "Led Zeppelin - Coda [2015 Deluxe Edition] (FLAC)")

    assert not release.get("year")
    assert release.get("release_year") == "2015"
    assert release.get("edition_year") == "2015"
    assert release.get("edition") == "Deluxe Edition"


def test_web_directory_brackets_populate_release_not_edition_metadata():
    release = MusicRelease(root=".")
    release.tracks.append(
        AudioTrack(
            path="track.flac",
            relative_path="track.flac",
            format="FLAC",
            codec="FLAC",
            artist="The Carter Family",
            album_artist="The Carter Family & Johnny Cash",
            album="Keep On The Sunny Side",
            title="Keep On The Sunny Side",
            date="1963",
            tags={"albumartist": ["The Carter Family & Johnny Cash"]},
        )
    )

    MusicReleaseAnalyzer()._derive_release_fields(
        release,
        "1963 - The Carter Family & Johnny Cash - Keep On The Sunny Side [2014 WEB FLAC][Columbia Nashville Legacy][886444460446]",
    )

    assert release.get("year") == "1963"
    assert release.get("release_year") == "2014"
    assert release.get("release_label") == "Columbia Nashville Legacy"
    assert release.get("release_catalogue_number") == "886444460446"
    assert not release.get("edition_year")


def test_compilation_uses_multiple_artists_not_various_artists_literal():
    release = MusicRelease(root=".")
    for index, artist in enumerate(("Artist One", "Artist Two", "Artist Three", "Artist Four"), start=1):
        release.tracks.append(
            AudioTrack(
                path=f"{index}.flac",
                relative_path=f"{index}.flac",
                format="FLAC",
                codec="FLAC",
                artist=artist,
                album_artist="Various Artists",
                album="Compilation",
                title=f"Track {index}",
                track_number=index,
                tags={"albumartist": ["Various Artists"], "artist": [artist]},
            )
        )

    MusicReleaseAnalyzer()._derive_release_fields(release, "Compilation")

    assert release.get("release_type") == "Compilation"
    assert release.get("artists") == ["Artist One", "Artist Two", "Artist Three", "Artist Four"]
    assert release.get("artist") != "Various Artists"


def test_featured_track_artists_do_not_turn_a_stable_album_artist_into_a_compilation():
    """Guest-heavy albums must retain the release's ALBUMARTIST credit.

    This mirrors Bootsy Collins - Metal Health: all tracks are credited to
    Bootsy at album level, while individual songs add different guests.
    """
    release = MusicRelease(root=".")
    track_artists = (
        "Bootsy Collins",
        "Bootsy Collins, Manou Gallo, Buckethead",
        "Bootsy Collins, Buckethead, Victor Wooten",
        "Bootsy Collins, Ouiwey Collins",
        "Bootsy Collins, Buckethead",
        "Bootsy Collins, Buckethead, Robert Trujillo",
        "Bootsy Collins, Nate Alien8, Buckethead, Barbie T",
        "Bootsy Collins, Robert Trujillo",
        "Bootsy Collins, Tobotius",
        "Bootsy Collins, Billy Sheehan",
        "Bootsy Collins, Buckethead, Jennifer Batten",
        "Bootsy Collins, Buckethead, Tobotius",
        "Bootsy Collins, Samuel L. Jackson",
        "Bootsy Collins, Eric Gales",
    )
    for index, artist in enumerate(track_artists, start=1):
        release.tracks.append(
            AudioTrack(
                path=f"{index}.flac",
                relative_path=f"{index}.flac",
                format="FLAC",
                codec="FLAC",
                artist=artist,
                album_artist="Bootsy Collins",
                album="Metal Health",
                title=f"Track {index}",
                track_number=index,
                tags={"albumartist": ["Bootsy Collins"], "artist": [artist]},
            )
        )

    MusicReleaseAnalyzer()._derive_release_fields(release, "Bootsy_Collins-Metal_Health-16BIT-WEB-FLAC-2026-ENViED")

    assert release.get("release_type") == "Album"
    assert release.get("artists") == ["Bootsy Collins"]
    assert release.get("artist") == "Bootsy Collins"


def test_album_title_containing_ost_letters_is_not_a_soundtrack():
    release = MusicRelease(root=".")
    for index in range(1, 8):
        release.tracks.append(
            AudioTrack(
                path=f"{index}.flac",
                relative_path=f"{index}.flac",
                format="FLAC",
                codec="FLAC",
                artist="RiN",
                album_artist="RiN",
                album="NOSTALGIA",
                title=f"Track {index}",
                track_number=index,
                tags={"albumartist": ["RiN"], "artist": ["RiN"]},
            )
        )

    MusicReleaseAnalyzer()._derive_release_fields(release, "RiN-NOSTALGIA-DE-16BIT-WEB-FLAC-2026-ENRiCH")

    assert release.get("release_type") == "Album"


def test_orpheus_preserves_multiple_artists_and_release_namespace():
    release = MusicRelease(root=".")
    release.tracks.append(
        AudioTrack(path="track.flac", relative_path="track.flac", format="FLAC", codec="FLAC", bit_depth=16, sample_rate=44_100, title="No Church in the Wild", track_number=1)
    )
    for field, value in {
        "artists": ["Jay-Z", "Kanye West"],
        "artist": "Jay-Z & Kanye West",
        "album": "Watch the Throne",
        "year": "2011",
        "media": "CD",
        "release_type": "Album",
        "release_label": "Roc-A-Fella",
        "release_catalogue_number": "B0015962-02",
    }.items():
        release.set_field(field, value, MetadataSource.FILE_TAG, 1.0)

    adapter = Orpheus({"TRACKERS": {"ORPHEUS": {}}})
    payload = adapter.build_upload_payload(Meta(category="MUSIC", artwork_url="https://images.example/cover.jpg"), release)

    assert payload["artists[]"] == ["Jay-Z", "Kanye West"]
    assert payload["importance[]"] == [1, 1]
    assert payload["record_label"] == "Roc-A-Fella"
    assert payload["catalogue_number"] == "B0015962-02"
    assert "remaster_record_label" not in payload
    assert "remaster_catalogue_number" not in payload
    assert [entry for entry in adapter._form_data(payload) if entry[0] == "artists[]"] == [("artists[]", "Jay-Z"), ("artists[]", "Kanye West")]


def test_orpheus_additional_checks_block_prohibited_music_artists():
    release = MusicRelease(root=".")
    release.set_field("artists", ["Paul DVR & Allowed Guest"], MetadataSource.FILE_TAG, 1.0)
    release.set_field("artist", "Paul DVR & Allowed Guest", MetadataSource.FILE_TAG, 1.0)
    meta = Meta(category="MUSIC", debug=True, music_release=release.to_dict())
    adapter = Orpheus({"TRACKERS": {"ORPHEUS": {}}})

    assert not asyncio.run(adapter.get_additional_checks(meta))
    assert "Paul_DVR" in meta.tracker_status["ORPHEUS"]["status_message"]
    assert not asyncio.run(adapter.upload(meta))
    assert "debug_payload" not in meta.tracker_status["ORPHEUS"]


def test_orpheus_additional_checks_block_blacklisted_releases_and_labels():
    adapter = Orpheus({"TRACKERS": {"ORPHEUS": {}}})
    for artist, album in (
        ("Bruce Springsteen", "Odds and Sods"),
        ("Dr. Dre", "Detox"),
        ("Green Day", "Cigarettes and Valentines"),
        ("Jean-Michel Jarre", "Music for Supermarkets"),
        ("Michael Jackson", "Super Mix"),
        ("Pink Floyd", "Tree Full of Secrets"),
        ("The Beatles", "Carnival of Light"),
        ("The Upholsterers", "Your Furniture Was Always Dead... I Was Just Afraid To Tell You"),
        ("Various Artists", "The Ultimate 500 CD Jazz Collection"),
        ("Wu-Tang Clan", "Once Upon a Time in Shaolin"),
    ):
        release = MusicRelease(root=".")
        release.set_field("artist", artist, MetadataSource.FILE_TAG, 1.0)
        release.set_field("artists", [artist], MetadataSource.FILE_TAG, 1.0)
        release.set_field("album", album, MetadataSource.FILE_TAG, 1.0)
        meta = Meta(category="MUSIC", music_release=release.to_dict())

        assert not asyncio.run(adapter.get_additional_checks(meta))
        assert "blacklisted release" in meta.tracker_status["ORPHEUS"]["status_message"]

    for label in ("Sandero Classic Sound", "Sip It & Trip It Records"):
        release = MusicRelease(root=".")
        release.set_field("release_label", label, MetadataSource.FILE_TAG, 1.0)
        meta = Meta(category="MUSIC", music_release=release.to_dict())

        assert not asyncio.run(adapter.get_additional_checks(meta))
        assert f"blacklisted label {label}" in meta.tracker_status["ORPHEUS"]["status_message"]


def test_orpheus_album_description_includes_track_and_total_durations():
    release = MusicRelease(root=".")
    release.tracks.extend(
        [
            AudioTrack(path="01.flac", relative_path="01.flac", format="FLAC", codec="FLAC", title="Never Said No", track_number=1, duration=213.4),
            AudioTrack(path="02.flac", relative_path="02.flac", format="FLAC", codec="FLAC", title="All The Beauty", track_number=2, duration=237.0),
        ]
    )

    assert Orpheus._album_description(release) == "[b]Tracklist[/b] (1 disc(s))\n\n1. Never Said No (03:33)\n2. All The Beauty (03:57)\n\nTotal length: 07:30"


def test_orpheus_debug_renders_payload_without_public_cover_url():
    """Debug must inspect an embedded/local cover without hosting or blocking."""
    release = MusicRelease(root=".")
    release.tracks.append(
        AudioTrack(path="single.flac", relative_path="single.flac", format="FLAC", codec="FLAC", bit_depth=16, sample_rate=44_100, title="Single", track_number=1)
    )
    for field, value in {"artist": "Artist", "artists": ["Artist"], "album": "Album", "year": "2024", "media": "WEB", "release_type": "Single"}.items():
        release.set_field(field, value, MetadataSource.FILE_TAG, 1.0)
    meta = Meta(category="MUSIC", debug=True, music_release=release.to_dict())

    assert asyncio.run(Orpheus({"TRACKERS": {"ORPHEUS": {}}}).upload(meta))
    assert "image" not in meta.tracker_status["ORPHEUS"]["debug_payload"]
    assert "Artwork is optional" in meta.tracker_status["ORPHEUS"]["status_message"]


def test_orpheus_form_values_include_ogg_and_current_release_types():
    assert _format_for(Path("track.ogg"), object()) == ("Ogg Vorbis", "Vorbis")
    assert Orpheus.release_types["Sampler"] == 8
    assert Orpheus.release_types["Demo"] == 10
    assert Orpheus.release_types["Split"] == 12
    assert Orpheus.release_types["DJ Mix"] == 17


def test_orpheus_uses_concrete_release_year_for_required_edition_year():
    release = MusicRelease(root=".")
    release.tracks.append(
        AudioTrack(path="track.flac", relative_path="track.flac", format="FLAC", codec="FLAC", bit_depth=16, sample_rate=44_100, title="Track", track_number=1)
    )
    for field, value in {
        "artist": "Artist",
        "artists": ["Artist"],
        "album": "Album",
        "year": "2020",
        "release_year": "2026",
        "media": "WEB",
        "release_type": "Album",
    }.items():
        release.set_field(field, value, MetadataSource.FILE_TAG, 1.0)

    payload = Orpheus({"TRACKERS": {"ORPHEUS": {}}}).build_upload_payload(Meta(category="MUSIC"), release)

    assert payload["remaster"] == 1
    assert payload["remaster_year"] == "2026"
    assert not release.get("edition_year")


def test_orpheus_request_match_is_title_artist_and_initial_year_aware():
    release = MusicRelease(root=".")
    for field, value in {"artists": ["Led Zeppelin"], "artist": "Led Zeppelin", "album": "Coda", "year": "1982"}.items():
        release.set_field(field, value, MetadataSource.FILE_TAG, 1.0)
    record = {
        "title": "Coda",
        "year": 1982,
        "artists": [[{"name": "Led Zeppelin"}]],
    }

    assert Orpheus._request_match_type(release, record) == "exact"
    assert Orpheus._request_match_type(release, {**record, "year": 2015}) == "partial"
    assert Orpheus._request_match_type(release, {**record, "title": "Presence"}) is None


def test_nfo_enrichment_is_auxiliary_and_sidecars_are_checked_without_hashing(tmp_path):
    (tmp_path / "release.nfo").write_text(
        "Improve the quality or value of.\nARTIST.....: Artist\nALBUM......: Album\nLABEL......: Example Records\nGENRE......: Rock\nSOURCE.....: WEB\nQUALITY....: 24 bit / 48 kHz\nRETAIL DATE: 2026-07-24\nURL........: https://store.example/album\n",
        encoding="utf-8",
    )
    (tmp_path / "release.m3u").write_text("01-track.flac\n", encoding="utf-8")
    (tmp_path / "release.sfv").write_text("01-track.flac 1234ABCD\n", encoding="utf-8")
    release = MusicRelease(root=str(tmp_path))
    release.tracks.append(
        AudioTrack(
            path=str(tmp_path / "01-track.flac"),
            relative_path="01-track.flac",
            format="FLAC",
            codec="FLAC",
            bit_depth=24,
            sample_rate=48_000,
            artist="Artist",
            album_artist="Artist",
            album="Album",
            title="Track",
            date="2026",
        )
    )
    analyzer = MusicReleaseAnalyzer()
    for path in (tmp_path / "release.nfo", tmp_path / "release.m3u", tmp_path / "release.sfv"):
        analyzer._classify_auxiliary(release, path, tmp_path)

    analyzer._derive_release_fields(release, "Artist-Album-24BIT-48KHZ-WEB-FLAC-2026-GRP")

    assert release.get("release_label") == "Example Records"
    assert release.get("retail_date") == "2026-07-24"
    assert release.get("store_url") == "https://store.example/album"
    assert release.get("nfo_bit_depth") == 24
    assert release.get("nfo_sample_rate") == 48_000
    assert release.get("playlist_tracks") == 1
    assert release.get("sfv_entries") == 1
    assert _clean("4. \u2060Assets") == "4. Assets"


def test_music_confirmation_reports_music_specific_review_data(tmp_path):
    release = MusicRelease(root=str(tmp_path))
    release.tracks.append(
        AudioTrack(
            path="track.flac",
            relative_path="track.flac",
            format="FLAC",
            codec="FLAC",
            bit_depth=24,
            sample_rate=48_000,
            channels=2,
            artist="Artist",
            album="Album",
            title="Track",
        )
    )
    release.auxiliary.logs.append("rip.log")
    release.auxiliary.nfos.append("release.nfo")
    for name, value in {
        "artist": "Artist",
        "artists": ["Artist"],
        "album": "Album",
        "year": "2026",
        "media": "WEB",
        "release_type": "Album",
        "release_label": "Example Records",
    }.items():
        release.set_field(name, value, MetadataSource.FILE_TAG, 1.0)
    release.warnings.append("warning: verify retail date")

    lines = dict(item for item in _music_confirmation_lines(Meta(category="MUSIC", music_release=release.to_dict()), "MISSING") if isinstance(item, tuple))

    assert lines["Artist"].startswith("Artist")
    assert lines["Audio"] == "FLAC / 24-bit / 48 kHz / Stereo"
    assert lines["This Release"].startswith("Example Records")
    assert lines["Auxiliary"] == "1 log, 1 NFO"
    assert "verify retail date" in lines["Music validation"]


def test_orpheus_success_response_records_ids_and_warnings():
    meta = Meta(category="MUSIC")
    adapter = Orpheus({"TRACKERS": {"ORPHEUS": {}}})

    accepted = adapter._record_upload_response(
        meta,
        {
            "status": "success",
            "response": {
                "groupId": 1625999,
                "newgroup": True,
                "torrentId": 3691787,
                "private": True,
                "source": True,
                "extraTorrents": [],
                "warnings": ["Please verify the edition details."],
            },
            "info": {"source": "Orpheus", "version": 1},
        },
    )

    status = meta.tracker_status["ORPHEUS"]
    assert accepted
    assert status["torrent_id"] == 3691787
    assert status["group_id"] == 1625999
    assert status["new_group"] is True
    assert status["warnings"] == ["Please verify the edition details."]
    assert "Warnings: Please verify the edition details." in status["status_message"]


def test_discogs_reference_and_release_metadata_preserve_stronger_file_tags():
    assert DiscogsEnricher.parse_reference("https://www.discogs.com/release/12345-Test") == ("release", "12345")
    assert DiscogsEnricher.parse_reference("master/67890") == ("master", "67890")

    release = MusicRelease(root=".")
    release.set_field("release_label", "Embedded Label", MetadataSource.FILE_TAG, 0.95)
    DiscogsEnricher._apply_release(
        release,
        {
            "id": 12345,
            "master_id": 67890,
            "title": "Artist - Album",
            "year": 2024,
            "released": "2024-05-01",
            "country": "US",
            "artists": [{"name": "Artist (2)"}],
            "labels": [{"name": "Discogs Label", "catno": "ABC-123"}],
            "genres": ["Rock"],
            "styles": ["Alternative Rock"],
            "formats": [{"name": "File", "descriptions": ["Album", "FLAC"]}],
        },
    )

    assert release.external_ids["discogs_release"] == "12345"
    assert release.external_ids["discogs_master"] == "67890"
    assert release.get("artist") == "Artist"
    assert release.get("album") == "Album"
    assert release.get("release_year") == "2024"
    assert release.get("release_catalogue_number") == "ABC-123"
    assert release.get("release_label") == "Embedded Label"
    assert release.get("media") == "WEB"


def test_musicbrainz_requires_an_exact_title_and_track_count_match():
    result = MusicBrainzEnricher._select_release(
        [
            {
                "id": "wrong-single",
                "title": "nostalgia is killing me",
                "score": "100",
                "track-count": 2,
                "release-group": {"primary-type": "Single"},
            }
        ],
        "NOSTALGIA",
        18,
    )

    assert result is None


def test_musicbrainz_prefers_matching_cd_barcode_over_same_track_count_vinyl():
    result = MusicBrainzEnricher._select_release(
        [
            {
                "id": "wrong-vinyl",
                "title": "Seventh Son of a Seventh Son",
                "score": "100",
                "barcode": "881034121455",
                "media": [{"format": '12" Vinyl', "track-count": 8}],
            },
            {
                "id": "correct-cd",
                "title": "Seventh Son of a Seventh Son",
                "score": "95",
                "barcode": "0190295567699",
                "media": [{"format": "CD", "track-count": 8}],
                "label-info": [{"catalog-number": "0190295567699"}],
            },
        ],
        "Seventh Son of a Seventh Son",
        8,
        "CD",
        "0190295567699",
    )

    assert result is not None
    assert result["id"] == "correct-cd"


def test_external_single_cannot_override_an_album_length_local_release():
    release = MusicRelease(root=".")
    release.tracks = [AudioTrack(path=f"{index}.flac", relative_path=f"{index}.flac", format="FLAC", codec="FLAC", duration=150) for index in range(18)]
    release.set_field("artist", "RiN", MetadataSource.FILE_TAG, 1.0)
    release.set_field("album", "NOSTALGIA", MetadataSource.FILE_TAG, 1.0)
    release.set_field("release_type", "Album", MetadataSource.INFERRED, 0.65)
    external_single = {"id": "wrong-single", "release-group": {"primary-type": "Single"}}

    with patch.object(MusicBrainzEnricher, "_find_release", new=AsyncMock(return_value=external_single)):
        asyncio.run(MusicBrainzEnricher().enrich(release))

    assert release.get("release_type") == "Album"
    assert any("Ignored external MusicBrainz release type 'Single'" in warning for warning in release.warnings)


def test_music_discogs_cli_ids_keep_user_requested_identifiers(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--music-discogs-id", "master/67890", "--music-discogs-release-id", "12345"], Meta())
    release = MusicRelease(root=str(tmp_path))

    release_id, master_id = _discogs_ids(meta, release)

    assert (release_id, master_id) == ("12345", "67890")
    assert release.external_ids["discogs_release"] == "12345"
    assert release.external_ids["discogs_master"] == "67890"
    assert release.fields["discogs_release"].source == MetadataSource.USER


def test_no_music_discogs_cli_disables_automatic_lookup(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--no-music-discogs"], Meta())

    assert meta.music_discogs_enabled is False


def test_discogs_exact_search_requires_exact_artist_and_title():
    assert DiscogsEnricher._is_exact_release({"title": "Artist - Album"}, "Artist", "Album")
    assert not DiscogsEnricher._is_exact_release({"title": "Artist - Album (Deluxe)"}, "Artist", "Album")
    assert not DiscogsEnricher._is_exact_release({"title": "Another Artist - Album"}, "Artist", "Album")


def test_discogs_match_filter_excludes_incompatible_media():
    candidates = [
        {"id": 1, "format": ["File", "FLAC"]},
        {"id": 2, "format": ["DVD", "Album"]},
        {"id": 3, "format": ["CD", "Album"]},
        {"id": 4, "format": []},
        {"id": 5, "format": ["CDr", "Album"]},
        {"id": 6, "format": ["MiniDisc", "Album"]},
    ]

    assert [candidate["id"] for candidate in DiscogsEnricher.filter_releases_by_media(candidates, "WEB")] == [1, 4]
    assert [candidate["id"] for candidate in DiscogsEnricher.filter_releases_by_media(candidates, "CD")] == [3, 4, 5]
    assert [candidate["id"] for candidate in DiscogsEnricher.filter_releases_by_media(candidates, "DVD")] == [2, 4]


def test_discogs_catalogue_filter_preserves_hyphens_and_uses_safe_fallbacks():
    candidates = [{"id": 1, "catno": "B0012198-02"}, {"id": 2, "catno": "1791341"}]

    assert DiscogsEnricher.filter_releases_by_catalogue(candidates, "B001219802") == candidates
    assert DiscogsEnricher.filter_releases_by_catalogue(candidates, " B0012198-02 ") == [candidates[0]]
    assert DiscogsEnricher.filter_releases_by_catalogue(candidates, "does-not-exist") == candidates


def test_directory_catalogue_and_label_are_extracted_from_braced_release_info(tmp_path):
    release = MusicRelease(root=str(tmp_path))

    MusicReleaseAnalyzer._derive_from_directory(release, "Kanye West - 808s & Heartbreak (2008) [FLAC] {Roc-A-Fella Records B001219802 CD}")

    assert release.get("release_catalogue_number") == "B001219802"
    assert release.get("directory_catalogue_number") == "B001219802"
    assert release.get("release_label") == "Roc-A-Fella Records"


def test_directory_derivation_strips_only_matched_bracketed_metadata(tmp_path):
    release = MusicRelease(root=str(tmp_path))

    MusicReleaseAnalyzer._derive_from_directory(release, "Artist - Album (2008) [FLAC] {Label CATNO CD}")

    assert release.get("artist") == "Artist"
    assert release.get("album") == "Album (2008)"


def test_orpheus_enrichment_extracts_discogs_master_from_group_wiki(tmp_path):
    release = MusicRelease(root=str(tmp_path))
    release.set_field("artist", "Kanye West", MetadataSource.FILE_TAG, 1.0)
    release.set_field("album", "808s & Heartbreak", MetadataSource.FILE_TAG, 1.0)
    meta = Meta(category="MUSIC", orpheus="953914", base_dir=str(tmp_path), uuid="orpheus-master", music_release=release.to_dict())
    response = {
        "group": {"id": 610888, "name": "808s & Heartbreak", "year": 2008, "wikiBBcode": "https://www.discogs.com/master/8489"},
        "torrent": {"media": "CD", "encoding": "Lossless", "remasterYear": 2008, "remasterRecordLabel": "Roc-A-Fella Records", "remasterCatalogueNumber": "B001219802"},
    }

    with patch.object(Orpheus, "get_torrent", new=AsyncMock(return_value=response)):
        assert asyncio.run(enrich_music_from_orpheus(meta, {"TRACKERS": {"ORPHEUS": {}}}))

    assert meta.music_release["external_ids"]["discogs_master"] == "8489"
    assert meta.music_release["fields"]["release_catalogue_number"]["value"] == "B001219802"
    assert "edition_year" not in meta.music_release["fields"]


def test_discogs_auto_lookup_uses_only_one_exact_match(tmp_path):
    meta = Meta(unattended=True)
    release = MusicRelease(root=str(tmp_path))
    release.set_field("artist", "Artist", MetadataSource.FILE_TAG, 1.0)
    release.set_field("album", "Album", MetadataSource.FILE_TAG, 1.0)

    with patch.object(DiscogsEnricher, "find_exact_releases", new=AsyncMock(return_value=[{"id": 12345}])):
        assert asyncio.run(_find_discogs_release(meta, release, "token")) == "12345"

    with patch.object(DiscogsEnricher, "find_exact_releases", new=AsyncMock(return_value=[{"id": 12345}, {"id": 67890}])):
        assert asyncio.run(_find_discogs_release(meta, release, "token")) == ""

    release.set_field("media", "WEB", MetadataSource.USER, 1.0)
    with patch.object(DiscogsEnricher, "find_exact_releases", new=AsyncMock(return_value=[{"id": 12345, "format": ["File"]}, {"id": 67890, "format": ["DVD"]}])):
        assert asyncio.run(_find_discogs_release(meta, release, "token")) == "12345"


def test_discogs_exact_lookup_requires_a_token(tmp_path):
    enricher = DiscogsEnricher(base_dir=str(tmp_path))

    assert asyncio.run(enricher.find_exact_releases("Artist", "Album")) == []


def test_discogs_and_musicbrainz_use_persistent_music_metadata_cache(tmp_path):
    discogs_path = _music_cache_path(str(tmp_path), "discogs", "releases", "987654321")
    musicbrainz_key = "artist\x1falbum\x1f2\x1f\x1f"
    musicbrainz_path = _music_cache_path(str(tmp_path), "musicbrainz", "release_search", musicbrainz_key)
    asyncio.run(_write_music_cache(discogs_path, {"id": 987654321, "title": "Artist - Album"}))
    asyncio.run(_write_music_cache(musicbrainz_path, {"id": "cached-release", "title": "Album"}))

    DiscogsEnricher._cache.clear()
    MusicBrainzEnricher._cache.clear()
    discogs = DiscogsEnricher(base_dir=str(tmp_path))
    musicbrainz = MusicBrainzEnricher(base_dir=str(tmp_path))

    assert asyncio.run(discogs._get("releases", "987654321"))["id"] == 987654321
    assert asyncio.run(musicbrainz._find_release("Artist", "Album", 2))["id"] == "cached-release"


def test_music_prep_runs_shared_client_path_lookup_before_returning():
    prep = Prep.__new__(Prep)
    prep.config = {"DEFAULT": {}, "TRACKERS": {"default_trackers": "ORPHEUS"}}
    meta = Meta(category="MUSIC", path="C:/Music/Artist - Album")
    client = object()
    hash_ids = ["infohash", "torrent_hash", "skip_auto_torrent"]
    tracker_ids = ["orpheus"]

    with (
        patch("src.prep.prep_helpers.init_meta", return_value=(False, False, client, False, hash_ids, tracker_ids)),
        patch("src.prep.prep_helpers.detect_disc_and_category", new=AsyncMock(return_value=("", {}))),
        patch.object(Prep, "_gather_music_prep", new=AsyncMock()),
        patch("src.prep.prep_helpers.process_trackers_and_torrent", new=AsyncMock()) as process_trackers,
        patch("src.prep._enrich_music_from_orpheus_fn", new=AsyncMock()) as enrich_orpheus,
        patch("src.prep._enrich_music_from_discogs_fn", new=AsyncMock()) as enrich_discogs,
    ):
        result = asyncio.run(prep.gather_prep(meta, "cli"))

    assert result is meta
    process_trackers.assert_awaited_once_with(prep, meta, client, hash_ids, tracker_ids, "", "")
    enrich_orpheus.assert_awaited_once_with(meta, prep.config)
    enrich_discogs.assert_awaited_once_with(meta, prep.config)


def test_webui_music_preview_includes_release_review_data():
    meta = {
        "category": "MUSIC",
        "path": "C:/Music/Artist - Album",
        "music_release": {
            "fields": {
                "artists": {"value": ["Artist One", "Artist Two"], "source": "file_tag"},
                "album": {"value": "Album", "source": "file_tag"},
                "year": {"value": "2024", "source": "file_tag"},
                "media": {"value": "WEB", "source": "auxiliary"},
                "release_type": {"value": "Album", "source": "external"},
                "release_label": {"value": "Example Records", "source": "auxiliary"},
                "disc_count": {"value": 2, "source": "inferred"},
                "track_count": {"value": 12, "source": "inferred"},
            },
            "tracks": [{"format": "FLAC", "codec": "FLAC", "bit_depth": 24, "sample_rate": 48_000, "channels": 2, "bitrate": 1_600_000}],
            "auxiliary": {"logs": ["rip.log"], "nfos": ["release.nfo"]},
            "warnings": ["warning: review rip log"],
            "conflicts": {"year": ["2024", "2025"]},
        },
    }

    preview = _extract_execution_preview(meta, meta["path"])

    assert preview["title"] == "Album"
    assert preview["music"]["artist"] == "Artist One & Artist Two"
    assert preview["music"]["technical"] == "FLAC / 24-bit / 48 kHz / Stereo / 1600 kbps"
    assert preview["music"]["auxiliary"] == ["1 log", "1 NFO"]
    assert preview["music"]["conflicts"] == ["year"]


def test_music_cli_arguments_override_analysis_with_user_provenance(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(
        [
            str(tmp_path),
            "--music-artist",
            "Artist One & Artist Two",
            "--music-album",
            "Correct Album",
            "--music-media",
            "vinyl",
            "--music-release-type",
            "live album",
            "--music-release-year",
            "2024",
            "--music-label",
            "Example Records",
            "--music-catalogue-number",
            "ABC-123",
            "--music-genre",
            "Rock, Live",
            "--year",
            "1982",
            "--edition",
            "Deluxe Edition",
            "--music-edition-year",
            "2025",
            "--music-enrich",
        ],
        Meta(),
    )
    release = MusicRelease(root=str(tmp_path))
    release.set_field("artist", "Wrong Artist", MetadataSource.FILE_TAG, 1.0)

    _apply_music_cli_overrides(meta, release)

    assert release.get("artists") == ["Artist One", "Artist Two"]
    assert release.get("album") == "Correct Album"
    assert release.get("year") == "1982"
    assert release.get("media") == "Vinyl"
    assert release.get("release_type") == "Live album"
    assert release.get("release_year") == "2024"
    assert release.get("edition") == "Deluxe Edition"
    assert release.get("edition_year") == "2025"
    assert release.get("genres") == ["Rock", "Live"]
    assert release.fields["artist"].source == MetadataSource.USER
    assert meta.music_enrichment is True
    assert _music_override_year(0, "--year") == ""


def test_orpheus_async_multipart_uses_mapping_and_repeats_list_fields():
    async def encode_request() -> bytes:
        async with httpx.AsyncClient() as client:
            request = client.build_request(
                "POST",
                "https://example.invalid/ajax.php?action=upload",
                data={"artists[]": ["Artist One", "Artist Two"], "importance[]": [1, 1]},
                files=[("file_input", ("release.torrent", io.BytesIO(b"torrent"), "application/x-bittorrent"))],
            )
            return b"".join([chunk async for chunk in request.stream])

    body = asyncio.run(encode_request())

    assert body.count(b'name="artists[]"') == 2
    assert body.count(b'name="importance[]"') == 2
    assert b'name="file_input"; filename="release.torrent"' in body


def test_gather_music_prep_generates_mediainfo(tmp_path):
    from src.music.models import AudioTrack, MusicRelease
    from src.music.prep import gather_music_prep

    meta = Meta(
        category="MUSIC",
        path=str(tmp_path),
        uuid="dummy-uuid",
        base_dir=str(tmp_path),
        edit=False,
    )

    release = MusicRelease(root=str(tmp_path))
    track = AudioTrack(
        path=str(tmp_path / "01.flac"),
        relative_path="01.flac",
        format="FLAC",
        codec="FLAC",
    )
    dummy_file = tmp_path / "01.flac"
    dummy_file.write_bytes(b"dummy audio content")
    release.tracks.append(track)

    mock_mi = {"media": {"track": [{"@type": "General", "Format": "FLAC"}]}}

    with (
        patch.object(MusicReleaseAnalyzer, "analyze", return_value=release),
        patch("src.exportmi.export_info", new=AsyncMock(return_value=mock_mi)) as mock_export_info,
        patch("src.music.prep.prepare_music_cover", new=AsyncMock(return_value="")),
    ):
        asyncio.run(gather_music_prep(meta, {"DEFAULT": {}}))

    assert meta.mediainfo == mock_mi
    mock_export_info.assert_awaited_once_with(
        str(dummy_file),
        meta.isdir,
        meta.uuid,
        meta.base_dir,
        is_dvd=False,
    )
