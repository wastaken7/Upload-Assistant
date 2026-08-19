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
