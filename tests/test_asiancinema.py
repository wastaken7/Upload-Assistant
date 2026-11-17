# ruff: noqa: S101
import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.asiancinema import AsianCinema


def _tracker() -> AsianCinema:
    return AsianCinema({"DEFAULT": {}, "TRACKERS": {"ASIANCINEMA": {}}})


@pytest.mark.parametrize("category, expected", [("MOVIE", "1"), ("TV", "2"), ("MUSIC", "3")])
def test_category_ids(category: str, expected: str) -> None:
    tracker = _tracker()
    assert category in tracker.supported_categories
    assert asyncio.run(tracker.get_category_id(Meta(category=category))) == {"category_id": expected}


@pytest.mark.parametrize(
    "meta, expected",
    [
        (Meta(type="DISC"), "1"),
        (Meta(type="REMUX"), "7"),
        (Meta(type="WEBDL"), "9"),
        (Meta(type="HDTV", source="SDTV"), "13"),
        (Meta(type="HDTV"), "17"),
        (Meta(type="HDTV", source="UHDTV"), "19"),
        (Meta(category="MUSIC", format="FLAC"), "15"),
        (Meta(type="ENCODE"), "0"),
    ],
)
def test_type_ids(meta: Meta, expected: str) -> None:
    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": expected}


def test_mapping_modes_and_existing_resolutions() -> None:
    tracker = _tracker()
    assert asyncio.run(tracker.get_category_id(Meta(), reverse=True))["3"] == "MUSIC"
    assert asyncio.run(tracker.get_type_id(Meta(), mapping_only=True))["UHDTV"] == "19"
    assert asyncio.run(tracker.get_type_id(Meta(), type="SDTV")) == {"type_id": "13"}
    assert asyncio.run(tracker.get_resolution_id(Meta(resolution="1080p"))) == {"resolution_id": "2"}


def _bdmv_meta(**overrides: object) -> Meta:
    discs = [
        {"type": "BDMV", "name": "DISC_1", "summary": "Disc Title: Fictional Story Disc 1\nPlaylist: 00800.MPLS"},
        {"type": "BDMV", "name": "DISC_2", "summary": "Disc Title: Fictional Story Disc 2\nPlaylist: 00801.MPLS"},
        {"type": "BDMV", "name": "DISC_3", "summary": "Disc Title: Fictional Story Disc 3\nPlaylist: 00802.MPLS"},
    ]
    values: dict[str, object] = {"is_disc": "BDMV", "bdinfo": {"label": "DISC_1"}, "discs": discs}
    values.update(overrides)
    return Meta(**values)


def test_bdinfo_field_holds_every_disc_summary() -> None:
    bdinfo = asyncio.run(_tracker().get_bdinfo(_bdmv_meta()))["bdinfo"]
    assert bdinfo == "\n\n".join(f"Disc Title: Fictional Story Disc {n}\nPlaylist: 0080{n - 1}.MPLS" for n in (1, 2, 3))


def test_single_disc_bdinfo_reads_the_summary_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.trackers.UNIT3D import UNIT3D

    async def base_bdinfo(_self: UNIT3D, _meta: Meta) -> dict[str, str]:
        return {"bdinfo": "from file"}

    monkeypatch.setattr(UNIT3D, "get_bdinfo", base_bdinfo)
    meta = _bdmv_meta()
    meta.discs = meta.discs[:1]
    assert asyncio.run(_tracker().get_bdinfo(meta)) == {"bdinfo": "from file"}


@pytest.mark.parametrize("disc_count, disc_bdinfo", [(3, False), (1, True)])
def test_description_leaves_later_disc_bdinfo_to_the_bdinfo_field(monkeypatch: pytest.MonkeyPatch, disc_count: int, disc_bdinfo: bool) -> None:
    from src.get_desc import DescriptionBuilder

    calls: list[dict[str, object]] = []

    async def generator(_self: DescriptionBuilder, _meta: Meta, **kwargs: object) -> str:
        calls.append(kwargs)
        return "description"

    monkeypatch.setattr(DescriptionBuilder, "general_description_generator", generator)
    meta = _bdmv_meta()
    meta.discs = meta.discs[:disc_count]
    assert asyncio.run(_tracker().get_description(meta)) == {"description": "description"}
    assert calls == [{"disc_bdinfo": disc_bdinfo, "mediainfo": False, "nfo": False}]
