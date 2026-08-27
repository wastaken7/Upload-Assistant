import ast
from pathlib import Path

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

    comments, subsections = server._extract_example_metadata(example_path)

    assert subsections["DEFAULT/update_notification"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/default_torrent_client"] == "CLIENT SELECTION"
    assert subsections["DEFAULT/post_upload_hook_timeout"] == "POST-UPLOAD"
    assert "TRACKERS/default_trackers" not in subsections
    assert comments["DEFAULT/update_notification"] == ["Display an update notice."]


def test_current_example_config_exposes_workflow_subsections() -> None:
    example_path = server.CODE_DIR / "data" / "example_config.py"

    _, subsections = server._extract_example_metadata(example_path)

    assert subsections["DEFAULT/update_notification"] == "MAIN SETTINGS"
    assert subsections["DEFAULT/console_show_time"] == "LOGGING"
    assert subsections["DEFAULT/default_torrent_client"] == "CLIENT SELECTION"
    assert subsections["DEFAULT/post_upload_hook_timeout"] == "POST-UPLOAD"
    assert subsections["USENET/enabled"] == "GENERAL SETTINGS"
    assert subsections["USENET/nzb_output_dir"] == "OUTPUT PATHS"


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

    prepared = server._prepare_default_webui_section(example_section, comments, subsections)
    items = server._build_config_items(prepared, user_section, comments, subsections, ["DEFAULT"])
    client_selection = next(item for item in items if item["key"] == "CLIENT SELECTION")

    assert [child["key"] for child in client_selection["children"]] == [
        "default_torrent_client",
        "injecting_client_list",
        "searching_client_list",
    ]
    assert client_selection["children"][1]["value"] == ["qbittorrent", "rtorrent"]
    assert client_selection["children"][1]["source"] == "config"
    assert all(
        item["key"] not in {"injecting_client_list", "searching_client_list"}
        for item in items
    )


def test_torrent_client_template_prefers_primary_qbittorrent_example() -> None:
    example_clients = {
        "qbittorrent_searching": {"torrent_client": "qbit", "host": "searching"},
        "qbittorrent": {"torrent_client": "qbit", "host": "primary"},
        "rtorrent": {"torrent_client": "rtorrent", "host": "rtorrent"},
    }

    match = server._torrent_client_template(example_clients, "QBIT")

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

    prepared = server._prepare_torrent_client_webui_section(
        example_clients,
        user_clients,
        comments,
    )

    assert prepared["seedbox_qbit"] == example_clients["qbittorrent"]
    assert comments["TORRENT_CLIENTS/seedbox_qbit/qbit_url"] == [
        "qBittorrent WebUI URL."
    ]


def test_config_writer_supports_annotated_config_assignments() -> None:
    source = """from typing import Any

config: dict[str, Any] = {
    "TORRENT_CLIENTS": {
        "qbittorrent": {"torrent_client": "qbit"},
    },
}
"""

    updated = server._replace_config_value_in_source(
        source,
        ["TORRENT_CLIENTS", "seedbox"],
        repr({"torrent_client": "qbit"}),
    )
    tree = ast.parse(updated)
    config_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "config"
    )
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

    assert server._configured_torrent_client_names(user_config, example_config) == [
        "seedbox"
    ]


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

    assert server._configured_torrent_client_names(user_config, example_config) == [
        "qbittorrent",
        "rtorrent",
    ]
