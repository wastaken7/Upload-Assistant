# ruff: noqa: S101

import web_ui.server as server


def _verify_with_headers(headers: dict[str, str]) -> bool:
    with server.app.test_request_context("/api/config_options", headers=headers):
        return server._verify_same_origin()


def test_same_origin_accepts_matching_origin() -> None:
    assert _verify_with_headers(
        {
            "Host": "upload-assistant.local:5000",
            "Origin": "http://upload-assistant.local:5000",
        }
    )


def test_same_origin_accepts_browser_fetch_metadata_when_referer_is_unavailable() -> None:
    assert _verify_with_headers(
        {
            "Host": "internal-service:5000",
            "Sec-Fetch-Site": "same-origin",
        }
    )


def test_same_origin_rejects_cross_site_request() -> None:
    assert not _verify_with_headers(
        {
            "Host": "upload-assistant.local:5000",
            "Origin": "https://example.invalid",
            "Sec-Fetch-Site": "cross-site",
        }
    )


def test_same_origin_rejects_request_without_browser_origin_signals() -> None:
    assert not _verify_with_headers({"Host": "upload-assistant.local:5000"})
