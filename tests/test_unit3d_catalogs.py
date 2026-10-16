# ruff: noqa: S101
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src import unit3d_catalogs as catalogs
from src.get_name import NameManager
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.locadora import Locadora


@pytest.mark.asyncio
async def test_locadora_uses_catalog_and_tracker_region_override():
    tracker = Locadora({"DEFAULT": {}, "TRACKERS": {"LOCADORA": {}}})
    assert await tracker.get_region_id(Meta(region="EUR")) == {"region_id": "244"}
    assert await tracker.get_region_id(Meta(region="INVALID", region_overrides={"LOCADORA": "EUR"})) == {"region_id": "244"}
    assert await tracker.get_region_id(Meta(region=None)) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["region", "distributor"])
@pytest.mark.parametrize("value", [None, "", "SKIPPED"])
async def test_missing_required_field_warning_describes_missing_information(monkeypatch, field, value):
    warning = Mock()
    monkeypatch.setattr("src.get_name.logger.warning", warning)
    manager = NameManager({})
    manager.common.unit3d_distributor_ids = AsyncMock(return_value="902" if field == "region" else "")
    meta = Meta(is_disc="BDMV", region="USA", distributor="Example Studio", unattended=True)
    setattr(meta, field, value)
    assert (await manager.missing_disc_info(meta, ["ULCX"]))[2] == ["ULCX"]
    assert any(f"missing {field} information" in call.args[0] for call in warning.call_args_list)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_region_and_distributor_return_empty_ids(value):
    assert catalogs.region_id(value) == ""
    assert catalogs.distributor_id(value) == ""


@pytest.mark.asyncio
async def test_none_region_prompts_as_missing():
    manager = NameManager({})
    manager.common.unit3d_distributor_ids = AsyncMock(return_value="902")
    manager._prompt_for_field = AsyncMock(return_value="USA")
    meta = Meta(is_disc="BDMV", region=None, distributor="Example Studio")
    result = await manager.missing_disc_info(meta, ["ULCX"])
    assert result == ("USA", "Example Studio", [])
    manager._prompt_for_field.assert_awaited_once_with(meta, "Region code", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("trackers", [["ULCX", "OLDTOONSWORLD"], ["OLDTOONSWORLD", "ULCX"]])
async def test_region_correction_is_isolated_and_used_only_by_its_tracker(trackers):
    manager = NameManager({})
    manager.common.unit3d_distributor_ids = AsyncMock(return_value="902")
    manager._prompt_for_field = AsyncMock(return_value="BRA")
    manager.common.unit3d_region_ids = AsyncMock(side_effect=lambda code, tracker: "1" if code == ("BRA" if tracker == "ULCX" else "USA") else "")
    meta = Meta(is_disc="BDMV", region="USA", distributor="Example Studio")
    assert await manager.missing_disc_info(meta, trackers) == ("USA", "Example Studio", [])
    assert meta.region == "USA"
    assert meta.region_overrides == {"ULCX": "BRA"}
    manager._prompt_for_field.assert_awaited_once()
    for name in trackers:
        tracker = UNIT3D({"DEFAULT": {}, "TRACKERS": {name: {}}}, tracker_name=name)
        tracker.common.unit3d_region_ids = manager.common.unit3d_region_ids
        assert await tracker.get_region_id(meta) == {"region_id": "1"}


@pytest.mark.parametrize(
    "tracker,code,expected", [("", "BRA", "33"), ("AITHER", "FIN", "244"), ("BLUTOPIA", "FIN", "246"), ("LST", "FIN", "245"), ("ASIANCINEMA", "USA", "14")]
)
def test_migrated_region_ids(tracker, code, expected):
    assert catalogs.region_id(code.lower(), tracker) == expected
    assert catalogs.region_name(expected, tracker) == code


@pytest.mark.usefixtures("exported_catalog")
def test_restricted_region_catalog_does_not_inherit_unsupported_countries():
    assert catalogs.region_id("USA", "EXAMPLE") == ""
    assert catalogs.region_name(33, "EXAMPLE") == ""
    assert catalogs.region_id("BRA", "UNLISTEDTRACKER") == "33"
    assert catalogs.region_name("invalid") == ""
    assert catalogs.region_name(None) == ""


@pytest.fixture
def exported_catalog(tmp_path, monkeypatch):
    default = Path(catalogs._CATALOG_DIR) / "default.json"
    (tmp_path / "default.json").write_text(default.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "example.json").write_text(
        json.dumps(
            {
                "regions": {"901": "BRA"},
                "distributors": {"902": "Example Studio"},
                "regions_complete": True,
                "distributors_complete": True,
                "categories": {"1": "Example Movies"},
                "types": {"2": "Example Encode"},
                "resolutions": {"3": "1080p"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(catalogs, "_CATALOG_DIR", tmp_path)
    catalogs._load_region_maps.cache_clear()
    catalogs._load_distributor_maps.cache_clear()
    yield tmp_path
    catalogs._load_region_maps.cache_clear()
    catalogs._load_distributor_maps.cache_clear()


@pytest.mark.usefixtures("exported_catalog")
def test_complete_export_is_authoritative():
    assert catalogs.region_id("BRA", "EXAMPLE") == "901"
    assert catalogs.region_name("901", "EXAMPLE") == "BRA"
    assert catalogs.region_id("USA", "EXAMPLE") == ""
    assert catalogs.region_name(33, "EXAMPLE") == ""
    assert catalogs.distributor_id("Example Studio", "EXAMPLE") == "902"
    assert catalogs.distributor_name(902, "EXAMPLE") == "EXAMPLE STUDIO"
    assert catalogs.distributor_id("BFI", "EXAMPLE") == ""


@pytest.mark.asyncio
@pytest.mark.usefixtures("exported_catalog")
async def test_tracker_upload_and_api_metadata_use_same_catalog():
    tracker = UNIT3D({"DEFAULT": {}, "TRACKERS": {"EXAMPLE": {}}}, tracker_name="EXAMPLE")
    assert await tracker.get_region_id(Meta(region="BRA")) == {"region_id": "901"}
    assert await tracker.get_distributor_id(Meta(distributor="Example Studio")) == {"distributor_id": "902"}
    assert await tracker.get_region_name("901") == "BRA"
    meta = Meta()
    await Common({})._apply_region_distributor(meta, {"region_id": "901", "distributor_id": "902"}, "EXAMPLE")
    assert (meta.region, meta.distributor) == ("BRA", "EXAMPLE STUDIO")


@pytest.mark.asyncio
async def test_invalid_required_region_can_be_corrected():
    manager = NameManager({})
    manager.common.unit3d_distributor_ids = AsyncMock(return_value="902")
    manager._prompt_for_field = AsyncMock(return_value="BRA")
    meta = Meta(is_disc="BDMV", region="INVALID", distributor="Example Studio")
    result = await manager.missing_disc_info(meta, ["ULCX"])
    assert result == ("INVALID", "Example Studio", [])
    assert meta.region_overrides == {"ULCX": "BRA"}
    tracker = UNIT3D({"DEFAULT": {}, "TRACKERS": {"ULCX": {}}}, tracker_name="ULCX")
    assert await tracker.get_region_id(meta) == {"region_id": catalogs.region_id("BRA", "ULCX")}
    manager._prompt_for_field.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_required_region_is_skipped_with_warning_unattended(monkeypatch):
    warning = Mock()
    monkeypatch.setattr("src.get_name.logger.warning", warning)
    manager = NameManager({})
    manager.common.unit3d_distributor_ids = AsyncMock(return_value="902")
    manager._prompt_for_field = AsyncMock()
    result = await manager.missing_disc_info(Meta(is_disc="BDMV", region="INVALID", distributor="Example Studio", unattended=True), ["ULCX"])
    assert result == ("INVALID", "Example Studio", ["ULCX"])
    assert any("Skipping upload to ULCX" in call.args[0] and "region" in call.args[0] for call in warning.call_args_list)
    manager._prompt_for_field.assert_not_awaited()
