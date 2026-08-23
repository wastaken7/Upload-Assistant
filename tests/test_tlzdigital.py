import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.tlzdigital import TheLeachZone


def _tracker() -> TheLeachZone:
    return TheLeachZone({"DEFAULT": {}, "TRACKERS": {"THELEACHZONE": {}}})


@pytest.mark.parametrize(
    ("meta", "expected_type_id"),
    (
        (Meta(category="MOVIE", type="WEBDL"), "1"),
        (Meta(category="TV", type="WEBDL"), "3"),
        (Meta(category="TV", type="WEBDL", tv_pack=True), "4"),
        (Meta(category="TV", type="PACK"), "4"),
    ),
)
def test_tlzdigital_maps_standard_release_types(meta: Meta, expected_type_id: str):
    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": expected_type_id}  # noqa: S101


def test_tlzdigital_normalizes_category_case():
    tracker = _tracker()

    assert asyncio.run(tracker.get_category_id(Meta(category="movie"))) == {"category_id": "1"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="movie", type="webdl"))) == {"type_id": "1"}  # noqa: S101


@pytest.mark.parametrize(
    "meta",
    (
        Meta(category="MOVIE", type="CAM"),
        Meta(category="MOVIE", type="HDCAM"),
        Meta(category="MOVIE", source="R5"),
        Meta(category="MOVIE", type="WEBDL", pre_release=True),
        Meta(category="TV", type="TELESYNC"),
    ),
)
def test_tlzdigital_maps_pre_releases_to_cam_type(meta: Meta):
    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": "2"}  # noqa: S101


def test_tlzdigital_tv_pack_takes_priority_over_pre_release_type():
    meta = Meta(category="TV", type="CAM", pre_release=True, tv_pack=True)

    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": "4"}  # noqa: S101


def test_tlzdigital_does_not_infer_type_from_movie_title():
    meta = Meta(category="MOVIE", title="The Line", name="The.Line.2024.1080p.WEB-DL", type="WEBDL", source="WEB")

    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": "1"}  # noqa: S101


@pytest.mark.parametrize("source", ("LD", "LaserDisc", "LINE", "LINE AUDIO"))
def test_tlzdigital_does_not_treat_ambiguous_sources_as_cam(source: str):
    meta = Meta(category="MOVIE", type="ENCODE", source=source)

    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": "1"}  # noqa: S101
