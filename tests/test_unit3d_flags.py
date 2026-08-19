"""Tests for UNIT3D tracker featured, doubleup, and sticky flags."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.args import Args
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D


def test_unit3d_flags_default():
    config = {"DEFAULT": {}, "TRACKERS": {"UNIT3D": {}}}
    tracker = UNIT3D(config, tracker_name="UNIT3D")
    meta = Meta()

    assert asyncio.run(tracker.get_featured(meta)) == {"featured": "0"}
    assert asyncio.run(tracker.get_doubleup(meta)) == {"doubleup": "0"}
    assert asyncio.run(tracker.get_sticky(meta)) == {"sticky": "0"}


def test_unit3d_flags_from_meta():
    config = {"DEFAULT": {}, "TRACKERS": {"UNIT3D": {}}}
    tracker = UNIT3D(config, tracker_name="UNIT3D")
    meta = Meta()
    meta.featured = True
    meta.doubleup = True
    meta.sticky = True

    assert asyncio.run(tracker.get_featured(meta)) == {"featured": "1"}
    assert asyncio.run(tracker.get_doubleup(meta)) == {"doubleup": "1"}
    assert asyncio.run(tracker.get_sticky(meta)) == {"sticky": "1"}


def test_unit3d_flags_from_config():
    config = {
        "DEFAULT": {},
        "TRACKERS": {
            "UNIT3D": {
                "featured": True,
                "doubleup": True,
                "sticky": True,
            }
        },
    }
    tracker = UNIT3D(config, tracker_name="UNIT3D")
    meta = Meta()

    assert asyncio.run(tracker.get_featured(meta)) == {"featured": "1"}
    assert asyncio.run(tracker.get_doubleup(meta)) == {"doubleup": "1"}
    assert asyncio.run(tracker.get_sticky(meta)) == {"sticky": "1"}


def test_unit3d_doubleup_from_double_upload_config():
    config = {
        "DEFAULT": {},
        "TRACKERS": {
            "UNIT3D": {
                "double_upload": True,
            }
        },
    }
    tracker = UNIT3D(config, tracker_name="UNIT3D")
    meta = Meta()

    assert asyncio.run(tracker.get_doubleup(meta)) == {"doubleup": "1"}


def test_unit3d_doubleup_from_double_up_config():
    config = {
        "DEFAULT": {},
        "TRACKERS": {
            "UNIT3D": {
                "double_up": True,
            }
        },
    }
    tracker = UNIT3D(config, tracker_name="UNIT3D")
    meta = Meta()

    assert asyncio.run(tracker.get_doubleup(meta)) == {"doubleup": "1"}


def test_unit3d_cli_args_parsing():
    config = {
        "DEFAULT": {
            "screens": 2,
            "img_host_1": "imgbox",
        },
        "TRACKERS": {},
        "DISCORD": {},
    }

    # Test short flags
    cli_args = ["/path/to/test.mkv", "-feat", "-dup", "-stk", "-ref", "-fl-until", "7", "-dupuntil", "14"]
    with patch("sys.argv", ["upload.py"] + cli_args):
        args_handler = Args(config)
        meta, _, _ = args_handler.parse(cli_args, Meta())
        assert meta.featured is True
        assert meta.doubleup is True
        assert meta.sticky is True
        assert meta.refundable is True
        assert meta.freeleech_until == 7
        assert meta.double_upload_until == 14

    # Test long flags
    cli_args_long = [
        "/path/to/test.mkv",
        "--featured",
        "--double-upload",
        "--sticky",
        "--refundable",
        "--freeleech-until",
        "3",
        "--double-upload-until",
        "6",
    ]
    with patch("sys.argv", ["upload.py"] + cli_args_long):
        args_handler = Args(config)
        meta, _, _ = args_handler.parse(cli_args_long, Meta())
        assert meta.featured is True
        assert meta.doubleup is True
        assert meta.sticky is True
        assert meta.refundable is True
        assert meta.freeleech_until == 3
        assert meta.double_upload_until == 6

    # Test negative duration values are rejected (set to 0)
    cli_args_negative = [
        "/path/to/test.mkv",
        "-fl-until",
        "-5",
        "-dupuntil",
        "-10",
        "-fl",
        "-1",
    ]
    with patch("sys.argv", ["upload.py"] + cli_args_negative):
        args_handler = Args(config)
        meta, _, _ = args_handler.parse(cli_args_negative, Meta())
        assert meta.freeleech_until == 0
        assert meta.double_upload_until == 0
        assert meta.freeleech == 0


def test_aither_additional_data_defaults():
    from src.trackers.UNIT3D.aither import Aither

    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}}}
    tracker = Aither(config)
    meta = Meta()

    data = asyncio.run(tracker.get_additional_data(meta))
    assert data.get("mod_queue_opt_in") == "0"
    assert "refundable" not in data
    assert "fl_until" not in data
    assert "du_until" not in data


def test_aither_additional_data_from_meta():
    from src.trackers.UNIT3D.aither import Aither

    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}}}
    tracker = Aither(config)
    meta = Meta()
    meta.refundable = True
    meta.freeleech_until = 7
    meta.double_upload_until = 14

    data = asyncio.run(tracker.get_additional_data(meta))
    assert data.get("refundable") is True
    assert data.get("fl_until") == 7
    assert data.get("du_until") == 14


def test_aither_additional_data_from_config():
    from src.trackers.UNIT3D.aither import Aither

    config = {
        "DEFAULT": {},
        "TRACKERS": {
            "AITHER": {
                "refundable": True,
                "freeleech_until": 5,
                "double_upload_until": 10,
            }
        },
    }
    tracker = Aither(config)
    meta = Meta()

    data = asyncio.run(tracker.get_additional_data(meta))
    assert data.get("refundable") is True
    assert data.get("fl_until") == 5
    assert data.get("du_until") == 10


def test_aither_additional_data_disabled_refundable():
    from src.trackers.UNIT3D.aither import Aither

    config = {
        "DEFAULT": {},
        "TRACKERS": {
            "AITHER": {
                "refundable": False,
            }
        },
    }
    tracker = Aither(config)
    meta = Meta()

    data = asyncio.run(tracker.get_additional_data(meta))
    assert "refundable" not in data


def test_configvalidator_unit3d_flags():
    from src.configvalidator import _validate_trackers_section

    # Valid tracker config with double_up and duration fields
    valid_trackers = {
        "AITHER": {
            "api_key": "key",
            "announce_url": "https://aither.cc/announce/key",
            "featured": True,
            "double_up": True,
            "doubleup": True,
            "double_upload": True,
            "sticky": True,
            "refundable": True,
            "freeleech_until": 7,
            "double_upload_until": 14,
        }
    }
    errors, warnings = _validate_trackers_section(valid_trackers, active_trackers=["AITHER"])
    assert not errors
    tracker_warnings = [w.message for w in warnings if w.key == "AITHER"]
    assert not tracker_warnings

    # Invalid tracker config with non-boolean double_up and negative durations
    invalid_trackers = {
        "AITHER": {
            "api_key": "key",
            "announce_url": "https://aither.cc/announce/key",
            "double_up": "false",
            "freeleech_until": -5,
            "double_upload_until": -10,
        }
    }
    errors, warnings = _validate_trackers_section(invalid_trackers, active_trackers=["AITHER"])
    assert not errors
    warning_messages = [w.message for w in warnings if w.key == "AITHER"]
    assert any("'double_up' must be a boolean" in msg for msg in warning_messages)
    assert any("'freeleech_until' must be a non-negative integer" in msg for msg in warning_messages)
    assert any("'double_upload_until' must be a non-negative integer" in msg for msg in warning_messages)


def test_merge_meta_preserves_saved_flags():
    from upload import merge_meta

    meta = Meta()
    saved_meta = {
        "title": "Saved Title",
        "featured": True,
        "doubleup": True,
        "sticky": True,
        "refundable": True,
        "freeleech_until": 7,
        "double_upload_until": 14,
    }

    asyncio.run(merge_meta(meta, saved_meta))
    assert meta.title == "Saved Title"
    assert meta.featured is True
    assert meta.doubleup is True
    assert meta.sticky is True
    assert meta.refundable is True
    assert meta.freeleech_until == 7
    assert meta.double_upload_until == 14


def test_merge_meta_overrides_when_explicitly_set():
    from upload import merge_meta

    meta = Meta()
    meta.title = "New Title"
    meta.featured = False
    meta.freeleech_until = 30
    saved_meta = {
        "title": "Saved Title",
        "featured": True,
        "freeleech_until": 7,
    }

    asyncio.run(merge_meta(meta, saved_meta))
    assert meta.title == "New Title"
    # featured in meta is False (default falsy), so saved True is preserved
    assert meta.featured is True
    # freeleech_until is explicitly non-zero in meta, so it overrides saved
    assert meta.freeleech_until == 30

