# ruff: noqa: S101

from pathlib import Path


def test_webui_catalog_exposes_usenet_episodes_only() -> None:
    source = (Path(__file__).parents[1] / "web_ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert 'label: "--usenet-episodes-only"' in source
    assert 'placeholder: "CURUPIRA,NZBNEST"' in source
