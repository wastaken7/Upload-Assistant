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
