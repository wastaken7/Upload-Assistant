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


def test_trackers_pass_parsed_as_int(tmp_path):
    args = Args({"DEFAULT": {"screens": 1}})
    meta, _, _ = args.parse([str(tmp_path), "--trackers-pass", "2"], Meta())
    assert meta.trackers_pass == 2
    assert isinstance(meta.trackers_pass, int)


def test_numeric_cli_arguments_parsed_as_correct_types(tmp_path):
    config = {"DEFAULT": {"screens": 2}}
    args = Args(config)

    cli_input = [
        str(tmp_path),
        "--trackers-pass",
        "3",
        "--screens",
        "5",
        "--limit-queue",
        "10",
        "--comparison_index",
        "2",
        "--randomized",
        "4",
        "--max-piece-size",
        "64",
        "--entropy",
        "32",
        "--douban",
        "123456",
        "--music-release-year",
        "2021",
        "--music-edition-year",
        "2023",
        "--qbit-bw-threshold",
        "500",
        "--qbit-bw-time",
        "30",
        "--year",
        "1994",
        "--dupe-size-difference-tolerance",
        "15.5",
        "--freeleech",
        "100",
        "--freeleech-until",
        "7",
        "--double-upload-until",
        "14",
    ]

    meta, _, _ = args.parse(cli_input, Meta())

    assert meta.trackers_pass == 3
    assert isinstance(meta.trackers_pass, int)

    assert meta.screens == 5
    assert isinstance(meta.screens, int)

    assert meta.limit_queue == 10
    assert isinstance(meta.limit_queue, int)

    assert meta.comparison_index == 2
    assert isinstance(meta.comparison_index, int)

    assert meta.randomized == 4
    assert isinstance(meta.randomized, int)

    assert meta.max_piece_size == 64
    assert isinstance(meta.max_piece_size, int)

    assert meta.entropy == 32
    assert isinstance(meta.entropy, int)

    assert meta.douban_manual == 123456
    assert isinstance(meta.douban_manual, int)

    assert meta.music_release_year == 2021
    assert isinstance(meta.music_release_year, int)

    assert meta.music_edition_year == 2023
    assert isinstance(meta.music_edition_year, int)

    assert meta.qbit_bandwidth_threshold == 500
    assert isinstance(meta.qbit_bandwidth_threshold, int)

    assert meta.qbit_bandwidth_time == 30
    assert isinstance(meta.qbit_bandwidth_time, int)

    assert meta.manual_year == 1994
    assert isinstance(meta.manual_year, int)

    assert meta.dupe_size_difference_tolerance == 15.5
    assert isinstance(meta.dupe_size_difference_tolerance, float)

    assert meta.freeleech == 100
    assert isinstance(meta.freeleech, int)

    assert meta.freeleech_until == 7
    assert isinstance(meta.freeleech_until, int)

    assert meta.double_upload_until == 14
    assert isinstance(meta.double_upload_until, int)


