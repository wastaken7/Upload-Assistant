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
    assert asyncio.run(bitporn.get_resolution_id(meta, "1080i")) == {"resolution_id": "11"}  # noqa: S101


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
