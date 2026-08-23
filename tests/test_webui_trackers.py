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
