import ast
from pathlib import Path

import pytest

import web_ui.config_store as webui_config_store
import web_ui.context as webui_context
import web_ui.routes.config as config_routes
import web_ui.security as webui_security
import web_ui.server as server


def test_delimited_subsection_headers_do_not_require_blank_lines(tmp_path: Path) -> None:
    example_path = tmp_path / "example_config.py"
    example_path.write_text(
        """from typing import Any

config: dict[str, Any] = {
    "DEFAULT": {
        # --- MAIN SETTINGS ---
        # Display an update notice.
        "update_notification": True,
        # --- CLIENT SELECTION ---
        # Client used by default.
        "default_torrent_client": "qbittorrent",
        # --- POST-UPLOAD ---
        "post_upload_hook_timeout": 30,
    },
    "TRACKERS": {
        # Available trackers:
        # AITHER, BLUTOPIA
        "default_trackers": "",
    },
}
""",
        encoding="utf-8",
    )

    comments, subsections = webui_config_store._extract_example_metadata(example_path)

    assert subsections["DEFAULT/update_notification"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/default_torrent_client"] == "CLIENT SELECTION"
    assert subsections["DEFAULT/post_upload_hook_timeout"] == "POST-UPLOAD"
    assert "TRACKERS/default_trackers" not in subsections
    assert comments["DEFAULT/update_notification"] == ["Display an update notice."]


def test_current_example_config_exposes_workflow_subsections() -> None:
    example_path = webui_context.CODE_DIR / "data" / "example_config.py"

    _, subsections = webui_config_store._extract_example_metadata(example_path)

    assert subsections["DEFAULT/update_notification"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/console_show_time"] == "LOGGING"
    assert subsections["DEFAULT/stats_enabled"] == "LOCAL STATISTICS"
    assert subsections["DEFAULT/default_torrent_client"] == "CLIENT SELECTION"
    assert subsections["DEFAULT/post_upload_hook_timeout"] == "POST-UPLOAD"
    assert subsections["USENET/enabled"] == "GENERAL SETTINGS"
    assert subsections["USENET/nzb_output_dir"] == "OUTPUT PATHS"


def test_stats_enabled_is_grouped_with_main_settings_only_in_webui() -> None:
    example_path = webui_context.CODE_DIR / "data" / "example_config.py"
    example_config = webui_config_store._load_config_from_file(example_path)
    assert example_config is not None
    defaults = example_config["DEFAULT"]
    original_keys = list(defaults)
    comments, subsections = webui_config_store._extract_example_metadata(example_path)

    prepared = webui_config_store._prepare_default_webui_section(defaults, comments, subsections)
    items = webui_config_store._build_config_items(prepared, {"stats_enabled": True}, comments, subsections, ["DEFAULT"])

    headings = [item["key"] for item in items if item.get("subsection")]
    assert headings[:3] == ["MAIN SETTINGS", "WEBUI SETTINGS", "LOGGING"]
    assert headings.count("MAIN SETTINGS") == 1
    assert "LOCAL STATISTICS" not in headings
    main_settings = next(item for item in items if item["key"] == "MAIN SETTINGS")
    stats_items = [item for item in main_settings["children"] if item["key"] == "stats_enabled"]
    assert len(stats_items) == 1
    assert stats_items[0]["value"] is True
    assert stats_items[0]["example_value"] is False
    assert stats_items[0]["help"] == comments["DEFAULT/stats_enabled"]
    history_items = [item for item in main_settings["children"] if item["key"] == "history_enabled"]
    assert len(history_items) == 1
    assert history_items[0]["example_value"] is True
    assert list(defaults) == original_keys
    assert defaults["stats_enabled"] is False


@pytest.mark.parametrize(
    "removed_key,legacy_value",
    [("keep_meta", True), ("dvd_mediainfo_path", ""), ("dvd_mediainfo_path", "/legacy/DVD_MediaInfo")],
)
def test_removed_settings_are_not_exposed_from_existing_config(removed_key: str, legacy_value: object) -> None:
    """Hide retired defaults without discarding saved values or custom fields."""
    user_section = {removed_key: legacy_value, "stats_enabled": True, "custom_setting": "preserved"}
    items = webui_config_store._build_config_items(
        {"stats_enabled": False},
        user_section,
        {},
        {"DEFAULT/stats_enabled": "MAIN SETTINGS"},
        ["DEFAULT"],
    )

    assert [item["key"] for item in items] == ["MAIN SETTINGS", "custom_setting"]
    assert items[0]["children"][0]["value"] is True
    assert items[1]["value"] == "preserved"
    assert user_section[removed_key] == legacy_value


@pytest.mark.parametrize("keep_running,timeout", [(True, 60), (False, 0), (True, 150.5)])
def test_webui_session_settings_are_grouped_without_changing_saved_paths(keep_running, timeout) -> None:
    example_path = webui_context.CODE_DIR / "data" / "example_config.py"
    example_config = webui_config_store._load_config_from_file(example_path)
    assert example_config is not None
    defaults = example_config["DEFAULT"]
    original_defaults = dict(defaults)
    comments, subsections = webui_config_store._extract_example_metadata(example_path)
    user_defaults = {
        "webui_keep_uploads_on_disconnect": keep_running,
        "webui_unattended_prompt_timeout": timeout,
    }

    prepared = webui_config_store._prepare_default_webui_section(defaults, comments, subsections)
    items = webui_config_store._build_config_items(prepared, user_defaults, comments, subsections, ["DEFAULT"])

    assert [item["key"] for item in items[:3]] == ["MAIN SETTINGS", "WEBUI SETTINGS", "LOGGING"]
    session_sections = [item for item in items if item["key"] == "WEBUI SETTINGS"]
    assert len(session_sections) == 1
    assert session_sections[0]["subsection"] is True
    fields = {child["key"]: child for child in session_sections[0]["children"]}
    assert set(fields) == set(user_defaults)
    for key, value in user_defaults.items():
        assert fields[key]["value"] == value
        assert fields[key]["example_value"] == defaults[key]
        assert fields[key]["source"] == "config"
        assert fields[key]["help"] == comments[f"DEFAULT/{key}"]
    main_settings = next(item for item in items if item["key"] == "MAIN SETTINGS")
    assert not any(child["key"].startswith("webui_") for child in main_settings["children"])
    assert defaults == original_defaults


def test_current_example_config_exposes_merged_metadata_settings() -> None:
    example_path = webui_context.CODE_DIR / "data" / "example_config.py"
    example_config = webui_config_store._load_config_from_file(example_path)

    assert example_config is not None
    defaults = example_config["DEFAULT"]
    assert defaults["ggn_api_key"] == ""
    assert defaults["audible_domain"] == ""
    assert defaults["metadata_cache_services"]["gazellegames"] == {
        "enabled": True,
        "ttl_hours": 24,
    }

    _, subsections = webui_config_store._extract_example_metadata(example_path)
    assert subsections["DEFAULT/ggn_api_key"] == "METADATA API CREDENTIALS"
    assert subsections["DEFAULT/audible_domain"] == "GENERAL DESCRIPTION SETTINGS"
    assert subsections["DEFAULT/metadata_cache_services"] == "METADATA CACHING"


def test_default_client_lists_are_grouped_with_client_selection() -> None:
    example_section = {
        "before": True,
        "default_torrent_client": "qbittorrent",
        "after": False,
    }
    comments = {}
    subsections = {
        "DEFAULT/before": "MAIN SETTINGS",
        "DEFAULT/default_torrent_client": "CLIENT SELECTION",
        "DEFAULT/after": "METADATA CACHING",
    }
    user_section = {
        "injecting_client_list": ["qbittorrent", "rtorrent"],
        "searching_client_list": ["qbittorrent_searching"],
    }

    prepared = webui_config_store._prepare_default_webui_section(example_section, comments, subsections)
    items = webui_config_store._build_config_items(prepared, user_section, comments, subsections, ["DEFAULT"])
    client_selection = next(item for item in items if item["key"] == "CLIENT SELECTION")

    assert [child["key"] for child in client_selection["children"]] == [
        "default_torrent_client",
        "injecting_client_list",
        "searching_client_list",
    ]
    assert client_selection["children"][1]["value"] == ["qbittorrent", "rtorrent"]
    assert client_selection["children"][1]["source"] == "config"
    assert all(item["key"] not in {"injecting_client_list", "searching_client_list"} for item in items)


def test_default_arr_fields_expose_all_supported_optional_instances() -> None:
    example_section = {
        "use_sonarr": False,
        "sonarr_url": "http://localhost:8989",
        "sonarr_api_key": "",
        "use_radarr": False,
        "radarr_url": "http://localhost:7878",
        "radarr_api_key": "",
    }
    comments = {}
    subsections = {f"DEFAULT/{key}": "ARR INTEGRATION" for key in example_section}

    prepared = webui_config_store._prepare_default_webui_section(example_section, comments, subsections)

    assert list(prepared) == [
        "use_sonarr",
        "sonarr_url",
        "sonarr_api_key",
        "sonarr_url_1",
        "sonarr_api_key_1",
        "sonarr_url_2",
        "sonarr_api_key_2",
        "sonarr_url_3",
        "sonarr_api_key_3",
        "use_radarr",
        "radarr_url",
        "radarr_api_key",
        "radarr_url_1",
        "radarr_api_key_1",
        "radarr_url_2",
        "radarr_api_key_2",
        "radarr_url_3",
        "radarr_api_key_3",
        "injecting_client_list",
        "searching_client_list",
    ]
    assert prepared["sonarr_url_2"] == ""
    assert prepared["radarr_api_key_3"] == ""
    assert comments["DEFAULT/sonarr_url_1"][0] == ("Settings for Sonarr instance 2.")
    assert subsections["DEFAULT/sonarr_url_3"] == "ARR INTEGRATION"
    assert comments["DEFAULT/radarr_api_key_2"][0] == ("Settings for Radarr instance 3.")


def test_config_update_removes_all_optional_arr_instance_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    code_dir = tmp_path / "code"
    state_dir = tmp_path / "state"
    (code_dir / "data").mkdir(parents=True)
    (state_dir / "data").mkdir(parents=True)
    (code_dir / "data" / "example_config.py").write_text(
        "config = {'DEFAULT': {'sonarr_url_1': 'http://second:8989', 'sonarr_api_key_1': ''}}\n",
        encoding="utf-8",
    )
    config_path = state_dir / "data" / "config.py"
    config_path.write_text(
        "config = {'DEFAULT': {'sonarr_url_1': 'http://configured:8989', 'sonarr_api_key_1': ''}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(webui_context, "CODE_DIR", code_dir)
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(webui_security, "_write_audit_log", lambda *args, **kwargs: None)

    for key in ("sonarr_url_1", "sonarr_api_key_1"):
        with server.app.test_request_context(
            "/api/config_update",
            method="POST",
            json={"path": ["DEFAULT", key], "value": "", "remove": True},
        ):
            response = config_routes.config_update()
        assert response.get_json()["success"] is True

    updated_config = webui_config_store._load_config_from_file(config_path)
    assert updated_config == {"DEFAULT": {}}


def test_config_update_accepts_dvd_par_boolean(tmp_path: Path, monkeypatch) -> None:
    code_dir = tmp_path / "code"
    state_dir = tmp_path / "state"
    (code_dir / "data").mkdir(parents=True)
    (state_dir / "data").mkdir(parents=True)
    (code_dir / "data" / "example_config.py").write_text("config = {'DEFAULT': {'scale_dvd_screenshots_for_par': True}}\n", encoding="utf-8")
    config_path = state_dir / "data" / "config.py"
    config_path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(webui_context, "CODE_DIR", code_dir)
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(webui_security, "_write_audit_log", lambda *_args, **_kwargs: None)

    for value, expected in ((True, True), (False, False)):
        with server.app.test_request_context("/api/config_update", method="POST", json={"path": ["DEFAULT", "scale_dvd_screenshots_for_par"], "value": value}):
            response = config_routes.config_update()
        assert response.get_json()["success"] is True
        assert webui_config_store._load_config_from_file(config_path)["DEFAULT"]["scale_dvd_screenshots_for_par"] is expected


def test_torrent_client_template_prefers_primary_qbittorrent_example() -> None:
    example_clients = {
        "qbittorrent_searching": {"torrent_client": "qbit", "host": "searching"},
        "qbittorrent": {"torrent_client": "qbit", "host": "primary"},
        "rtorrent": {"torrent_client": "rtorrent", "host": "rtorrent"},
    }

    match = webui_config_store._torrent_client_template(example_clients, "QBIT")

    assert match == (
        "qbittorrent",
        {"torrent_client": "qbit", "host": "primary"},
    )


def test_custom_torrent_clients_inherit_template_fields_and_help() -> None:
    example_clients = {
        "qbittorrent": {
            "torrent_client": "qbit",
            "qbit_url": "http://127.0.0.1:8080",
        },
        "watch": {
            "torrent_client": "watch",
            "watch_folder": "",
        },
    }
    user_clients = {
        "seedbox_qbit": {
            "torrent_client": "qbit",
            "qbit_url": "https://seedbox.example",
        },
    }
    comments = {
        "TORRENT_CLIENTS/qbittorrent/qbit_url": ["qBittorrent WebUI URL."],
    }

    prepared = webui_config_store._prepare_torrent_client_webui_section(
        example_clients,
        user_clients,
        comments,
    )

    assert prepared["seedbox_qbit"] == example_clients["qbittorrent"]
    assert comments["TORRENT_CLIENTS/seedbox_qbit/qbit_url"] == ["qBittorrent WebUI URL."]


def test_config_writer_supports_annotated_config_assignments() -> None:
    source = """from typing import Any

config: dict[str, Any] = {
    "TORRENT_CLIENTS": {
        "qbittorrent": {"torrent_client": "qbit"},
    },
}
"""

    updated = webui_config_store._replace_config_value_in_source(
        source,
        ["TORRENT_CLIENTS", "seedbox"],
        repr({"torrent_client": "qbit"}),
    )
    tree = ast.parse(updated)
    config_assignment = next(node for node in tree.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config")
    loaded = ast.literal_eval(config_assignment.value)

    assert loaded["TORRENT_CLIENTS"]["seedbox"] == {"torrent_client": "qbit"}
    assert "config: dict[str, Any] = {" in updated


def test_untouched_torrent_client_templates_are_not_configured_clients() -> None:
    example_config = {
        "DEFAULT": {"default_torrent_client": ""},
        "TORRENT_CLIENTS": {
            "qbittorrent": {"torrent_client": "qbit", "qbit_url": "localhost"},
            "rtorrent": {"torrent_client": "rtorrent", "rtorrent_url": "localhost"},
        },
    }
    user_config = {
        "DEFAULT": {"default_torrent_client": ""},
        "TORRENT_CLIENTS": {
            "qbittorrent": {"torrent_client": "qbit", "qbit_url": "localhost"},
            "rtorrent": {"torrent_client": "rtorrent", "rtorrent_url": "localhost"},
            "seedbox": {"torrent_client": "qbit", "qbit_url": "localhost"},
        },
    }

    assert webui_config_store._configured_torrent_client_names(user_config, example_config) == ["seedbox"]


def test_referenced_or_edited_torrent_client_templates_remain_visible() -> None:
    example_config = {
        "TORRENT_CLIENTS": {
            "qbittorrent": {"torrent_client": "qbit", "qbit_url": "localhost"},
            "rtorrent": {"torrent_client": "rtorrent", "rtorrent_url": "localhost"},
        },
    }
    user_config = {
        "DEFAULT": {"default_torrent_client": "qbittorrent"},
        "TORRENT_CLIENTS": {
            "qbittorrent": {"torrent_client": "qbit", "qbit_url": "localhost"},
            "rtorrent": {"torrent_client": "rtorrent", "rtorrent_url": "seedbox"},
        },
    }

    assert webui_config_store._configured_torrent_client_names(user_config, example_config) == [
        "qbittorrent",
        "rtorrent",
    ]
