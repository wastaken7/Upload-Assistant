# ruff: noqa: S101

import asyncio

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.blutopia import Blutopia

CONFIG = {"DEFAULT": {"multiScreens": 1}, "TRACKERS": {"BLUTOPIA": {}, "AITHER": {}, "UNIT3D": {}}}


def _image(name):
    return {"web_url": f"https://example.com/{name}", "raw_url": f"https://example.com/{name}.png"}


def _dvd(index):
    # Three blank lines inside the MediaInfo exercise the UNIT3D newline cleanup.
    filler = "x" * 2000
    return {
        "type": "DVD",
        "name": f"FICTIONAL_SHOW_D{index}",
        "vob": f"/media/Fictional Show/D{index}/VIDEO_TS/VTS_01_1.VOB",
        "ifo": f"/media/Fictional Show/D{index}/VIDEO_TS/VTS_01_0.IFO",
        "vob_mi": f"General\nDisc : {index}\n\n\n\nVideo\nNote : {filler}\n",
        "ifo_mi": f"General\nDisc : {index}\nMenu : {filler}\n",
    }


@pytest.fixture
def dvd_pack(tmp_path):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="pack",
        category="TV",
        screens=1,
        image_list=[_image("disc0")],
        discs=[_dvd(i) for i in range(4)],
    )
    for i in range(1, 4):
        meta[f"new_images_disc_{i}"] = [_image(f"disc{i}")]
    builder = DescriptionBuilder("BLUTOPIA", CONFIG)
    rendered = asyncio.run(builder._handle_discs_and_screenshots(meta, [], meta.image_list, 1))
    return meta, builder.tracker_specific_formats("BLUTOPIA", rendered)


def test_under_limit_description_is_unchanged(dvd_pack):
    meta, description = dvd_pack
    assert Blutopia(CONFIG).fit_description(meta, description) == description


def test_later_discs_lose_mediainfo_last_first(dvd_pack):
    meta, description = dvd_pack
    tracker = Blutopia(CONFIG)
    # Room for everything but the MediaInfo of the last two discs.
    disc_size = sum(len(block) for block in DescriptionBuilder.disc_mediainfo_blocks(meta.discs[3]))
    tracker.max_description_bytes = len(description.encode("utf-8")) - disc_size - 10

    fitted = tracker.fit_description(meta, description)

    assert len(fitted.encode("utf-8")) <= tracker.max_description_bytes
    for index in range(4):
        # Every disc keeps its name and screenshots.
        assert f"FICTIONAL_SHOW_D{index}:" in fitted
        assert f"https://example.com/disc{index}.png" in fitted
    assert "Disc : 0" in fitted
    assert "Disc : 1" in fitted
    assert "Disc : 2" not in fitted
    assert "Disc : 3" not in fitted
    for tag in ("spoiler", "code", "center"):
        assert fitted.count(f"[{tag}]") + fitted.count(f"[{tag}=") == fitted.count(f"[/{tag}]")


def test_first_disc_mediainfo_is_never_removed(dvd_pack):
    meta, description = dvd_pack
    tracker = Blutopia(CONFIG)
    tracker.max_description_bytes = 100

    fitted = tracker.fit_description(meta, description)

    assert "Disc : 0" in fitted
    assert all(f"Disc : {index}" not in fitted for index in range(1, 4))
    assert all(f"https://example.com/disc{index}.png" in fitted for index in range(4))


def test_limit_counts_utf8_bytes(dvd_pack):
    meta, description = dvd_pack
    tracker = UNIT3D(CONFIG, tracker_name="UNIT3D")
    accented = description + "é" * 100
    # Fits in characters, not in bytes.
    tracker.max_description_bytes = len(accented) + 50

    assert "Disc : 3" not in tracker.fit_description(meta, accented)


def test_aither_keeps_large_descriptions(dvd_pack):
    meta, description = dvd_pack
    large = description + "x" * 70000
    assert Aither(CONFIG).fit_description(meta, large) == large


def _render(meta, multi_screens=1):
    builder = DescriptionBuilder("BLUTOPIA", CONFIG)
    rendered = asyncio.run(builder._handle_discs_and_screenshots(meta, [], meta.image_list, multi_screens))
    return builder.tracker_specific_formats("BLUTOPIA", rendered)


def _bdmv(index, summary):
    return {"type": "BDMV", "name": f"FICTIONAL_FILM_D{index}", "summary": summary}


def test_identical_mediainfo_without_later_disc_sections_keeps_the_first_disc(tmp_path):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    # DVD MediaInfo leaves out the folder, so two discs can share identical blocks.
    disc = {**_dvd(0), "name": "FICTIONAL_SHOW_D0"}
    meta = Meta(base_dir=str(tmp_path), uuid="pack", category="TV", screens=1, image_list=[_image("disc0")], discs=[disc, {**disc, "name": "FICTIONAL_SHOW_D1"}])
    description = _render(meta, multi_screens=0)
    tracker = Blutopia(CONFIG)
    tracker.max_description_bytes = 100

    assert tracker.fit_description(meta, description) == description


def test_later_bdmv_disc_keeps_its_name_and_matches_formatted_summary(tmp_path):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    # UNIT3D formatting drops [hr], so the block must be matched after the same formatting.
    summary = "Disc Title: Fictional Film\n[hr]\n" + "y" * 4000
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="pack",
        category="MOVIE",
        screens=1,
        image_list=[_image("disc0")],
        discs=[_bdmv(0, summary), _bdmv(1, summary)],
        new_images_disc_1=[_image("disc1")],
    )
    description = _render(meta)
    tracker = Blutopia(CONFIG)
    tracker.max_description_bytes = len(description.encode("utf-8")) - 100

    fitted = tracker.fit_description(meta, description)

    assert "y" * 4000 not in fitted
    assert "[center]FICTIONAL_FILM_D1" in fitted
    assert "https://example.com/disc1.png" in fitted
    assert "[center]\n[/center]" not in fitted


def test_fitting_keeps_comparison_payloads_untouched(dvd_pack):
    meta, description = dvd_pack
    comparison = "[comparison=Source, Encode]\nhttps://example.com/a.png\n\n\n\nhttps://example.com/b.png\n[/comparison]"
    description = f"{comparison}\n{description}"
    tracker = Blutopia(CONFIG)
    tracker.max_description_bytes = len(description.encode("utf-8")) - 10

    fitted = tracker.fit_description(meta, description)

    assert "Disc : 3" not in fitted
    assert comparison in fitted
