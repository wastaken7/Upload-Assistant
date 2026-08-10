import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.capybarabr import CapybaraBR
from src.trackers.UNIT3D.samaritano import Samaritano


@pytest.mark.parametrize(
    "tracker_class",
    [CapybaraBR, Samaritano],
)
@pytest.mark.parametrize(
    ("audio_languages", "expected_tag"),
    [
        (["Japanese", "English"], ""),
        (["Portuguese", "Portuguese"], ""),
        (["Portuguese", "English"], "DUAL"),
        (["Portuguese", "English", "Japanese"], "MULTI"),
    ],
)
def test_brazilian_trackers_audio_tags_require_portuguese(tracker_class: type[CapybaraBR] | type[Samaritano], audio_languages: list[str], expected_tag: str) -> None:
    meta = Meta(
        category="TV",
        name="Example Show 2026 WEB-DL - GROUP",
        title="Example Show",
        year=2026,
        tag="-GROUP",
        audio_languages=audio_languages,
        dual_audio=True,
    )

    name = asyncio.run(tracker_class({"TRACKERS": {}}).get_name(meta))["name"]

    assert (" DUAL-" in name) == (expected_tag == "DUAL")  # noqa: S101
    assert (" MULTI-" in name) == (expected_tag == "MULTI")  # noqa: S101


def test_capybarabr_formats_dvdrips_with_resolution_before_audio_and_codec() -> None:
    meta = Meta(
        category="MOVIE",
        name="Example Movie 2001 DVD x264 DVDRip DD 2.0-DDOS",
        title="Example Movie",
        year=2001,
        type="DVDRIP",
        resolution="480p",
        audio="DD 2.0",
        video_encode="x264",
        tag="-DDOS",
    )

    name = asyncio.run(CapybaraBR({"TRACKERS": {}}).get_name(meta))["name"]

    assert name == "Example Movie 2001 480p DVDRip DD2.0 x264-DDOS"  # noqa: S101
