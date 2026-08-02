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
