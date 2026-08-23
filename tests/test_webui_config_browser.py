from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import abort
from flask.sessions import SecureCookieSessionInterface
from werkzeug.serving import make_server

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def config_browser_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    state_dir = tmp_path_factory.mktemp("config-browser-state")
    data_dir = state_dir / "data"
    data_dir.mkdir()
    code_dir = Path(__file__).resolve().parents[1]
    shutil.copy2(code_dir / "data" / "example_config.py", data_dir / "config.py")

    auth_config_dir = state_dir / "auth-config"
    auth_config_dir.mkdir()
    isolated_environment = {
        "APPDATA": str(auth_config_dir),
        "SESSION_SECRET": (
            "config-browser-test-session-secret-that-never-leaves-this-process"
        ),
        "UA_DATA_DIR": str(state_dir),
        "XDG_CONFIG_HOME": str(auth_config_dir),
    }
    original_environment = {
        key: os.environ.get(key) for key in isolated_environment
    }
    os.environ.update(isolated_environment)

    server = None
    http_server = None
    thread = None

    try:
        import web_ui.server as server

        original_state_dir = server.STATE_DIR
        original_session_interface = server.app.session_interface
        original_testing = server.app.config.get("TESTING", False)
        original_secret_key = server.app.secret_key

        server.STATE_DIR = state_dir
        server.app.config["TESTING"] = True
        server.app.secret_key = "config-browser-test-secret"
        server.app.session_interface = SecureCookieSessionInterface()

        endpoint = "_config_browser_test_login"
        if endpoint not in server.app.view_functions:

            def browser_test_login():
                if not server.app.testing:
                    return abort(404)
                server._session_set("authenticated", True)
                server._session_set("username", "browser-test")
                server._session_set("csrf_token", "config-browser-test-csrf-token")
                return "Authenticated for config browser test"

            server.app.add_url_rule(
                "/__config_browser_test_login",
                endpoint,
                browser_test_login,
                methods=["GET"],
            )

        http_server = make_server("127.0.0.1", 0, server.app, threaded=True)
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()

        yield f"http://127.0.0.1:{http_server.server_port}"
    finally:
        if http_server is not None:
            http_server.shutdown()
        if thread is not None:
            thread.join(timeout=5)
        if server is not None:
            server.STATE_DIR = original_state_dir
            server.app.session_interface = original_session_interface
            server.app.config["TESTING"] = original_testing
            server.app.secret_key = original_secret_key
        for key, original_value in original_environment.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


def test_config_accordions_and_responsive_layout(config_browser_server: str) -> None:
    with playwright.sync_playwright() as playwright_runtime:
        browser_executable = os.environ.get("UA_BROWSER_TEST_EXECUTABLE")
        launch_options = (
            {"executable_path": browser_executable} if browser_executable else {}
        )
        browser = playwright_runtime.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(
            f"{config_browser_server}/__config_browser_test_login",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        page.goto(
            f"{config_browser_server}/config",
            referer=f"{config_browser_server}/",
            wait_until="networkidle",
            timeout=60_000,
        )
        page.get_by_role("button", name="DEFAULT", exact=True).wait_for(timeout=30_000)

        expected_theme_variables = {
            "graphite": {
                "obsidian": "#0b1220",
                "stone": "#1f2937",
            },
            "obsidian": {
                "obsidian": "#0c0a09",
                "stone": "#292524",
            },
        }
        rendered_theme_surfaces = {}
        surface_colors_script = """element => ({
            bar: getComputedStyle(element).backgroundColor,
            active: getComputedStyle(element.querySelector('button')).backgroundColor,
        })"""

        for theme_id, expected_variables in expected_theme_variables.items():
            page.get_by_label("Color theme").select_option(theme_id)
            page.wait_for_function(
                "theme => document.documentElement.dataset.uaTheme === theme",
                arg=theme_id,
            )
            theme_variables = page.evaluate(
                """() => {
                    const styles = getComputedStyle(document.documentElement);
                    return {
                        obsidian: styles.getPropertyValue('--ua-obsidian').trim(),
                        stone: styles.getPropertyValue('--ua-stone').trim(),
                    };
                }"""
            )
            assert theme_variables == expected_variables

            page.get_by_role("button", name="TRACKERS", exact=True).click()
            tracker_tabs = page.get_by_test_id("tracker-category-tabs")
            tracker_colors = tracker_tabs.evaluate(surface_colors_script)

            page.get_by_role("button", name="TORRENT_CLIENTS", exact=True).click()
            standard_subtabs = page.get_by_test_id("config-subtabs")
            standard_colors = standard_subtabs.evaluate(surface_colors_script)
            assert tracker_colors == standard_colors

            page.get_by_role("button", name="DEFAULT", exact=True).click()
            page.get_by_role("button", name="Metadata", exact=True).click()
            translucent_panel_color = page.get_by_test_id(
                "metadata-cache-services-accordion"
            ).evaluate("element => getComputedStyle(element).backgroundColor")
            rendered_theme_surfaces[theme_id] = {
                **tracker_colors,
                "translucent_panel": translucent_panel_color,
            }

        assert rendered_theme_surfaces["graphite"] != rendered_theme_surfaces["obsidian"]

        page.get_by_role("button", name="Toggle theme", exact=True).click()
        page.wait_for_function(
            "() => localStorage.getItem('ua_config_theme') === 'light'"
        )
        page.get_by_role("button", name="TRACKERS", exact=True).click()
        light_tracker_colors = page.get_by_test_id("tracker-category-tabs").evaluate(
            surface_colors_script
        )
        page.get_by_role("button", name="TORRENT_CLIENTS", exact=True).click()
        light_standard_colors = page.get_by_test_id("config-subtabs").evaluate(
            surface_colors_script
        )
        assert light_tracker_colors == light_standard_colors

        page.get_by_role("button", name="Toggle theme", exact=True).click()
        page.wait_for_function(
            "() => localStorage.getItem('ua_config_theme') === 'dark'"
        )

        page.get_by_role("button", name="DEFAULT", exact=True).click()

        expected_panel_headings = {
            "Main": ["Updates"],
            "Image Hosting": ["Upload Behavior"],
            "Screenshot Handling": ["Screenshot Basics"],
            "Description": ["General Layout"],
            "Client Setup": [
                "Upload Scheduling",
                "Client Selection",
                "Client Lists",
            ],
            "Torrent Creation": ["Torrent Generation"],
        }
        for tab_label, panel_headings in expected_panel_headings.items():
            page.get_by_role("button", name=tab_label, exact=True).click()
            for panel_heading in panel_headings:
                page.get_by_text(panel_heading, exact=True).wait_for()

        page.get_by_role("button", name="Metadata", exact=True).click()

        metadata_accordion = page.get_by_test_id("metadata-cache-services-accordion")
        metadata_toggle = metadata_accordion.locator("button").first
        assert metadata_toggle.get_attribute("aria-expanded") == "false"
        metadata_toggle.click()
        assert metadata_toggle.get_attribute("aria-expanded") == "true"

        service_row = page.get_by_test_id("metadata-cache-service-row").first
        service_columns = service_row.locator(":scope > div")
        mobile_service_label = service_columns.nth(0).bounding_box()
        mobile_service_fields = service_columns.nth(1).bounding_box()
        assert mobile_service_label is not None
        assert mobile_service_fields is not None
        assert abs(mobile_service_label["x"] - mobile_service_fields["x"]) <= 1
        assert mobile_service_fields["y"] >= mobile_service_label["y"] + mobile_service_label["height"] - 1

        viewport_metrics = page.evaluate(
            """() => ({
                viewportWidth: window.innerWidth,
                pageWidth: document.documentElement.scrollWidth,
                tabOverflow: Array.from(document.querySelectorAll('.ua-config-tabs'))
                    .some((tabs) => tabs.scrollWidth > tabs.clientWidth),
            })"""
        )
        assert viewport_metrics["pageWidth"] <= viewport_metrics["viewportWidth"] + 1
        assert viewport_metrics["tabOverflow"] is True

        metadata_toggle.click()
        assert metadata_toggle.get_attribute("aria-expanded") == "false"

        page.get_by_role("button", name="TORRENT_CLIENTS", exact=True).click()
        client_accordion = page.get_by_test_id("torrent-client-accordion").first
        client_toggle = client_accordion.locator("button").first
        assert client_toggle.get_attribute("aria-expanded") == "false"
        client_toggle.click()
        assert client_toggle.get_attribute("aria-expanded") == "true"
        controlled_id = client_toggle.get_attribute("aria-controls")
        assert controlled_id
        assert page.locator(f"#{controlled_id}").is_visible()

        page.set_viewport_size({"width": 1280, "height": 900})
        page.get_by_role("button", name="DEFAULT", exact=True).click()
        page.get_by_role("button", name="Metadata", exact=True).click()
        metadata_toggle = page.get_by_test_id("metadata-cache-services-accordion").locator("button").first
        metadata_toggle.click()
        service_row = page.get_by_test_id("metadata-cache-service-row").first
        service_columns = service_row.locator(":scope > div")
        desktop_service_label = service_columns.nth(0).bounding_box()
        desktop_service_fields = service_columns.nth(1).bounding_box()
        assert desktop_service_label is not None
        assert desktop_service_fields is not None
        assert desktop_service_fields["x"] >= desktop_service_label["x"] + desktop_service_label["width"] - 1

        browser.close()
