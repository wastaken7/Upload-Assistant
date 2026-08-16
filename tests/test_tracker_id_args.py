# ruff: noqa: S101

import pytest

from src.args import Args
from src.meta import Meta


def test_tracker_id_accepts_explicit_tracker_and_id():
    args = Args({"TRACKERS": {}})

    assert args.parse_tracker_id("AITHER=50049") == ("AITHER", "50049")


def test_tracker_id_accepts_aither_torrent_url():
    args = Args({"TRACKERS": {}})

    assert args.parse_tracker_id("https://aither.cc/torrents/415499") == ("AITHER", "415499")


def test_tracker_id_accepts_beyondhd_dotted_torrent_url():
    args = Args({"TRACKERS": {}})

    assert args.parse_tracker_id("https://beyond-hd.me/download/release.12345") == ("BEYONDHD", "12345")


def test_tracker_id_accepts_beyondhd_alias():
    args = Args({"TRACKERS": {}})

    assert args.parse_tracker_id("BHD=123") == ("BEYONDHD", "123")


def test_tracker_id_rejects_mismatched_tracker_url():
    args = Args({"TRACKERS": {}})

    with pytest.raises(ValueError, match="does not match"):
        args.parse_tracker_id("BLUTOPIA=https://aither.cc/torrents/415499")


def test_tracker_ids_persist_and_expose_tracker_field():
    meta = Meta()

    meta.set_tracker_ids({"AITHER": "50049"})

    assert meta.tracker_ids == {"AITHER": "50049"}
    assert meta.get_tracker_id("AITHER") == "50049"


@pytest.mark.parametrize(
    ("alias", "tracker_name"),
    [
        ("ptp", "PASSTHEPOPCORN"),
        ("hdb", "HDBITS"),
        ("bhd", "BEYONDHD"),
        ("blu", "BLUTOPIA"),
        ("oe", "ONLYENCODES"),
        ("huno", "HAWKEUNO"),
    ],
)
def test_tracker_id_aliases_are_stored_under_canonical_tracker_names(alias, tracker_name):
    meta = Meta()

    meta.set_tracker_ids({alias: "123"})

    assert meta.tracker_ids == {tracker_name: "123"}
    assert meta.get_tracker_id(alias) == "123"
    assert meta.get_tracker_id(tracker_name) == "123"


def test_restored_tracker_ids_are_canonicalized():
    meta = Meta({"tracker_ids": {"bhd": "123"}})

    assert meta.tracker_ids == {"BEYONDHD": "123"}
