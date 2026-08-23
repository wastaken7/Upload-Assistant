from __future__ import annotations

import ast
from pathlib import Path

import web_ui.server as server


ANNOTATED_CONFIG = '''from typing import Any

# Keep this module-level comment.
config: dict[str, Any] = {
    "DEFAULT": {
        # Number of screenshots.
        "screens": "4",
    },
    "TRACKERS": {
        "default_trackers": "",
        "AITHER": {
            "api_key": "",
        },
    },
}
'''


def _literal_config(source: str) -> dict[str, object]:
    tree = ast.parse(source)
    node = server._config_dict_node(tree)
    assert node is not None
    value = ast.literal_eval(node)
    assert isinstance(value, dict)
    return value


def test_configured_tracker_names_ignore_untouched_example_sections() -> None:
    example = {
        "TRACKERS": {
            "default_trackers": "",
            "AITHER": {"api_key": ""},
            "BLUTOPIA": {"api_key": "", "new_example_default": False},
            "ASIANCINEMA": {
                "api_key": "",
                "dynamic_hdr_plot_header": "[center]Plot[/center]",
            },
        }
    }
    user = {
        "TRACKERS": {
            "default_trackers": "AITHER",
            "AITHER": {"api_key": ""},
            "BLUTOPIA": {"api_key": "configured"},
            "ASIANCINEMA": {"api_key": "", "obsolete_legacy_key": "old default"},
            "CUSTOM": {"api_key": "configured"},
        }
    }

    assert server._configured_tracker_names(user, example, ["AITHER"]) == [
        "AITHER",
        "BLUTOPIA",
        "CUSTOM",
    ]


def test_replace_value_supports_annotated_config_and_preserves_comments() -> None:
    updated = server._replace_config_value_in_source(ANNOTATED_CONFIG, ["DEFAULT", "screens"], repr("8"))

    assert _literal_config(updated)["DEFAULT"] == {"screens": "8"}
    assert "config: dict[str, Any]" in updated
    assert "# Keep this module-level comment." in updated
    assert "# Number of screenshots." in updated


def test_replace_value_expands_sparse_annotated_config() -> None:
    source = "from typing import Any\n\nconfig: dict[str, Any] = {}\n"

    updated = server._replace_config_value_in_source(
        source,
        ["DEFAULT", "metadata_cache_services", "tmdb", "enabled"],
        "False",
    )

    assert _literal_config(updated) == {
        "DEFAULT": {"metadata_cache_services": {"tmdb": {"enabled": False}}}
    }
    assert "config: dict[str, Any]" in updated


def test_replace_value_handles_utf8_before_an_inline_target() -> None:
    source = "config: dict = {'DEFAULT': {'label': 'Café', 'screens': '4'}}\n"

    updated = server._replace_config_value_in_source(source, ["DEFAULT", "screens"], repr("8"))

    assert _literal_config(updated) == {
        "DEFAULT": {"label": "Café", "screens": "8"}
    }


def test_remove_key_supports_annotated_config_without_reformatting_module() -> None:
    updated = server._remove_config_key_in_source(ANNOTATED_CONFIG, ["TRACKERS", "AITHER"])

    assert _literal_config(updated)["TRACKERS"] == {"default_trackers": ""}
    assert "config: dict[str, Any]" in updated
    assert "# Keep this module-level comment." in updated
    assert '"AITHER"' not in updated


def test_extract_metadata_supports_annotated_example(tmp_path: Path) -> None:
    example = tmp_path / "example_config.py"
    example.write_text(
        '''from typing import Any

config: dict[str, Any] = {
    "TRACKERS": {
        # Which trackers do you want to upload to?
        # Available tracker: AITHER, BLUTOPIA
        "default_trackers": "",
    },
}
''',
        encoding="utf-8",
    )

    comments, _subsections = server._extract_example_metadata(example)

    assert comments["TRACKERS/default_trackers"] == [
        "Which trackers do you want to upload to?",
        "Available tracker: AITHER, BLUTOPIA",
    ]


def test_extract_metadata_uses_default_headings_as_subsections() -> None:
    example = Path(__file__).resolve().parents[1] / "data" / "example_config.py"

    _comments, subsections = server._extract_example_metadata(example)

    assert subsections["DEFAULT/update_notification"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/sfx_on_prompt"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/console_debug_markup"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/tracker_pass_checks"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/dupe_size_difference_tolerance"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/user_overrides"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/personal_release_groups"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/keep_meta"] == "METADATA CACHE"
    assert subsections["DEFAULT/ffmpeg_path"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/unrar_path"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/metadata_cache_enabled"] == "METADATA CACHE"
    assert (
        subsections["DEFAULT/tracker_metadata_cache_enabled"]
        == "TRACKER METADATA CACHE"
    )
    assert subsections["DEFAULT/img_host_1"] == "IMAGE HOSTING SETTINGS"
    assert subsections["DEFAULT/min_successful_image_uploads"] == "IMAGE HOSTING SETTINGS"
    assert subsections["DEFAULT/tmdb_api"] == "GETTING METADATA"
    assert subsections["DEFAULT/google_books_api_key"] == "GETTING METADATA"
    assert subsections["DEFAULT/tvdb_token"] == "GETTING METADATA"
    assert subsections["DEFAULT/btn_api"] == "GETTING METADATA"
    assert subsections["DEFAULT/music_enrichment_enabled"] == "GETTING METADATA"
    assert subsections["DEFAULT/music_discogs_token"] == "GETTING METADATA"
    assert subsections["DEFAULT/screens"] == "SCREENSHOT HANDLING"
    assert subsections["DEFAULT/cutoff_screens"] == "SCREENSHOT HANDLING"
    assert subsections["DEFAULT/add_logo"] == "DESCRIPTION SETTINGS"
    assert subsections["DEFAULT/default_torrent_client"] == "CLIENT SETUP"
    assert subsections["DEFAULT/skip_auto_torrent"] == "CLIENT SETUP"
    assert subsections["DEFAULT/prefer_max_16_torrent"] == "CLIENT SETUP"
    assert subsections["DEFAULT/use_sonarr"] == "ARR* INTEGRATION SETTINGS"
    assert subsections["DEFAULT/mkbrr"] == "TORRENT CREATION"
    assert subsections["DEFAULT/mkbrr_path"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/inject_delay"] == "POST UPLOAD"
    assert "TRACKERS/default_trackers" not in subsections
    assert not any(path.startswith("TRACKERS/") for path in subsections)


def test_build_items_marks_real_overrides_and_redacts_secrets() -> None:
    items = server._build_config_items(
        {"tvdb_token": "", "enabled": False},
        {"tvdb_token": "top-secret", "enabled": False},
        {},
        {},
        ["DEFAULT"],
    )
    by_key = {item["key"]: item for item in items}

    assert by_key["tvdb_token"]["value"] == "<REDACTED>"
    assert by_key["tvdb_token"]["sensitive"] is True
    assert by_key["tvdb_token"]["redacted"] is True
    assert by_key["tvdb_token"]["overridden"] is True
    assert by_key["enabled"]["overridden"] is False


def test_none_example_value_is_distinct_from_a_missing_path() -> None:
    config = {"DEFAULT": {"optional": None}}

    assert server._get_nested_value(config, ["DEFAULT", "optional"], server._MISSING_CONFIG_VALUE) is None
    assert server._get_nested_value(config, ["DEFAULT", "missing"], server._MISSING_CONFIG_VALUE) is server._MISSING_CONFIG_VALUE


def test_ip_control_reports_persistence_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "cfg_dir", tmp_path / "missing" / "config-dir")

    assert server._set_ip_control(["127.0.0.1"], []) is False


def test_token_store_reports_persistence_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        server.auth_mod,
        "set_api_tokens",
        lambda _store: (_ for _ in ()).throw(OSError("read-only")),
    )

    assert server._persist_token_store({}) is False
