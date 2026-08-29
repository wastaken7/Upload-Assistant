from pathlib import Path

import pytest

from src.meta import Meta
from src.nfo import parse_nfo_streaming_service
from src.prep import Prep


@pytest.mark.parametrize(
    ("source_line", "expected"),
    [
        ("  Source       : Netflix", ("NF", "Netflix")),
        ("Source......: Netflix", ("NF", "Netflix")),
        ("Source: HULU", ("HULU", "Hulu")),
        ("Source       : AMAZON", ("AMZN", "Amazon Prime")),
        ("Source: Prime Video", ("AMZN", "Amazon Prime")),
        ("source: primevideo.example", ("AMZN", "Amazon Prime")),
        ("source: peacocktv.example", ("PCOK", "Peacock")),
        ("source: disneyplus.example", ("DSNP", "Disney+")),
        ("SOURCE == https://amazon.example/title", ("AMZN", "Amazon Prime")),
    ],
)
def test_parse_nfo_streaming_service_supports_common_source_fields(source_line: str, expected: tuple[str, str]) -> None:
    service_map = {
        "Amazon Prime": "AMZN",
        "AMZN": "AMZN",
        "Disney": "DSNY",
        "Disney+": "DSNP",
        "DSNP": "DSNP",
        "Hulu": "HULU",
        "HULU": "HULU",
        "Netflix": "NF",
        "NF": "NF",
        "Peacock": "PCOK",
        "PCOK": "PCOK",
        "Prime Video": "AMZN",
    }
    nfo = f"Example.Movie.2024.1080p.WEB.H264-GROUP\n{source_line}\n"

    result = parse_nfo_streaming_service(nfo, service_map)

    assert result is not None
    assert result[1:] == expected


@pytest.mark.parametrize(
    "source_line",
    [
        "Source: WEB",
        "Source: Amazon / iTunes",
        "Source: Apple",
        "Video Source: Netflix",
        "We are looking for Netflix cappers",
    ],
)
def test_parse_nfo_streaming_service_ignores_non_service_and_ambiguous_text(source_line: str) -> None:
    services = {"Amazon Prime": "AMZN", "Apple TV": "ATV", "Apple TV+": "ATVP", "iTunes": "iT", "Netflix": "NF"}
    assert parse_nfo_streaming_service(source_line, services) is None


@pytest.mark.asyncio
async def test_parse_scene_nfo_sets_service_for_movie(tmp_path: Path) -> None:
    nfo_file = tmp_path / "example.movie.2024.1080p.web.h264-group.nfo"
    nfo_file.write_text("Example.Movie.2024.1080p.WEB.H264-GROUP\nSource: Prime Video\n", encoding="utf-8")
    meta = Meta(category="MOVIE", scene=True, scene_nfo_file=nfo_file)

    await Prep.__new__(Prep).parse_scene_nfo(meta)

    assert meta.service == "AMZN"
    assert meta.service_longname == "Amazon Prime"
