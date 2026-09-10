# ruff: noqa: S101

import pytest

from src.region import get_service


@pytest.mark.parametrize(
    ("service_tag", "expected"),
    [
        ("AMZN", ("AMZN", "Amazon")),
        ("IQ", ("iQIYI", "iQIYI")),
        ("iQIYI", ("iQIYI", "iQIYI")),
        ("MY5", ("MY5", "Channel 5")),
        ("NF", ("NF", "Netflix")),
        ("DSCP", ("DSCP", "Discovery Plus")),
        ("JHS", ("JHS", "JioHotstar")),
        ("BB", ("BB", "BritBox")),
        ("VMX", ("VMX", "Vivamax")),
        ("GLOB", ("GLBO", "GloboSat Play")),
        ("HS", ("HTSR", "Hotstar")),
        ("BRTB", ("BB", "BritBox")),
        ("CORE", ("BCORE", "Sony Pictures Core")),
        ("VVMX", ("VMX", "Vivamax")),
        ("Vimeo", ("VMEO", "Vimeo")),
        ("35mm.online", ("35MM", "35mm.online")),
        ("AcornTV", ("ACORN", "Acorn TV")),
        ("DiscoveryPlus", ("DSCP", "Discovery Plus")),
        ("AppleTV+", ("ATVP", "Apple TV+")),
        ("STARZ", ("STZ", "Starz")),
        ("STZ", ("STZ", "Starz")),
        ("All4", ("ALL4", "Channel 4")),
        ("Channel 5", ("MY5", "Channel 5")),
        ("Sony.Pictures.Core", ("BCORE", "Sony Pictures Core")),
    ],
)
@pytest.mark.asyncio
async def test_get_service_detects_release_tag(service_tag: str, expected: tuple[str, str]) -> None:
    release_name = f"Example.Show.S01E01.1080p.{service_tag}.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == expected


@pytest.mark.parametrize(
    ("service_tag", "expected"),
    [
        ("Discovery.Plus", ("DSCP", "Discovery Plus")),
        ("Investigation.Discovery", ("ID", "Investigation Discovery")),
    ],
)
@pytest.mark.asyncio
async def test_get_service_prefers_longer_alias(service_tag: str, expected: tuple[str, str]) -> None:
    release_name = f"Example.Show.S01E01.1080p.{service_tag}.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == expected


@pytest.mark.asyncio
async def test_get_service_does_not_join_title_fields() -> None:
    release_name = "Example.Apple.S01E01.TV.1080p.Apple.TV.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == ("ATV", "Apple TV")


@pytest.mark.asyncio
async def test_get_service_excludes_compact_alias_in_episode_title() -> None:
    release_name = "Example.Show.S01E01.DiscoveryPlus.Adventures.1080p.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name) == ("", "")


@pytest.mark.asyncio
async def test_get_service_uses_tag_only_for_long_service_names() -> None:
    release_name = "Example.Show.S01E01.1080p.{}.WEB-DL.AAC2.0.H.264-GROUP"

    assert await get_service(release_name.format("Comedians.in.Cars.Getting.Coffee")) == ("", "")
    assert await get_service(release_name.format("ComediansinCarsGettingCoffee")) == ("", "")
    assert await get_service(release_name.format("CCGC")) == ("CCGC", "Comedians in Cars Getting Coffee")


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
