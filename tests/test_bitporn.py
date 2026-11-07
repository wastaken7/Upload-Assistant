import asyncio
from pathlib import Path

from src.meta import Meta
from src.screenshot_manifest import register as register_screenshots
from src.trackers.UNIT3D.bitporn import BitPorn
from src.trackersetup import tracker_class_map


def tracker() -> BitPorn:
    return BitPorn({"DEFAULT": {}, "TRACKERS": {"BITPORN": {}}})


def test_bitporn_is_registered_for_xxx_only() -> None:
    assert tracker_class_map["BITPORN"] is BitPorn  # noqa: S101
    assert tracker().supported_categories == ("XXX",)  # noqa: S101


def test_bitporn_infers_category_from_basename_only() -> None:
    bitporn = tracker()

    assert asyncio.run(bitporn.get_category_id(Meta(category="XXX", basename_no_ext="OnlyFans.2026.Creator.Big.Tits.1080p"))) == {  # noqa: S101
        "category_id": "10"
    }
    assert asyncio.run(bitporn.get_category_id(Meta(category="XXX", basename_no_ext="ManyVids.Creator.1080p"))) == {  # noqa: S101
        "category_id": "20"
    }
    assert asyncio.run(bitporn.get_category_id(Meta(category="XXX", basename_no_ext="Plain.Release.1080p"))) == {  # noqa: S101
        "category_id": "52"
    }


def test_bitporn_category_mappings_and_no_type_field() -> None:
    bitporn = tracker()
    meta = Meta(category="XXX", basename_no_ext="Release")

    assert asyncio.run(bitporn.get_category_id(meta, mapping_only=True))["Ai Generated"] == "54"  # noqa: S101
    assert asyncio.run(bitporn.get_category_id(meta, reverse=True))["52"] == "Uncategorized"  # noqa: S101
    assert asyncio.run(bitporn.get_type_id(meta)) == {"type_id": "1"}  # noqa: S101


def test_bitporn_resolution_mapping() -> None:
    bitporn = tracker()
    meta = Meta(category="XXX", resolution="2160p")

    assert asyncio.run(bitporn.get_resolution_id(meta)) == {"resolution_id": "18"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(meta, "2048p")) == {"resolution_id": "14"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(meta, "1080i")) == {"resolution_id": "13"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(meta, "1440p")) == {"resolution_id": "20"}  # noqa: S101
    # VR frames: BitPorn uploaders list 2880p as 6K and 4096p as 8K.
    assert asyncio.run(bitporn.get_resolution_id(meta, "2880p")) == {"resolution_id": "15"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(meta, "4096p")) == {"resolution_id": "16"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(Meta(category="XXX", resolution="OTHER"))) == {"resolution_id": "11"}  # noqa: S101


def test_bitporn_uses_its_image_upload_contract(tmp_path: Path) -> None:
    meta = Meta(category="XXX", base_dir=str(tmp_path), uuid="bitporn-images")
    screenshot_dir = tmp_path / "tmp" / meta.uuid / "screenshots"
    screenshot_dir.mkdir(parents=True)
    source = screenshot_dir / "contact-sheet.png"
    source.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (tmp_path / "tmp" / meta.uuid / "MEDIAINFO_CLEANPATH.txt").write_text("MediaInfo", encoding="utf-8")
    registered = register_screenshots(meta.base_dir, meta.uuid, [source], "main")
    meta.artwork_path = str(registered[0])
    meta.artwork_banner_path = str(registered[0])

    bitporn = tracker()
    files = asyncio.run(bitporn.get_additional_files(meta))
    data = asyncio.run(bitporn.get_data(meta))

    assert "description_images[0]" in files  # noqa: S101
    assert files["description_images[0]"][2] == "image/png"  # noqa: S101
    assert "cover" in files  # noqa: S101
    assert "banner" in files  # noqa: S101
    assert "torrent-cover" not in files  # noqa: S101
    assert "torrent-banner" not in files  # noqa: S101
    assert "[upimg1]" in data["description"]  # noqa: S101
    assert data["description_image_widths[1]"] == "450"  # noqa: S101


def _category(meta: Meta) -> str:
    bitporn = tracker()
    names = {value: name for name, value in bitporn.category_ids.items()}
    return names[asyncio.run(bitporn.get_category_id(meta))["category_id"]]


def _match(**values: object) -> dict[str, object]:
    return {"provider": "tpdb", "kind": "scenes", "id": "1", "title": "Fictional Scene", **values}


def test_bitporn_category_follows_the_release_format() -> None:
    # Format beats genre words in the name: a VR scene or a pack is listed as such.
    assert _category(Meta(category="XXX", basename_no_ext="[ExampleVR.com] Jane Example - Big Tits Day 8K")) == "VR"  # noqa: S101
    assert _category(Meta(category="XXX", basename_no_ext="ExampleStudio.2025.36Clips.XXX.HEVC")) == "Collection"  # noqa: S101
    videos = [f"C:/fake/clip{index}.mp4" for index in range(3)]
    assert _category(Meta(category="XXX", basename_no_ext="Jane Example videos", filelist=videos)) == "Collection"  # noqa: S101
    assert _category(Meta(category="XXX", basename_no_ext="Example Feature 13 XXX WEB-DL", xxx_match=_match(kind="movies"))) == "Movie"  # noqa: S101
    assert _category(Meta(category="XXX", basename_no_ext="ABCD-123", xxx_match=_match(kind="jav"))) == "Asian"  # noqa: S101
    assert _category(Meta(category="XXX", basename_no_ext="Jane Example clip", xxx_match=_match(studio="Jane Example", network="Manyvids"))) == "Fansite"  # noqa: S101
    assert _category(Meta(category="XXX", basename_no_ext="[ExampleJapanHD] 26.01.02 Jane Example", xxx_match=_match(studio="ExampleJapanHD"))) == "Asian"  # noqa: S101


def test_bitporn_category_uses_who_is_in_the_scene_not_the_acts() -> None:
    lesbian = Meta(category="XXX", basename_no_ext="ExampleStudio.26.01.02.Jane.Example", keywords=["Deep Throat", "Lesbian", "Anal"])
    acts_only = Meta(category="XXX", basename_no_ext="ExampleStudio.26.01.02.Jane.Example", keywords=["Deep Throat", "Anal", "Creampie"])

    assert _category(lesbian) == "Lesbian"  # noqa: S101
    # Acts are subjective as the main genre; Uncategorized is better than a guess.
    assert _category(acts_only) == "Uncategorized"  # noqa: S101



def test_bitporn_category_review_cases() -> None:
    # A word ending in "vr" is not a VR site.
    assert _category(Meta(category="XXX", basename_no_ext="Lavr Scene")) == "Uncategorized"  # noqa: S101
    # A movie in three parts is still a movie.
    parts = [f"C:/fake/part{index}.mp4" for index in range(3)]
    assert _category(Meta(category="XXX", basename_no_ext="Example Feature 13", filelist=parts, xxx_match=_match(kind="movies"))) == "Movie"  # noqa: S101
    # "Caucasian" is not an Asian studio.
    assert _category(Meta(category="XXX", basename_no_ext="Jane Example clip", xxx_match=_match(studio="Caucasian Example Productions"))) == "Uncategorized"  # noqa: S101


def test_bitporn_vr_resolution_uses_the_frame_height() -> None:
    bitporn = tracker()
    # UA rounds a 5760x2880 frame up to 4320p; BitPorn lists 2880p as 6K.
    assert asyncio.run(bitporn.get_resolution_id(Meta(category="XXX", resolution="4320p", video_height=2880))) == {"resolution_id": "15"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(Meta(category="XXX", resolution="4320p", video_height=4320))) == {"resolution_id": "16"}  # noqa: S101
    # An explicit resolution is kept.
    assert asyncio.run(bitporn.get_resolution_id(Meta(category="XXX", video_height=2880), "4320p")) == {"resolution_id": "16"}  # noqa: S101
