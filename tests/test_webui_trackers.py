from pathlib import Path

import web_ui.server as server


def test_configured_trackers_include_defaults_and_non_default_setup() -> None:
    trackers_section = {
        "default_trackers": "AITHER",
        "AITHER": {"api_key": ""},
        "BLUTOPIA": {"api_key": "configured-key"},
        "FLOOD": {
            "api_key": "",
            "announce_url": "https://flood.st/announce/Custom_Announce_URL",
        },
    }
    example_trackers = {
        "AITHER": {"api_key": ""},
        "BLUTOPIA": {"api_key": ""},
        "FLOOD": {
            "api_key": "",
            "announce_url": "https://flood.st/announce/Custom_Announce_URL",
        },
    }
    supported_trackers = {"AITHER": object(), "BLUTOPIA": object(), "FLOOD": object()}

    configured = server._configured_tracker_names(
        trackers_section,
        example_trackers,
        ["AITHER"],
        supported_trackers,
    )

    assert configured == {"AITHER", "BLUTOPIA"}


def test_configured_trackers_include_cookie_and_legacy_btn_setup() -> None:
    supported_trackers = {
        "BROADCASTHENET": object(),
        "MAKINGOFF": object(),
        "UNSUPPORTED": object(),
    }

    configured = server._configured_tracker_names(
        {},
        {},
        [],
        supported_trackers,
        {"MAKINGOFF", "NOT_SUPPORTED"},
        {"DEFAULT": {"btn_api": "legacy-key"}},
    )

    assert configured == {"BROADCASTHENET", "MAKINGOFF"}


def test_whitespace_only_legacy_btn_key_is_not_configured() -> None:
    configured = server._configured_tracker_names(
        {},
        {},
        [],
        {"BROADCASTHENET": object()},
        user_config={"DEFAULT": {"btn_api": "  \t  "}},
    )

    assert configured == set()


def test_cookie_discovery_continues_after_one_lookup_failure(tmp_path: Path) -> None:
    valid_cookie = tmp_path / "MAKINGOFF.txt"
    valid_cookie.write_text("cookie data", encoding="utf-8")
    lookups: list[str] = []

    def find_cookie_file(_base_dir: str, tracker_name: str, _config: dict[str, object] | None) -> str:
        lookups.append(tracker_name)
        if tracker_name == "BROKEN":
            raise AttributeError("invalid cookie_file value")
        if tracker_name == "MAKINGOFF":
            return str(valid_cookie)
        return str(tmp_path / "missing.txt")

    configured = server._configured_cookie_tracker_names(
        {"BROKEN": object(), "MAKINGOFF": object(), "LATER": object()},
        {},
        tmp_path,
        find_cookie_file,
    )

    assert lookups == ["BROKEN", "MAKINGOFF", "LATER"]
    assert configured == {"MAKINGOFF"}
