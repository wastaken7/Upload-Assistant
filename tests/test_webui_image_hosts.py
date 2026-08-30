from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_config_page_loads_image_host_fallback_before_app() -> None:
    template = (ROOT / "web_ui" / "templates" / "config.html").read_text(encoding="utf-8")
    fallback = "js/config_image_host_fallback.js"
    app = "js/config_app.js"

    assert fallback in template
    assert template.index(fallback) < template.index(app)


def test_image_host_fallback_contains_common_hosts() -> None:
    script = (ROOT / "web_ui" / "static" / "js" / "config_image_host_fallback.js").read_text(encoding="utf-8")

    for host in ("ptscreens", "imgbb", "imgbox", "pixhost"):
        assert f'"{host}"' in script

    assert 'includes("/api/config_options")' in script
    assert 'startsWith("img_host_")' in script
