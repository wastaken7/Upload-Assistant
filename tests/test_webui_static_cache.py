import web_ui.server as server


def test_template_asset_urls_carry_the_file_version() -> None:
    with server.app.test_request_context():
        url = server.url_for("static", filename="js/app.js")
    assert url.startswith("/static/js/app.js?v=")


def test_versioned_static_assets_are_cached_long_term() -> None:
    with server.app.test_request_context():
        url = server.url_for("static", filename="js/app.js")
    response = server.app.test_client().get(url)
    cache_control = response.headers["Cache-Control"]
    assert response.status_code == 200
    assert "immutable" in cache_control
    assert f"max-age={server._VERSIONED_STATIC_MAX_AGE}" in cache_control
    assert "no-cache" not in cache_control


def test_unversioned_images_are_cached_for_a_day_and_scripts_revalidate() -> None:
    client = server.app.test_client()

    image = client.get("/static/img/logo.png")
    assert f"max-age={server._STATIC_IMAGE_MAX_AGE}" in image.headers["Cache-Control"]
    assert "no-cache" not in image.headers["Cache-Control"]

    script = client.get("/static/js/app.js")
    assert "no-cache" in script.headers["Cache-Control"]
    assert "immutable" not in script.headers["Cache-Control"]
