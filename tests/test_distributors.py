# ruff: noqa: S101
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.distributors import distributor_id, distributor_name
from src.get_name import NameManager
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


@pytest.mark.parametrize("tracker, expected", [("", ""), ("AITHER", "994"), ("BLUTOPIA", "984"), ("ULCX", "970"), ("OLDTOONSWORLD", "")])
def test_tracker_specific_ids(tracker, expected):
    assert distributor_id("a24", tracker) == expected


@pytest.mark.parametrize("tracker, name", [("", ""), ("AITHER", "ABC STUDIOS"), ("BLUTOPIA", "PLUMERIA PICTURES"), ("ULCX", "CRUNCHYROLL, LLC"), ("OLDTOONSWORLD", "DEAF CROCODILE")])
def test_reverse_lookup_uses_tracker_identity(tracker, name):
    assert distributor_name("966", tracker) == name


def test_upstream_canonical_names_override_old_aliases():
    assert distributor_id("Capitol") == "158"
    assert distributor_id("Capitol Records") == "159"
    assert distributor_id("Columbia") == "202"
    assert distributor_id("Columbia Pictures") == "203"
    assert distributor_id("4K UHD") == "13"
    assert distributor_id("4K UHD", "AITHER") == "13"


@pytest.mark.parametrize("tracker", ["AITHER", "BLUTOPIA"])
def test_missing_tracker_entries_do_not_fall_back_to_default(tracker):
    assert distributor_id("A Contracorriente") == "18"
    assert distributor_id("A Contracorriente", tracker) == ""
    assert distributor_name(18, tracker) == ""


def test_renamed_entries_accept_upstream_spelling():
    assert distributor_id("Kinowelt Home Entertainment/DVD", "AITHER") == "473"
    assert distributor_id("Kinowelt Home Entertainment", "AITHER") == "473"
    assert distributor_name(473, "AITHER") == "KINOWELT HOME ENTERTAINMENT"
    assert distributor_id("Studio Canal", "BLUTOPIA") == "1184"
    assert distributor_id("StudioCanal", "BLUTOPIA") == "820"


def test_unknown_tracker_uses_upstream_only():
    assert distributor_id("BFI", "LST") == distributor_id("BFI")
    assert distributor_id("A24", "LST") == ""
    assert distributor_name("invalid", "LST") == ""
    assert distributor_name(None) == ""


@pytest.mark.parametrize("name", [path.stem for path in sorted((Path(__file__).resolve().parent.parent / "data" / "distributors").glob("*.json"))])
def test_all_canonical_entries_round_trip(name):
    path = Path(__file__).resolve().parent.parent / "data" / "distributors" / f"{name}.json"
    data = json.loads(path.read_text())
    tracker = "" if name == "default" else name.upper()
    if name == "default":
        assert set(map(int, data["distributors"])) == set(range(1, 966))
        assert set(data["aliases"].values()) <= set(range(1, 966))
    entries = data["distributors"]
    if name != "default":
        default = json.loads((path.parent / "default.json").read_text())["distributors"]
        assert "source" not in data
        assert all(id_value not in default or default[id_value].upper() != label.upper() for id_value, label in entries.items())
        entries = {id_value: label for id_value, label in default.items() if int(id_value) not in data.get("excluded_ids", [])} | entries
        assert len(entries) == {"aither": 1022, "asiancinema": 1011, "blutopia": 1351, "darkpeers": 965, "hawkeuno": 25, "itatorrents": 968, "latteam": 0, "oldtoonsworld": 970, "onlyencodes": 967, "polishtorrent": 1019, "rastastugan": 965, "reelflix": 966, "shareisland": 971, "theoldschool": 965, "ulcx": 973}[name]
    for id_value, label in entries.items():
        assert distributor_id(label, tracker) == id_value
        assert distributor_name(id_value, tracker) == label.upper()


@pytest.mark.asyncio
async def test_upload_uses_tracker_mapping():
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}, "ULCX": {}, "OLDTOONSWORLD": {}}}
    for tracker, expected in [("AITHER", {"distributor_id": "994"}), ("ULCX", {"distributor_id": "970"}), ("OLDTOONSWORLD", {})]:
        instance = UNIT3D(config, tracker_name=tracker)
        assert await instance.get_distributor_id(Meta(distributor="A24")) == expected


@pytest.mark.asyncio
async def test_metadata_lookup_preserves_override_and_resolves_tracker_id():
    common = Common({})
    meta = Meta()
    await common._apply_region_distributor(meta, {"distributor_id": "970"}, "ULCX")
    assert meta.distributor == "A24"
    await common._apply_region_distributor(meta, {"distributor_id": "966"}, "OLDTOONSWORLD")
    assert meta.distributor == "A24"


@pytest.mark.asyncio
async def test_required_tracker_accepts_its_custom_distributor_without_prompt():
    manager = NameManager({})
    manager._prompt_for_field = AsyncMock()
    meta = Meta(is_disc="BDMV", region="USA", distributor="A24")
    region, distributor, removed = await manager.missing_disc_info(meta, ["ULCX", "OLDTOONSWORLD"])
    assert (region, distributor, removed) == ("USA", "A24", [])
    manager._prompt_for_field.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_supplied_distributor_is_preserved_and_required_tracker_skipped():
    manager = NameManager({})
    manager._prompt_for_field = AsyncMock()
    meta = Meta(is_disc="BDMV", region="USA", distributor="UNLISTED STUDIO")
    region, distributor, removed = await manager.missing_disc_info(meta, ["ULCX", "OLDTOONSWORLD"])
    assert (region, distributor, removed) == ("USA", "UNLISTED STUDIO", ["ULCX"])
    manager._prompt_for_field.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["unit3d_region_distributor", "unit3d_torrent_info"])
@pytest.mark.parametrize("array_response", [False, True])
async def test_api_metadata_uses_tracker_specific_reverse_mapping(monkeypatch, method, array_response):
    attributes = {"distributor_id": "966"}
    payload = {"data": [{"attributes": attributes}]} if array_response else {"attributes": attributes}

    class Response:
        status_code = 200

        def json(self):
            return payload

    client = AsyncMock()
    client.get.return_value = Response()
    client.__aenter__.return_value = client
    monkeypatch.setattr("src.trackers.common.httpx.AsyncClient", lambda **kwargs: client)
    common = Common({"TRACKERS": {"OLDTOONSWORLD": {"api_key": "test"}}})
    meta = Meta(is_disc="BDMV")
    if method == "unit3d_region_distributor":
        await common.unit3d_region_distributor(meta, "OLDTOONSWORLD", "https://tracker.test/api/", "1")
    else:
        await common.unit3d_torrent_info("OLDTOONSWORLD", "https://tracker.test/api/", "https://tracker.test/search", meta, id="1")
    assert meta.distributor == "DEAF CROCODILE"


@pytest.mark.parametrize("tracker, distributor, expected", [
    ("ASIANCINEMA", "ABC Studios", "966"),
    ("ITATORRENTS", "Prime Video", "968"),
    ("ONLYENCODES", "A24", "967"),
    ("POLISHTORRENT", "PTTRiP", "966"),
    ("REELFLIX", "Radiance Films", "966"),
    ("SHAREISLAND", "Fandango", "966"),
])
def test_new_tracker_additions(tracker, distributor, expected):
    assert distributor_id(distributor, tracker) == expected
    assert distributor_name(expected, tracker) == distributor.upper()


@pytest.mark.parametrize("tracker", ["DARKPEERS", "RASTASTUGAN", "THEOLDSCHOOL"])
def test_verified_empty_overrides_use_default_mapping(tracker):
    assert distributor_id("BFI", tracker) == distributor_id("BFI")
    assert distributor_name(965, tracker) == distributor_name(965)
    path = Path(__file__).resolve().parent.parent / "data" / "distributors" / f"{tracker.lower()}.json"
    assert json.loads(path.read_text()) == {"distributors": {}}


def test_latteam_only_supports_other():
    assert distributor_id("BFI", "LATTEAM") == ""
    assert distributor_name(1, "LATTEAM") == ""
    assert distributor_name(965, "LATTEAM") == ""


def test_hawkeuno_aliases_follow_names_not_upstream_ids():
    assert distributor_id("Criterion Collection", "HAWKEUNO") == "1"
    assert distributor_id("BFI", "HAWKEUNO") == "2"
    assert distributor_id("88 Films", "HAWKEUNO") == "11"
    assert distributor_id("A24", "HAWKEUNO") == "25"
    assert distributor_name(1, "HAWKEUNO") == "CRITERION COLLECTION"
    assert distributor_id("01 Distribution", "HAWKEUNO") == ""
    assert distributor_id("4Digital", "HAWKEUNO") == ""
    assert distributor_id("4K UHD", "HAWKEUNO") == ""


@pytest.mark.parametrize("alias, tracker, expected", [
    ("Arrow Video", "", "75"),
    ("Arrow Video", "HAWKEUNO", "3"),
    ("Arrow", "HAWKEUNO", "3"),
    ("The Criterion Collection", "", "218"),
    ("The Criterion Collection", "HAWKEUNO", "1"),
    ("Kino-Lorber", "", "470"),
    ("Kino-Lorber", "HAWKEUNO", "7"),
    ("StudioCanal", "", "820"),
    ("StudioCanal", "BLUTOPIA", "820"),
    ("Studio Canal", "BLUTOPIA", "1184"),
    ("Crunchyroll", "AITHER", "968"),
    ("Crunchyroll", "ASIANCINEMA", "978"),
    ("Crunchyroll", "BLUTOPIA", "985"),
    ("Crunchyroll, LLC", "OLDTOONSWORLD", "970"),
    ("Crunchyroll", "ULCX", "966"),
    ("US Manga Corps", "AITHER", "991"),
    ("US Manga Corps", "ASIANCINEMA", "998"),
    ("U.S. Manga Corps", "OLDTOONSWORLD", "968"),
    ("VIZ Media", "AITHER", "996"),
    ("Factory 25", "AITHER", "982"),
    ("Factory 25", "BLUTOPIA", "1025"),
    ("Arts Magic", "ASIANCINEMA", "969"),
    ("Disney+", "POLISHTORRENT", ""),
    ("Vertice 360o", "", "906"),
    ("Crunchyroll", "", ""),
    ("VIZ Media", "ULCX", ""),
    ("Arrow Video", "LATTEAM", ""),
])
def test_obvious_aliases_follow_tracker_ids(alias, tracker, expected):
    assert distributor_id(alias.lower(), tracker) == expected


@pytest.mark.parametrize("alias, tracker, expected, canonical", [
    ("Cine Asia", "", "175", "Cine-Asia"),
    ("CineAsia", "", "175", "Cine-Asia"),
    ("AV Jet", "", "96", "AV-JET"),
    ("Bennett Watt Media", "", "115", "Bennett-Watt Media"),
    ("Astro Records and Filmworks", "", "87", "Astro Records & Filmworks"),
    ("U.S. Manga Corps", "OLDTOONSWORLD", "968", "US Manga Corps"),
    ("Crunchyroll, LLC", "OLDTOONSWORLD", "970", "Crunchyroll"),
    ("VIZ Media LLC", "AITHER", "996", "VIZ Media, LLC"),
    ("Anti Worlds", "BLUTOPIA", "1210", "Anti-Worlds"),
    ("Source 1 Media", "BLUTOPIA", "1018", "Source 1 Media B.V."),
    ("Source 1 Media BV", "BLUTOPIA", "1018", "Source 1 Media B.V."),
    ("Salzgeber & Co", "BLUTOPIA", "1173", "Salzgeber & Co."),
])
@pytest.mark.asyncio
async def test_added_spelling_aliases_preserve_canonical_names(alias, tracker, expected, canonical):
    from src.region import get_distributor

    assert await get_distributor(alias.lower()) == alias.upper()
    assert distributor_id(f" {alias.lower()} ", tracker) == expected
    assert distributor_name(expected, tracker) == canonical.upper()


@pytest.mark.parametrize("tracker", [path.stem for path in sorted((Path(__file__).resolve().parent.parent / "data" / "distributors").glob("*.json"))])
def test_default_spelling_aliases_follow_tracker_availability(tracker):
    for alias, canonical in [
        ("Cine Asia", "Cine-Asia"),
        ("CineAsia", "Cine-Asia"),
        ("AV Jet", "AV-JET"),
        ("Bennett Watt Media", "Bennett-Watt Media"),
        ("Astro Records and Filmworks", "Astro Records & Filmworks"),
    ]:
        assert distributor_id(alias, tracker) == distributor_id(canonical, tracker)


@pytest.mark.parametrize("tracker, first, first_id, second, second_id", [
    ("", "Entertainment One", "300", "entertainmentone", "302"),
    ("ASIANCINEMA", "A-film", "24", "Afilm", "1003"),
    ("BLUTOPIA", "Atlantic Film", "89", "AtlanticFilm", "1037"),
    ("BLUTOPIA", "StudioCanal", "820", "Studio Canal", "1184"),
])
def test_similar_canonical_names_keep_separate_ids(tracker, first, first_id, second, second_id):
    assert distributor_id(first, tracker) == first_id
    assert distributor_id(second, tracker) == second_id


@pytest.mark.asyncio
async def test_added_aliases_are_recognized_without_changing_canonical_names():
    from src.region import get_distributor

    assert await get_distributor("factory 25") == "FACTORY 25"
    assert await get_distributor("cinematographe") == "CINEMATOGRAPHE"
    assert distributor_name(968, "AITHER") == "CRUNCHYROLL, LLC"
    assert distributor_name(253, "POLISHTORRENT") == "DISNEY +"


@pytest.mark.parametrize("tracker, expected", [("AITHER", "969"), ("ASIANCINEMA", "977"), ("BLUTOPIA", "990")])
def test_unaccented_cinematographe_alias(tracker, expected):
    assert distributor_id("Cinematographe", tracker) == expected
    assert distributor_name(expected, tracker) == "CINÉMATOGRAPHE"


def test_polishtorrent_only_has_ascii_spelling_aliases():
    path = Path(__file__).resolve().parent.parent / "data" / "distributors" / "polishtorrent.json"
    assert json.loads(path.read_text())["aliases"] == {"PIEC SMAKOW": 1004, "PRIME": 969}


@pytest.mark.parametrize("alias, tracker, expected", [
    ("Wonder Multimidia", "ASIANCINEMA", "1011"),
    ("Arcades", "BLUTOPIA", "971"),
    ("Cahiers du cinema", "BLUTOPIA", "1076"),
    ("Les documents cinematographiques", "BLUTOPIA", "1133"),
    ("Les films du Camelia", "BLUTOPIA", "1136"),
    ("Rai", "BLUTOPIA", "1165"),
    ("Rene Chateau Video", "BLUTOPIA", "1169"),
    ("Gemini Video Editions", "BLUTOPIA", "1283"),
    ("Filmoteca Espanola", "BLUTOPIA", "1333"),
    ("Vertice Cine", "BLUTOPIA", "1338"),
    ("Mokep", "BLUTOPIA", "1339"),
    ("Piec Smakow", "POLISHTORRENT", "1004"),
    ("Prime", "POLISHTORRENT", "969"),
    ("Bildstorung", "", "125"),
    ("Hannsler Classic", "", "416"),
])
@pytest.mark.asyncio
async def test_ascii_distributor_spellings(alias, tracker, expected):
    from src.region import get_distributor

    assert distributor_id(alias, tracker) == expected
    assert await get_distributor(alias.lower()) == alias.upper()


@pytest.mark.parametrize("tracker, archive_id, bros_id", [
    ("", "935", "935"),
    ("AITHER", "974", "935"),
    ("ASIANCINEMA", "1001", "935"),
    ("BLUTOPIA", "1204", "935"),
    ("HAWKEUNO", "19", ""),
    ("ULCX", "935", "935"),
    ("LATTEAM", "", ""),
])
def test_warner_archive_respects_separate_tracker_entry(tracker, archive_id, bros_id):
    assert distributor_id("Warner Archive Collection", tracker) == archive_id
    assert distributor_id("Warner Archive", tracker) == archive_id
    assert distributor_id("wac", tracker) == archive_id
    for name in ("Warner Bros.", "Warner Bros", "Warner"):
        assert distributor_id(name, tracker) == bros_id
    if archive_id and archive_id != bros_id:
        expected = "WARNER ARCHIVE" if tracker == "HAWKEUNO" else "WARNER ARCHIVE COLLECTION"
        assert distributor_name(archive_id, tracker) == expected
    if bros_id:
        assert distributor_name(bros_id, tracker) == "WARNER BROS."


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["Warner Archive", "WAC"])
async def test_warner_archive_uploads_use_dedicated_ids(alias):
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}, "BLUTOPIA": {}, "HAWKEUNO": {}}}
    for name, id_value in [("AITHER", "974"), ("BLUTOPIA", "1204"), ("HAWKEUNO", "19")]:
        tracker = UNIT3D(config, tracker_name=name)
        assert await tracker.get_distributor_id(Meta(distributor=alias)) == {"distributor_id": id_value}
    tracker = UNIT3D(config, tracker_name="HAWKEUNO")
    assert await tracker.get_distributor_id(Meta(distributor="Warner Bros.")) == {}


@pytest.mark.asyncio
async def test_wac_alias_is_recognized():
    from src.region import get_distributor

    assert await get_distributor("wac") == "WAC"


@pytest.mark.parametrize("tracker, disney_id, buena_vista_id, combined_id", [
    ("", "253", "253", "253"),
    ("AITHER", "253", "253", "253"),
    ("ASIANCINEMA", "253", "1008", ""),
    ("BLUTOPIA", "253", "1302", "253"),
    ("HAWKEUNO", "23", "", ""),
])
def test_disney_buena_vista_split_does_not_merge_tracker_entries(tracker, disney_id, buena_vista_id, combined_id):
    assert distributor_id("Disney", tracker) == disney_id
    assert distributor_id("Buena Vista", tracker) == buena_vista_id
    assert distributor_id("Disney / Buena Vista", tracker) == combined_id
    assert distributor_id("Disney Buena Vista", tracker) == combined_id


def test_shareisland_universal_home_aliases_use_separate_distributor():
    for name in ("Universal Home", "Universal Home Entertainment", "Universal Pictures Home Entertainment"):
        assert distributor_id(name, "SHAREISLAND") == "967"
    for name in ("Universal Sony Pictures", "Universal Sony Pictures Home", "Universal Sony Pictures Home Entertainment"):
        assert distributor_id(name, "SHAREISLAND") == "896"
    assert distributor_id("Universal", "SHAREISLAND") == "897"
    assert distributor_id("Universal Entertainment", "SHAREISLAND") == ""
    assert distributor_id("Universal Home", "") == "896"
    assert distributor_name(967, "SHAREISLAND") == "UNIVERSAL PICTURES HOME ENTERTAINMENT"
    assert distributor_name(896, "SHAREISLAND") == "UNIVERSAL SONY PICTURES HOME ENTERTAINMENT"


@pytest.mark.asyncio
async def test_separate_distributor_aliases_are_used_for_uploads():
    config = {"DEFAULT": {}, "TRACKERS": {"SHAREISLAND": {}, "HAWKEUNO": {}}}
    tracker = UNIT3D(config, tracker_name="SHAREISLAND")
    assert await tracker.get_distributor_id(Meta(distributor="Universal Home")) == {"distributor_id": "967"}
    assert await tracker.get_distributor_id(Meta(distributor="Universal Entertainment")) == {}
    tracker = UNIT3D(config, tracker_name="HAWKEUNO")
    assert await tracker.get_distributor_id(Meta(distributor="Buena Vista")) == {}
    assert await tracker.get_distributor_id(Meta(distributor="Disney")) == {"distributor_id": "23"}


def test_new_tracker_file_is_discovered_without_registration(tmp_path, monkeypatch):
    import src.distributors as distributors

    default_path = Path(__file__).resolve().parent.parent / "data" / "distributors" / "default.json"
    (tmp_path / "default.json").write_text(default_path.read_text())
    (tmp_path / "newtracker.json").write_text(json.dumps({"distributors": {"10001": "New Distributor"}, "aliases": {"NEW LABEL": 10001}}))
    monkeypatch.setattr(distributors, "_DISTRIBUTOR_DIR", tmp_path)
    distributors._load_maps.cache_clear()
    try:
        assert distributor_id("New Distributor", " NewTracker ") == "10001"
        assert distributor_id("New Label", "NEWTRACKER") == "10001"
        assert distributor_name("10001", "newtracker") == "NEW DISTRIBUTOR"
        assert distributor_id("BFI", "newtracker") == "120"
        assert distributor_id("New Distributor", "missingtracker") == ""
        assert distributor_id("BFI", "missingtracker") == "120"
    finally:
        distributors._load_maps.cache_clear()
