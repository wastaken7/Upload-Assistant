import pytest

import web_ui.server as server


@pytest.mark.parametrize("query, enabled", [("", False), ("?screenshot=1", True), ("?screenshot=0", False)])
def test_screenshot_mode_is_explicit_and_loads_before_shared_helpers(query, enabled):
    with server.app.test_request_context("/" + query):
        html = server.index()
    assert isinstance(html, str)
    demo_script = "js/screenshot_mode.js"
    assert (demo_script in html) is enabled
    if enabled:
        assert html.index(demo_script) < html.index("js/shared_utils.js")


def test_screenshot_mode_does_not_bypass_authentication(monkeypatch):
    monkeypatch.setattr(server, "_is_authenticated", lambda: False)
    response = server.app.test_client().get("/?screenshot=1")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
