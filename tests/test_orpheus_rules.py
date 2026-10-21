# ruff: noqa: S101
"""Orpheus upload rules, form fields, duplicate and request handling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx

from src.meta import Meta
from src.music.analyzer import _embedded_image_bytes, _flac_has_id3
from src.music.models import AudioTrack, MetadataSource, MusicRelease
from src.music.validation import OrpheusMusicValidator, lame_preset, resolve_orpheus_edition
from src.slot_rules.models import Verdict
from src.slot_rules.trackers.orpheus import SLOT_DECISION_KEY
from src.trackers.GAZELLE.orpheus import Orpheus
from src.trackers.GAZELLE.orpheus_tags import orpheus_tags


def _track(number: int, **overrides: Any) -> AudioTrack:
    values: dict[str, Any] = {
        "path": f"/music/Fictional Band - Paper Moons (2019) [FLAC]/{number:02d} - Song {number}.flac",
        "relative_path": f"{number:02d} - Song {number}.flac",
        "format": "FLAC",
        "codec": "FLAC",
        "bit_depth": 16,
        "sample_rate": 44_100,
        "channels": 2,
        "bitrate_mode": None,
        "track_number": number,
        "title": f"Song {number}",
        "artist": "Fictional Band",
        "album": "Paper Moons",
        "duration": 180.0,
    }
    values.update(overrides)
    return AudioTrack(**values)


def _release(tracks: int = 2, root: str = "/music/Fictional Band - Paper Moons (2019) [FLAC]", **fields: Any) -> MusicRelease:
    release = MusicRelease(root=root)
    release.tracks.extend(_track(number) for number in range(1, tracks + 1))
    defaults: dict[str, Any] = {
        "artist": "Fictional Band",
        "artists": ["Fictional Band"],
        "album": "Paper Moons",
        "year": "2019",
        "media": "WEB",
        "release_type": "Album",
    }
    defaults.update(fields)
    for name, value in defaults.items():
        release.set_field(name, value, MetadataSource.USER, 1.0)
    return release


def _codes(release: MusicRelease) -> dict[str, str]:
    return {issue.code: issue.level for issue in OrpheusMusicValidator().validate(release)}


def _adapter() -> Orpheus:
    return Orpheus({"TRACKERS": {"ORPHEUS": {"api_key": "fictional-token"}}})


def test_clean_release_has_no_errors():
    assert "error" not in _codes(_release()).values()


def test_edition_year_is_never_guessed_for_a_medium_that_postdates_the_album():
    release = _release(year="1968", media="CD")
    assert resolve_orpheus_edition(release).year == ""
    assert _codes(release)["missing_edition_year"] == "error"

    release.set_field("release_year", "1987", MetadataSource.USER, 1.0)
    assert resolve_orpheus_edition(release).year == "1987"
    assert "missing_edition_year" not in _codes(release)

    release.set_field("release_year", "1979", MetadataSource.USER, 1.0, force=True)
    assert _codes(release)["edition_predates_medium"] == "error"


def test_unknown_release_sends_only_the_unknown_flag():
    release = _release(year="1968", media="CD", release_label="Fictional Records", unknown_release=True)
    payload = _adapter().build_upload_payload(Meta(category="MUSIC"), release)

    assert payload["unknown"] == 1
    assert not any(key.startswith("remaster") for key in payload)
    assert "missing_edition_year" not in _codes(release)


def test_vinyl_edition_may_use_the_initial_year():
    release = _release(year="1968", media="Vinyl", release_label="Fictional Records", release_catalogue_number="FR-001")
    payload = _adapter().build_upload_payload(Meta(category="MUSIC"), release)

    assert payload["remaster_year"] == "1968"
    assert payload["remaster_record_label"] == "Fictional Records"
    assert payload["remaster_catalogue_number"] == "FR-001"


def test_original_release_title_is_rejected():
    assert _codes(_release(edition="Original Release"))["original_release_title"] == "error"


def test_server_file_rules_are_checked_before_upload():
    release = _release()
    release.auxiliary.artwork.append("cover.webp")
    release.auxiliary.other.append("Thumbs.db")
    release.auxiliary.other.append("notes from thepiratebay.org.txt")
    release.tracks.append(_track(3, relative_path="03 - What?.flac"))
    release.tracks.append(_track(4, relative_path=f"04 - {'x' * 260}.flac"))
    issues = OrpheusMusicValidator().validate(release)
    messages = " ".join(issue.message for issue in issues if issue.code == "file_extension")

    assert "cover.webp" in messages and "Thumbs.db" in messages
    assert {"forbidden_name", "forbidden_character", "path_length"} <= {issue.code for issue in issues}


def test_track_level_rules():
    release = _release(tracks=1, release_type="Single")
    release.tracks[0] = _track(1, title="", embedded_image_bytes=2 * 1024 * 1024, has_id3_tags=True, tags={"MQAENCODER": ["x"]})
    codes = _codes(release)

    assert codes["missing_required_tag"] == "error"
    assert codes["embedded_image_size"] == "error"
    assert codes["flac_id3"] == "warning"
    assert codes["mqa"] == "error"


def test_ogg_and_lossy_sample_rate_rules():
    ogg = _release(tracks=2)
    ogg.tracks[:] = [_track(n, format="Ogg Vorbis", path=f"{n}.ogg", relative_path=f"{n:02d} - Song.ogg") for n in (1, 2)]
    assert _codes(ogg)["unsupported_format"] == "error"

    mp3 = _release(media="CD")
    mp3.tracks[:] = [_track(n, format="MP3", path=f"{n}.mp3", relative_path=f"{n:02d} - Song.mp3", sample_rate=48_000, bit_depth=None) for n in (1, 2)]
    assert _codes(mp3)["mp3_cd_rate"] == "error"


def test_mixed_lame_presets_are_rejected():
    release = _release()
    release.tracks[:] = [
        _track(1, format="MP3", path="1.mp3", relative_path="01 - Song.mp3", encoder_settings="-V 0", bit_depth=None),
        _track(2, format="MP3", path="2.mp3", relative_path="02 - Song.mp3", encoder_settings="-V 2", bit_depth=None),
    ]
    assert _codes(release)["mixed_encoder_settings"] == "error"


def test_multi_disc_numbers_in_one_folder_and_nested_folders():
    release = _release(tracks=0)
    release.tracks.extend([_track(1, disc_number=1), _track(1, disc_number=2, relative_path="01 - Other.flac")])
    assert _codes(release)["duplicate_track_numbers"] == "error"

    nested = _release(tracks=0)
    nested.tracks.extend([_track(1, relative_path="Paper Moons/01 - Song 1.flac"), _track(2, relative_path="Paper Moons/02 - Song 2.flac")])
    assert _codes(nested)["nested_folders"] == "warning"


def test_blacklisted_sources_from_the_do_not_upload_list():
    assert _codes(_release(root="/music/Fictional Band - Paper Moons-TSX"))["blocked_source"] == "error"
    # BELLUM is banned for CD releases only.
    assert "blocked_source" not in _codes(_release(root="/music/Fictional Band - Paper Moons-BELLUM"))
    assert _codes(_release(root="/music/Fictional Band - Paper Moons-BELLUM", media="CD", release_year="2019"))["blocked_source"] == "error"


def test_lame_presets_and_form_bitrates():
    assert lame_preset("-V 0") == "V0 (VBR)"
    assert lame_preset("--preset extreme") == "APX (VBR)"
    assert lame_preset("--alt-preset standard") == "APS (VBR)"
    assert lame_preset("-b 320") is None

    release = _release()
    release.tracks[:] = [_track(n, format="MP3", encoder_settings="-V 0", bitrate_mode="VBR", bitrate=245_000) for n in (1, 2)]
    assert Orpheus._encoding(release, "MP3") == ("V0 (VBR)", "", False)

    release.tracks[:] = [_track(n, format="MP3", bitrate_mode="CBR", bitrate=128_000) for n in (1, 2)]
    assert Orpheus._encoding(release, "MP3") == ("128", "", False)

    release.tracks[:] = [_track(n, format="AAC", bitrate_mode="VBR", bitrate=245_000) for n in (1, 2)]
    assert Orpheus._encoding(release, "AAC") == ("Other", "245", True)


def test_tags_prefer_official_names_and_drop_upload_specific_tags():
    tags, unofficial, dropped = orpheus_tags(["Hip Hop", "R&B", "dnb", "Post-Rock", "FLAC", "Vinyl", "Shoegazey Folk"])

    assert tags[:4] == ["hip.hop", "rhythm.and.blues", "drum.and.bass", "post.rock"]
    assert unofficial == ["shoegazey.folk"]
    assert dropped == ["FLAC", "Vinyl"]


def test_payload_tags_fit_the_server_limit():
    release = _release(genres=[f"genre number {n}" for n in range(40)])
    tags = str(_adapter().build_upload_payload(Meta(category="MUSIC"), release)["tags"])
    assert 2 <= len(tags) <= 200


def test_artist_roles_for_guests_classical_and_cli_overrides():
    release = _release()
    release.tracks[0] = _track(1, artist="Fictional Band feat. Guest Singer & Second Guest")
    meta = Meta(category="MUSIC", music_artist_roles="Studio Person=producer; Fictional Band=main")
    credits = Orpheus._artist_credits(meta, release)
    assert ("Guest Singer", 2) in credits and ("Second Guest", 2) in credits
    assert ("Studio Person", 7) in credits and ("Fictional Band", 1) in credits

    classical = _release(genres=["Classical"])
    classical.tracks[0] = _track(1, tags={"composer": ["Imagined Composer"], "conductor": ["Pretend Conductor"]})
    classical_credits = Orpheus._artist_credits(Meta(category="MUSIC"), classical)
    assert ("Imagined Composer", 4) in classical_credits and ("Pretend Conductor", 5) in classical_credits

    pop = _release()
    pop.tracks[0] = _track(1, tags={"composer": ["Song Writer"]})
    assert all(role != 4 for _, role in Orpheus._artist_credits(Meta(category="MUSIC"), pop))


def test_cover_rejects_ptpimg_and_other_banned_hosts():
    assert Orpheus._cover_url(Meta(artwork_url="https://ptpimg.me/abc.jpg")) == ""
    assert Orpheus._cover_url(Meta(artwork_url="https://img.discogs.com/abc.jpg")) == ""
    assert Orpheus._cover_url(Meta(artwork_url="https://images.example/abc.jpg")) == "https://images.example/abc.jpg"


def test_release_description_documents_hybrids_scene_watermark_and_lineage(tmp_path):
    lineage = tmp_path / "lineage.txt"
    lineage.write_text("Turntable > preamp > ADC", encoding="utf-8")
    release = _release()
    release.tracks[1] = _track(2, bit_depth=24, sample_rate=96_000)
    meta = Meta(scene=True, scene_name="Fictional_Band-Paper_Moons-WEB-2019-FAKE", music_watermark="Voice-over on track 2", music_lineage=str(lineage))
    description = Orpheus._release_description(release, meta)

    assert "24-bit / 96 kHz / 2ch: tracks 2" in description
    assert "Scene release: Fictional_Band-Paper_Moons-WEB-2019-FAKE" in description
    assert "Voice-over on track 2" in description
    assert "Turntable > preamp > ADC" in description


def test_duplicate_search_assesses_each_torrent_in_the_matching_group():
    release = _release(release_label="Fictional Records", release_year="2019")
    # A folder catalogue number is not sent, but it identifies the release.
    release.set_field("release_catalogue_number", "FR 0042", MetadataSource.DIRECTORY, 0.65)
    meta = Meta(category="MUSIC", music_release=release.to_dict())
    torrent = {"torrentId": 7, "remasterYear": 2018, "remasterCatalogueNumber": "FR-0042 / FR-0043", "media": "WEB", "format": "FLAC", "encoding": "Lossless", "size": 1}
    results = {
        "results": [
            {
                "groupId": 1,
                "groupName": "Paper Moons",
                "artist": "Fictional Band",
                "groupYear": 2019,
                "torrents": [
                    torrent,
                    {**torrent, "torrentId": 8, "remasterYear": 2019, "remasterCatalogueNumber": "OTHER-1"},
                    {**torrent, "torrentId": 9, "remasterYear": 2021, "remasterCatalogueNumber": ""},
                ],
            },
            {"groupId": 2, "groupName": "Paper Moons Remixed", "artist": "Fictional Band", "torrents": [torrent]},
        ]
    }
    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value=results)):
        dupes = asyncio.run(_adapter().search_existing(meta))

    flags = [dupe["flags"][0] for dupe in dupes]
    assert flags[0].startswith("DUPE: A 16-bit FLAC already exists")
    assert flags[1].startswith("REVIEW: A release from the same year")
    assert flags[2] == "coexists with your upload"
    assert flags[3] == "different release group"
    assert dupes[0]["link"].endswith("torrentid=7")
    decision = meta[SLOT_DECISION_KEY]
    assert decision.verdict is Verdict.BLOCK
    assert [conflict["id"] for conflict in decision.conflicts] == [7]
    assert any("catalogue FR-0042 / FR-0043 as 2018" in note for note in decision.notes)


def test_request_search_uses_the_music_category_and_reports_compatibility():
    release = _release(release_year="2019")
    meta = Meta(category="MUSIC", music_release=release.to_dict())
    record = {
        "requestId": 55,
        "title": "Paper Moons",
        "year": 2019,
        "artists": [[{"name": "Fictional Band"}]],
        "formatList": ["MP3"],
        "bitrateList": ["Any"],
        "mediaList": ["Any"],
        "needLog": False,
        "needCue": False,
        "isFilled": False,
    }
    api = AsyncMock(return_value={"results": [record, {**record, "requestId": 56, "formatList": ["FLAC"]}]})
    with patch.object(Orpheus, "_api_get", new=api):
        matches = asyncio.run(_adapter().get_requests(meta))

    params = api.await_args.args[1]
    assert params["filter_cat[]"] == "0"
    assert "show_filled" not in params
    assert [(match["id"], match["compatible"]) for match in matches] == [("55", False), ("56", True)]


def test_request_fill_is_checked_before_it_is_sent():
    release = _release(release_year="2019")
    record = {
        "requestId": 9,
        "title": "Paper Moons",
        "year": 2019,
        "artists": [[{"name": "Fictional Band"}]],
        "categoryName": "Music",
        "formatList": ["FLAC"],
        "isFilled": False,
    }
    adapter = _adapter()

    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value=record)):
        assert asyncio.run(adapter._verify_request_fill(Meta(music_request_id="https://orpheus.network/requests.php?action=view&id=9"), release)) == ("9", "")
    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value={**record, "isFilled": True})):
        assert "already filled" in asyncio.run(adapter._verify_request_fill(Meta(music_request_id="9"), release))[1]
    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value={**record, "formatList": ["MP3"]})):
        assert "not met" in asyncio.run(adapter._verify_request_fill(Meta(music_request_id="9"), release))[1]


def test_debug_payload_includes_verified_request_and_group():
    release = _release(release_year="2019")
    meta = Meta(category="MUSIC", debug=True, music_release=release.to_dict(), music_request_id="9", music_group_id="4")

    async def fake_get(_self: Orpheus, _meta: Meta, params: dict[str, str], _timeout_seconds: float, _purpose: str) -> dict[str, Any]:
        if params["action"] == "request":
            return {"requestId": 9, "title": "Paper Moons", "categoryName": "Music", "isFilled": False}
        return {"group": {"id": 4, "name": "Paper Moons"}}

    with patch.object(Orpheus, "_api_get", new=fake_get):
        assert asyncio.run(_adapter().upload(meta))
    payload = meta.tracker_status["ORPHEUS"]["debug_payload"]
    assert payload["requestid"] == "9"
    assert payload["groupid"] == "4"


def test_upload_response_reports_failed_request_fill_and_trumps():
    meta = Meta(category="MUSIC")
    meta.tracker_status["ORPHEUS"] = {"dupe_assessment": [{"trumpable": True}]}
    response = {"status": "success", "response": {"torrentId": 1, "groupId": 2, "warnings": [], "fillRequest": {"status": 400, "error": "fictional failure"}}}

    assert _adapter()._record_upload_response(meta, response)
    message = meta.tracker_status["ORPHEUS"]["status_message"]
    assert "Request fill failed" in message
    assert "rule 2.2.3" in message


def test_single_file_path_is_blocked(tmp_path):
    audio = tmp_path / "01 - Song.flac"
    audio.write_bytes(b"fLaC")
    meta = Meta(category="MUSIC", path=str(audio), music_release=_release(tracks=1, release_type="Single").to_dict())

    assert not asyncio.run(_adapter().get_additional_checks(meta))
    assert "inside a folder" in meta.tracker_status["ORPHEUS"]["status_message"]


def test_drizzy_wap_is_blocked():
    meta = Meta(category="MUSIC", music_release=_release(artist="Drizzy Wap", artists=["Drizzy Wap"]).to_dict())
    assert not asyncio.run(_adapter().get_additional_checks(meta))


def test_analyzer_measures_embedded_artwork_and_id3_in_flac(tmp_path):
    flac = tmp_path / "id3.flac"
    flac.write_bytes(b"ID3" + b"\x00" * 200)
    clean = tmp_path / "clean.flac"
    clean.write_bytes(b"fLaC" + b"\x00" * 200)
    assert _flac_has_id3(flac)
    assert not _flac_has_id3(clean)

    padding = type("Padding", (), {"length": 4096})()
    technical = SimpleNamespace(pictures=[SimpleNamespace(data=b"x" * 1000)], metadata_blocks=[padding], tags=None)
    assert _embedded_image_bytes(technical) == 5096


def test_music_torrents_keep_their_folder_for_single_tracks():
    source = (Path(__file__).resolve().parents[1] / "src" / "torrentcreate.py").read_text(encoding="utf-8")
    assert 'not meta.keep_folder and meta.category != "MUSIC"' in source


def test_disc_prefixed_names_and_artist_prefixed_names_are_valid():
    release = _release(tracks=0)
    release.tracks.extend(
        [
            _track(1, disc_number=1, relative_path="1 - 01 - Opening.flac"),
            _track(1, disc_number=2, relative_path="2 - 01 - Reprise.flac"),
        ]
    )
    codes = _codes(release)
    assert "duplicate_track_numbers" not in codes

    named = _release(tracks=0)
    named.tracks.extend([_track(n, relative_path=f"Paper Moons - {n:02d} - Song {n}.flac") for n in (1, 2)])
    assert "filename_track_number" not in _codes(named)


def test_vinyl_side_folders_are_not_unnecessary_nesting():
    release = _release(tracks=0, media="Vinyl")
    release.tracks.extend([_track(1, relative_path="Side A/01 - Song 1.flac"), _track(2, relative_path="Side B/02 - Song 2.flac")])
    assert "nested_folders" not in _codes(release)


def test_folder_text_is_a_hint_not_edition_data():
    release = _release(media="CD", year="1970", release_year="1970")
    release.set_field("release_label", "R2", MetadataSource.DIRECTORY, 0.6, force=True)
    release.set_field("release_catalogue_number", "552928", MetadataSource.DIRECTORY, 0.65, force=True)
    release.set_field("release_year", "1970", MetadataSource.FILE_TAG, 0.9, force=True)
    edition = resolve_orpheus_edition(release)
    issues = {issue.code: issue for issue in OrpheusMusicValidator().validate(release)}

    assert (edition.year, edition.label, edition.catalogue_number) == ("", "", "")
    assert "edition_predates_medium" not in issues
    assert "pressing" in issues["missing_edition_year"].message
    assert "'R2'" in issues["folder_edition_hint"].message


def test_directory_technical_brackets_are_not_labels(tmp_path):
    from src.music.analyzer import MusicReleaseAnalyzer

    folder = tmp_path / "Fictional Band - Paper Moons (1966) [WEB] [FLAC] [16-bit 44100 Hz] [EAC]"
    folder.mkdir()
    release = MusicReleaseAnalyzer().analyze(folder)
    assert not release.get("release_label")
    assert not release.get("release_catalogue_number")


def test_compact_sample_rate_brackets_are_technical(tmp_path):
    from src.music.analyzer import MusicReleaseAnalyzer

    folder = tmp_path / "Fictional Band - Paper Moons (2019) [WEB] [96kHz] [44.1kHz]"
    folder.mkdir()
    assert not MusicReleaseAnalyzer().analyze(folder).get("release_label")


def test_missing_lineage_file_is_not_recorded(tmp_path):
    from src.music.prep import _apply_music_cli_overrides

    release = _release(media="Vinyl")
    _apply_music_cli_overrides(Meta(music_lineage=str(tmp_path / "missing.txt")), release)
    assert not release.get("lineage")
    assert _codes(release)["missing_lineage"] == "warning"

    lineage = tmp_path / "lineage.txt"
    lineage.write_text("Turntable > ADC", encoding="utf-8")
    _apply_music_cli_overrides(Meta(music_lineage=str(lineage)), release)
    assert release.get("lineage") == str(lineage)


def test_request_fill_rejects_low_log_score_and_other_artists():
    release = _release(release_year="2019")
    record = {"requestId": 9, "title": "Paper Moons", "artists": [[{"name": "Fictional Band"}]], "categoryName": "Music", "isFilled": False, "minLogScore": 100}
    adapter = _adapter()

    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value=record)):
        assert "below the minimum 100%" in asyncio.run(adapter._verify_request_fill(Meta(music_request_id="9"), release, [{"score": 95}]))[1]
        assert asyncio.run(adapter._verify_request_fill(Meta(music_request_id="9"), release, [{"score": 100}])) == ("9", "")
    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value={**record, "artists": [[{"name": "Someone Else"}]]})):
        assert "do not match" in asyncio.run(adapter._verify_request_fill(Meta(music_request_id="9"), release))[1]


def test_group_id_must_share_an_artist():
    release = _release()
    group = {"group": {"id": 4, "name": "Paper Moons", "musicInfo": {"artists": [{"id": 1, "name": "Someone Else"}]}}}
    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value=group)):
        assert "do not match" in asyncio.run(_adapter()._verify_group(Meta(music_group_id="4"), release))[1]
    group["group"]["musicInfo"]["artists"][0]["name"] = "Fictional Band"
    with patch.object(Orpheus, "_api_get", new=AsyncMock(return_value=group)):
        assert asyncio.run(_adapter()._verify_group(Meta(music_group_id="4"), release)) == ("4", "")


def test_scene_checkbox_is_only_sent_for_scene_uploads():
    # Orpheus treats any submitted "scene" field as checked (isset).
    release = _release()
    assert "scene" not in _adapter().build_upload_payload(Meta(category="MUSIC", scene=False), release)
    assert _adapter().build_upload_payload(Meta(category="MUSIC", scene=True), release)["scene"] == 1


def test_dupe_search_finds_a_group_written_differently():
    # Mirrors a real miss: different artist alias, punctuation and state name.
    release = _release(
        artist="Robbie Lane & Night Owls",
        artists=["Robbie Lane & Night Owls"],
        album="2023 12 31: Grand Hall Of Fictional Arts, Springfield, Florida",
        year="2023",
        release_year="2023",
    )
    meta = Meta(category="MUSIC", music_release=release.to_dict())
    existing = {
        "groupId": 77,
        "groupName": "2023-12-31 Grand Hall of Fictional Arts, Springfield, FL",
        "artist": "Rob Lane and Night Owls",
        "groupYear": 2023,
        "torrents": [{"torrentId": 5, "remasterYear": 2023, "media": "WEB", "format": "FLAC", "encoding": "Lossless"}],
    }
    calls: list[dict[str, str]] = []

    async def fake_get(_self: Orpheus, _meta: Meta, params: dict[str, str], _timeout_seconds: float, _purpose: str) -> dict[str, Any]:
        calls.append(params)
        return {"results": [existing] if params.get("groupname") == "2023 12 31" else []}

    with patch.object(Orpheus, "_api_get", new=fake_get), patch("asyncio.sleep", new=AsyncMock()):
        dupes = asyncio.run(_adapter().search_existing(meta))

    assert [call["action"] for call in calls] == ["browse", "browse", "browse", "torrentgroup"]
    assert dupes[0]["flags"][0].startswith("DUPE")


def test_group_matching_rejects_other_shows_and_artists():
    release = _release(artist="Robbie Lane & Night Owls", artists=["Robbie Lane & Night Owls"])
    assert not Orpheus._same_group_title("2023 12 31 Grand Hall", "2023-12-30 Grand Hall")
    assert Orpheus._same_group_title("Paper Moons (Deluxe)", "Paper Moons Deluxe")
    assert not Orpheus._same_group_title("Paper Moons", "Paper Moons Remixed And Extended")
    assert not Orpheus._shares_artist(release, "Someone Else Entirely")
    assert Orpheus._shares_artist(release, "Rob Lane and Night Owls")


def test_dated_titles_are_concert_recordings(tmp_path):
    from src.music.analyzer import MusicReleaseAnalyzer

    release = MusicRelease(root=str(tmp_path))
    release.set_field("album", "2023-12-31 Grand Hall, Springfield", MetadataSource.FILE_TAG, 1.0)
    release.tracks.extend([_track(n) for n in range(1, 8)])
    MusicReleaseAnalyzer._derive_release_type(release)
    assert release.get("release_type") == "Concert recording"


def test_same_date_at_another_venue_is_not_the_same_group():
    assert not Orpheus._same_group_title("2023-06-01 Live at Wembley", "2023-06-01 Live at Madison Square Garden")
    assert Orpheus._same_group_title("2023 12 31: Grand Hall Of Fictional Arts, Springfield, Florida", "2023-12-31 Grand Hall of Fictional Arts, Springfield, FL")


def test_artist_matching_is_strict_for_title_only_results():
    single = _release(artist="Robbie Lane", artists=["Robbie Lane"])
    # Server-side artist filter (first query): a co-credit still matches.
    assert Orpheus._shares_artist(single, "Robbie Lane & Marco Fictus")
    # Title/date-only queries need most of the larger credit to match.
    assert not Orpheus._shares_artist(single, "Robbie Lane & Marco Fictus & Third Person", strict=True)
    assert not Orpheus._shares_artist(single, "", strict=True)
    assert not Orpheus._shares_artist(single, "Various Artists", strict=True)
    compilation = _release(release_type="Compilation")
    assert Orpheus._shares_artist(compilation, "Various Artists", strict=True)


def test_accepted_upload_writes_the_torrent_link_into_the_client_torrent(tmp_path):
    from torf import Torrent

    content = tmp_path / "Fictional Band - Paper Moons (2019)"
    content.mkdir()
    (content / "01 - Song 1.flac").write_bytes(b"fLaC" + b"\0" * 4096)
    meta = Meta(category="MUSIC", base_dir=str(tmp_path), uuid="ops-comment")
    torrent_path = tmp_path / "tmp" / "ops-comment" / "[ORPHEUS].torrent"
    torrent_path.parent.mkdir(parents=True)
    torrent = Torrent(path=content, private=True, trackers=["https://example.invalid/announce"])
    torrent.metainfo["info"]["source"] = "OPS"
    torrent.generate()
    torrent.write(torrent_path)
    info_hash = Torrent.read(torrent_path).infohash

    adapter = Orpheus({"TRACKERS": {"ORPHEUS": {"api_key": "fictional-token", "announce_url": "https://example.invalid/announce"}}})
    response = {"status": "success", "response": {"torrentId": 42, "groupId": 7, "warnings": []}}
    assert adapter._record_upload_response(meta, response)
    asyncio.run(adapter._write_torrent_comment(meta))

    written = Torrent.read(torrent_path)
    assert written.comment == "https://orpheus.network/torrents.php?id=7&torrentid=42"
    assert written.infohash == info_hash


def _client_torrent(tmp_path: Path) -> tuple[Meta, Path]:
    from torf import Torrent

    content = tmp_path / "Fictional Band - Paper Moons (2019)"
    content.mkdir(exist_ok=True)
    (content / "01 - Song 1.flac").write_bytes(b"fLaC" + b"\0" * 4096)
    meta = Meta(category="MUSIC", base_dir=str(tmp_path), uuid="ops-download")
    torrent_path = tmp_path / "tmp" / "ops-download" / "[ORPHEUS].torrent"
    torrent_path.parent.mkdir(parents=True, exist_ok=True)
    torrent = Torrent(path=content, private=True, trackers=["https://example.invalid/announce"])
    torrent.generate()
    torrent.write(torrent_path, overwrite=True)
    meta.tracker_status["ORPHEUS"] = {"torrent_id": 42, "group_id": 7}
    return meta, torrent_path


def _fake_download(content: bytes | None):
    """Serve the site response through the real shared downloader."""
    client = httpx.AsyncClient
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200 if content is not None else 503, content=content or b"")

    def create_client(**kwargs: Any) -> httpx.AsyncClient:
        return client(transport=httpx.MockTransport(handle), **kwargs)

    return create_client, requests


def test_accepted_upload_seeds_the_torrent_downloaded_from_orpheus(tmp_path):
    import bencodepy

    meta, torrent_path = _client_torrent(tmp_path)
    site_torrent = bencodepy.decode(torrent_path.read_bytes())
    site_torrent[b"comment"] = b"https://orpheus.network/torrents.php?torrentid=42"
    site_file = bencodepy.encode(site_torrent)
    client, requests = _fake_download(site_file)
    with patch("src.trackers.common.httpx.AsyncClient", new=client):
        assert asyncio.run(_adapter()._download_site_torrent(meta))

    assert len(requests) == 1
    assert dict(requests[0].url.params) == {"action": "download", "id": "42"}  # never "usetoken"
    assert str(requests[0].url.copy_with(query=None)) == "https://orpheus.network/ajax.php"
    assert torrent_path.read_bytes() == site_file
    assert meta.tracker_status["ORPHEUS"]["torrent_link"] == "https://orpheus.network/torrents.php?torrentid=42"


def test_a_failed_download_keeps_the_local_torrent(tmp_path):
    meta, torrent_path = _client_torrent(tmp_path)
    original = torrent_path.read_bytes()
    # The API reports errors as JSON with HTTP 200; the helper must reject it.
    for content in (b'{"status":"failure","error":"rate limit"}', None):
        client, _ = _fake_download(content)
        with patch("src.trackers.common.httpx.AsyncClient", new=client):
            assert not asyncio.run(_adapter()._download_site_torrent(meta))
        assert torrent_path.read_bytes() == original


def test_file_error_after_upload_keeps_the_accepted_result(tmp_path):
    meta, torrent_path = _client_torrent(tmp_path)
    original = torrent_path.read_bytes()
    meta.music_release = _release(release_year="2019").to_dict()
    adapter = Orpheus({"TRACKERS": {"ORPHEUS": {"api_key": "fictional-token", "announce_url": "https://example.invalid/announce"}}})
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://orpheus.network/ajax.php?action=upload"),
        json={"status": "success", "response": {"torrentId": 42, "groupId": 7}},
    )
    with (
        patch.object(adapter, "get_additional_checks", new=AsyncMock(return_value=True)),
        patch.object(adapter, "_check_logs", new=AsyncMock(return_value=[])),
        patch.object(adapter, "_verify_request_fill", new=AsyncMock(return_value=("", ""))),
        patch.object(adapter, "_verify_group", new=AsyncMock(return_value=("", ""))),
        patch.object(adapter.common, "create_torrent_for_upload", new=AsyncMock()),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=response)),
        patch.object(adapter.common, "download_tracker_torrent", new=AsyncMock(side_effect=OSError("replacement failed"))),
        patch.object(adapter, "_write_torrent_comment", new=AsyncMock()) as fallback,
    ):
        assert asyncio.run(adapter.upload(meta))
    fallback.assert_awaited_once_with(meta)
    assert meta.tracker_status["ORPHEUS"]["status_message"] == "Upload accepted by Orpheus."
    assert torrent_path.read_bytes() == original


def test_title_fallback_query_drops_joining_words():
    # A combined credit ("A and B") misses groups listing A and B separately,
    # and the cleaned title must not turn "&" into a required word "and".
    release = _release(artist="Fictional Violin and Pretend Piano", artists=["Fictional Violin and Pretend Piano"], album="Bowstring & Keys")
    meta = Meta(category="MUSIC", music_release=release.to_dict())
    existing = {
        "groupId": 9,
        "groupName": "Bowstring & Keys",
        "artist": "Fictional Violin & Pretend Piano",
        "torrents": [{"torrentId": 1, "remasterYear": 2019, "media": "WEB", "format": "FLAC", "encoding": "Lossless"}],
    }
    calls: list[dict[str, str]] = []

    async def fake_get(_self: Orpheus, _meta: Meta, params: dict[str, str], _timeout_seconds: float, _purpose: str) -> dict[str, Any]:
        calls.append(params)
        return {"results": [existing] if params.get("groupname") == "bowstring keys" and "artistname" not in params else []}

    with patch.object(Orpheus, "_api_get", new=fake_get), patch("asyncio.sleep", new=AsyncMock()):
        dupes = asyncio.run(_adapter().search_existing(meta))

    assert {"action": "browse", "groupname": "bowstring keys"} in calls
    assert dupes and dupes[0]["flags"][0].startswith(("DUPE", "LIKELY DUPE"))


def test_classical_group_credits_compare_the_performers():
    duo = _release(artist="Fictional Violin and Pretend Piano", artists=["Fictional Violin and Pretend Piano"])
    credit = "Various Composers performed by Pretend Piano and Fictional Violin"
    assert Orpheus._shares_artist(duo, credit, strict=True)
    assert Orpheus._shares_artist(duo, "Imagined Composer performed by Fictional Violin and Pretend Piano under Some Conductor", strict=True)
    assert not Orpheus._shares_artist(duo, "Various Composers performed by Someone Else Entirely", strict=True)


def test_featuring_in_the_main_credit_and_named_remixes_become_roles():
    release = _release(
        tracks=1,
        artist="Neon Tide feat. Imaginary Singer",
        artists=["Neon Tide feat. Imaginary Singer"],
        album="Paper Boat (Imaginary Singer Remix)",
        release_type="Single",
    )
    release.tracks[0] = _track(1, artist="Neon Tide feat. Imaginary Singer", title="Paper Boat (Imaginary Singer Remix)")
    credits = Orpheus._artist_credits(Meta(category="MUSIC"), release)
    # Main artist only; the featured remixer is credited once, as remixer.
    assert credits == [("Neon Tide", 1), ("Imaginary Singer", 3)]

    plain = _release(tracks=1, artist="Neon Tide feat. Guest Voice", artists=["Neon Tide feat. Guest Voice"], release_type="Single")
    assert Orpheus._artist_credits(Meta(category="MUSIC"), plain) == [("Neon Tide", 1), ("Guest Voice", 2)]
    assert Orpheus._title_remixers("Paper Boat (Extended Mix)") == []
    assert Orpheus._title_remixers("Paper Boat (Original Remix)") == []


def test_release_type_markers_do_not_split_groups():
    assert Orpheus._strip_type_marker("Paper Boat EP") == ("Paper Boat", "ep")
    assert Orpheus._strip_type_marker("Paper Boat - Single") == ("Paper Boat", "single")
    assert Orpheus._strip_type_marker("Night Shift (Live)") == ("Night Shift", "live")
    for title in ("The EP", "EP", "Stay Live", "Steep"):
        assert Orpheus._strip_type_marker(title) == (title, "")
    assert Orpheus._same_group_title("Paper Boat EP", "Paper Boat")
    assert Orpheus._same_group_title("Night Shift (Live)", "Night Shift")


def test_upload_title_drops_a_marker_that_repeats_the_release_type():
    ep = _release(album="Paper Boat EP", release_type="EP")
    assert _adapter().build_upload_payload(Meta(category="MUSIC"), ep)["title"] == "Paper Boat"
    # A marker that does not match the release type is part of the title.
    album = _release(album="Paper Boat EP", release_type="Album")
    assert _adapter().build_upload_payload(Meta(category="MUSIC"), album)["title"] == "Paper Boat EP"


def test_dupe_search_ignores_a_trailing_type_marker():
    release = _release(album="Paper Boat EP", release_type="EP", release_year="2019")
    meta = Meta(category="MUSIC", music_release=release.to_dict())
    existing = {"groupId": 3, "groupName": "Paper Boat", "artist": "Fictional Band", "torrents": [{"torrentId": 8, "remasterYear": 2019, "media": "WEB", "format": "FLAC", "encoding": "Lossless"}]}
    calls: list[dict[str, str]] = []

    async def fake_get(_self: Orpheus, _meta: Meta, params: dict[str, str], _timeout_seconds: float, _purpose: str) -> dict[str, Any]:
        calls.append(params)
        return {"results": [existing] if params.get("groupname") == "Paper Boat" else []}

    with patch.object(Orpheus, "_api_get", new=fake_get), patch("asyncio.sleep", new=AsyncMock()):
        dupes = asyncio.run(_adapter().search_existing(meta))

    assert calls[0] == {"action": "browse", "artistname": "Fictional Band", "groupname": "Paper Boat"}
    assert dupes and dupes[0]["flags"][0].startswith(("DUPE", "LIKELY DUPE"))
