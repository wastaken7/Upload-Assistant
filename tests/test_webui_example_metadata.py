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
