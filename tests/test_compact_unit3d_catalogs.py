# ruff: noqa: S101
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src import unit3d_catalogs as catalogs


@pytest.mark.parametrize("label", ["Example Studio", "Alternate Studio"])
def test_default_aliases_are_case_insensitive_and_follow_tracker_identity(tmp_path, monkeypatch, label):
    default = {"distributors": {"1": "Example Studio"}, "aliases": {"alternate studio": 1}}
    (tmp_path / "default.json").write_text(json.dumps(default), encoding="utf-8")
    (tmp_path / "example.json").write_text(json.dumps({"distributors": {"9": label}, "distributors_complete": True}), encoding="utf-8")
    monkeypatch.setattr(catalogs, "_CATALOG_DIR", tmp_path)
    catalogs._load_distributor_maps.cache_clear()
    try:
        assert catalogs.distributor_id("Alternate Studio") == "1"
        assert catalogs.distributor_id("alternate studio", "EXAMPLE") == "9"
        assert catalogs.distributor_name(9, "EXAMPLE") == label.upper()
    finally:
        catalogs._load_distributor_maps.cache_clear()


def test_cli_rejects_empty_input_before_writing_outputs(tmp_path):
    script = Path(__file__).resolve().parent.parent / "scripts/compact_unit3d_catalogs.py"
    default = tmp_path / "default.json"
    default.write_text(json.dumps({"regions": {"1": "BRA"}}), encoding="utf-8")
    source = tmp_path / "empty.json"
    source.write_text("", encoding="utf-8")
    output = tmp_path / "output"
    command = [sys.executable, str(script), str(source), "--default", str(default), "--output-dir", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - Repository script and test-owned paths.
    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("compact", [False, True])
def test_complete_catalog_exclusions_apply_after_expansion(tmp_path, monkeypatch, compact):
    default = {"distributors": {"1": "Example Studio", "2": "Other Studio"}, "aliases": {"EXAMPLE": 1}}
    catalog = {"distributors": dict(default["distributors"]), "distributors_complete": True, "excluded_ids": [1]}
    if compact:
        catalog = catalogs.compact_catalog(catalog, default)
    (tmp_path / "default.json").write_text(json.dumps(default), encoding="utf-8")
    (tmp_path / "example.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(catalogs, "_CATALOG_DIR", tmp_path)
    catalogs._load_distributor_maps.cache_clear()
    try:
        assert catalogs.distributor_id("EXAMPLE", "EXAMPLE") == ""
        assert catalogs.distributor_name(1, "EXAMPLE") == ""
        assert catalogs.distributor_id("Other Studio", "EXAMPLE") == "2"
    finally:
        catalogs._load_distributor_maps.cache_clear()


def test_compaction_preserves_added_changed_and_missing_ids():
    default = {"regions": {"1": "BRA", "2": "USA", "3": "GBR", "4": "FRA"}}
    original = {"regions": {"1": "BRA", "2": "USA", "3": "GER", "8": "JPN"}, "regions_complete": True, "aliases": {"EXAMPLE": 9}}
    result = catalogs.compact_catalog(original, default)
    assert result["default_ids"] == {"regions": ["1-2"]}
    assert result["regions"] == {"3": "GER", "8": "JPN"}
    assert catalogs.expand_catalog_section(result, default, "regions") == original["regions"]
    assert result["aliases"] == original["aliases"]
    assert catalogs.compact_catalog(result, default) == result
    default["regions"]["5"] = "ITA"
    assert "5" not in catalogs.expand_catalog_section(result, default, "regions")


def test_empty_complete_and_legacy_catalogs_keep_their_meaning():
    default = {"regions": {"1": "BRA"}, "distributors": {"1": "Example Studio"}}
    empty = {"regions": {}, "distributors": {}, "regions_complete": True, "distributors_complete": True}
    assert catalogs.compact_catalog(empty, default) == empty
    legacy = {"regions": {"1": "BRA"}, "distributors": {"1": "Example Studio"}, "excluded_ids": [2]}
    assert catalogs.compact_catalog(legacy, default) == legacy


def test_only_regions_and_distributors_are_compacted_even_when_other_defaults_match():
    sections = ("regions", "distributors", "categories", "types", "resolutions", "region_labels")
    default = {section: {"1": "Example"} for section in sections}
    original = {section: {"1": "Example", "2": "EXAMPLE"} for section in sections}
    original.update(regions_complete=True, distributors_complete=True)
    result = catalogs.compact_catalog(original, default)
    assert set(result["default_ids"]) == {"regions", "distributors"}
    for section in sections:
        if section in ("regions", "distributors"):
            assert result[section] == {"2": "EXAMPLE"}
            assert result["default_ids"][section] == [1]
            assert catalogs.expand_catalog_section(result, default, section) == original[section]
        else:
            assert result[section] == original[section]


@pytest.mark.parametrize("references", [["2-1"], ["1-1000000000"], ["1-2", 1], ["invalid"], [3]])
def test_invalid_or_missing_default_references_fail(references):
    with pytest.raises(ValueError):
        catalogs.expand_catalog_section({"regions": {}, "default_ids": {"regions": references}}, {"regions": {"1": "BRA", "2": "USA"}}, "regions")


def test_runtime_resolvers_preserve_full_catalog_behavior_after_compaction(tmp_path, monkeypatch):
    default = {"regions": {"1": "BRA", "2": "USA"}, "distributors": {"1": "Example Studio", "2": "Other Studio"}, "aliases": {"EXAMPLE": 1}}
    original = {"regions": {"1": "BRA", "9": "GBR"}, "distributors": {"1": "Example Studio", "9": "New Studio"}, "regions_complete": True, "distributors_complete": True}
    (tmp_path / "default.json").write_text(json.dumps(default), encoding="utf-8")
    (tmp_path / "example.json").write_text(json.dumps(catalogs.compact_catalog(original, default)), encoding="utf-8")
    monkeypatch.setattr(catalogs, "_CATALOG_DIR", tmp_path)
    catalogs._load_region_maps.cache_clear()
    catalogs._load_distributor_maps.cache_clear()
    try:
        assert catalogs.region_id("BRA", "EXAMPLE") == "1"
        assert catalogs.region_name(9, "EXAMPLE") == "GBR"
        assert catalogs.region_id("USA", "EXAMPLE") == ""
        assert catalogs.distributor_id("EXAMPLE", "EXAMPLE") == "1"
        assert catalogs.distributor_name(9, "EXAMPLE") == "NEW STUDIO"
        assert catalogs.distributor_id("Other Studio", "EXAMPLE") == ""
    finally:
        catalogs._load_region_maps.cache_clear()
        catalogs._load_distributor_maps.cache_clear()


def test_cli_writes_separate_outputs_and_refuses_overwrites(tmp_path):
    script = Path(__file__).resolve().parent.parent / "scripts/compact_unit3d_catalogs.py"
    default = tmp_path / "default.json"
    default.write_text(json.dumps({"regions": {"1": "BRA"}}), encoding="utf-8")
    source = tmp_path / "example.json"
    original = json.dumps({"regions": {"1": "BRA"}, "regions_complete": True})
    source.write_text(original, encoding="utf-8")
    command = [sys.executable, str(script), str(source), "--default", str(default), "--output-dir", str(tmp_path / "output")]
    success = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - Repository script and test-owned paths.
    assert success.returncode == 0, success.stderr
    result = json.loads((tmp_path / "output/example.json").read_text(encoding="utf-8"))
    assert result["default_ids"]["regions"] == [1]
    assert source.read_text(encoding="utf-8") == original
    failure = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - Repository script and test-owned paths.
    assert failure.returncode == 1
    assert json.loads((tmp_path / "output/example.json").read_text(encoding="utf-8")) == result
