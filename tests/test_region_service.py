# ruff: noqa: S101

import pytest

from src.region import get_service


@pytest.mark.parametrize(
    ("service_tag", "expected"),
    [
        ("AMZN", ("AMZN", "Amazon")),
        ("MY5", ("MY5", "MY5")),
        ("NF", ("NF", "Netflix")),
    ],
)
@pytest.mark.asyncio
async def test_get_service_detects_release_tag(service_tag: str, expected: tuple[str, str]) -> None:
    release_name = f"Example.Show.S01E01.1080p.{service_tag}.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == expected
