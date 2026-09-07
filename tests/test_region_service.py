# ruff: noqa: S101

import pytest

from src.region import get_service


@pytest.mark.parametrize(
    ("service_tag", "expected"),
    [
        ("AMZN", ("AMZN", "Amazon")),
        ("IQ", ("iQIYI", "iQIYI")),
        ("iQIYI", ("iQIYI", "iQIYI")),
        ("MY5", ("MY5", "MY5")),
        ("NF", ("NF", "Netflix")),
    ],
)
@pytest.mark.asyncio
async def test_get_service_detects_release_tag(service_tag: str, expected: tuple[str, str]) -> None:
    release_name = f"Example.Show.S01E01.1080p.{service_tag}.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == expected


@pytest.mark.asyncio
async def test_get_service_does_not_join_title_fields() -> None:
    release_name = "Example.Apple.S01E01.TV.1080p.Apple.TV.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == ("ATV", "Apple TV")


@pytest.mark.parametrize(
    ("service_tag", "expected"),
    [
        ("", ("", "")),
        ("STAN.", ("STAN", "STAN")),
    ],
)
@pytest.mark.asyncio
async def test_get_service_distinguishes_episode_title_from_service_tag(service_tag: str, expected: tuple[str, str]) -> None:
    release_name = f"Example.Show.S01E01.Stan.Goes.on.a.Trip.1080p.{service_tag}WEB-DL.AAC2.0.H.264-GROUP.mkv"

    assert await get_service(release_name) == expected
