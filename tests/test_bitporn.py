import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.bitporn import BitPorn
from src.trackersetup import tracker_class_map


def tracker() -> BitPorn:
    return BitPorn({"TRACKERS": {"BITPORN": {}}})


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
    assert asyncio.run(bitporn.get_type_id(meta)) == {}  # noqa: S101


def test_bitporn_resolution_mapping() -> None:
    bitporn = tracker()
    meta = Meta(category="XXX", resolution="2160p")

    assert asyncio.run(bitporn.get_resolution_id(meta)) == {"resolution_id": "18"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(meta, "2048p")) == {"resolution_id": "14"}  # noqa: S101
    assert asyncio.run(bitporn.get_resolution_id(meta, "1080i")) == {"resolution_id": "11"}  # noqa: S101
