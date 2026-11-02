from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import web_ui.server as server


def _static_url(filename: str) -> str:
    with server.app.test_request_context():
        return server.url_for("static", filename=filename)


def test_template_asset_urls_carry_the_file_modification_time() -> None:
    url = urlsplit(_static_url("js/app.js"))
    expected = (Path(server.app.static_folder) / "js" / "app.js").stat().st_mtime_ns
    assert url.path == "/static/js/app.js"
    assert parse_qs(url.query)["v"] == [str(expected)]


def test_versioned_static_assets_are_cached_long_term() -> None:
    response = server.app.test_client().get(_static_url("js/app.js"))
    assert response.status_code == 200
    assert response.cache_control.max_age == server._VERSIONED_STATIC_MAX_AGE
    assert response.cache_control.immutable is True
    assert response.cache_control.no_cache is None


def test_unversioned_images_are_cached_for_a_day_and_scripts_revalidate() -> None:
    client = server.app.test_client()

    image = client.get("/static/img/logo.png")
    assert image.cache_control.max_age == server._STATIC_IMAGE_MAX_AGE
    assert image.cache_control.no_cache is None

    script = client.get("/static/js/app.js")
    assert script.cache_control.no_cache
    assert script.cache_control.immutable is False
