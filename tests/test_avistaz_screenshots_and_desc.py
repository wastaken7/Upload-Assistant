import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from src.meta import Meta
from src.trackers.AVISTAZ.avistaz import AvistaZ


def test_avistaz_get_screenshots_only_uploads_menus_and_standard_screenshots(tmp_path: Path, monkeypatch) -> None:
    screens_dir = tmp_path / "tmp" / "test-uuid" / "screenshots"
    screens_dir.mkdir(parents=True)
    (screens_dir / "generated.png").write_bytes(b"local_png_data")

    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test-uuid",
        category="MOVIE",
        menu_images=[{"raw_url": "https://imgbox.com/menu1.png"}],
        image_list=[
            {"raw_url": "https://imgbox.com/screen1.png"},
            {"raw_url": "https://imgbox.com/screen2.png"},
        ],
        spectrograms_images=[{"raw_url": "https://imgbox.com/spectro.png"}],
        dynamic_hdr_plot_images=[{"raw_url": "https://imgbox.com/dvplot.png"}],
    )

    config = {
        "DEFAULT": {"add_dynamic_hdr_plot": True},
        "TRACKERS": {"AVISTAZ": {"add_audio_spectrogram": True, "add_dynamic_hdr_plot": True}},
    }
    az = AvistaZ(config)

    uploaded_urls: list[str] = []

    async def fake_img_host(_self_meta, _referer, _image_bytes, filename):
        return f"id_{filename}"

    async def fake_session_get(url):
        uploaded_urls.append(url)
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_png_data"
        mock_response.raise_for_status = lambda: None
        return mock_response

    monkeypatch.setattr(az, "img_host", fake_img_host)
    monkeypatch.setattr(az.session, "get", fake_session_get)

    results = asyncio.run(az.get_screenshots(meta))

    assert results == ["id_menu1.png", "id_generated.png"]  # noqa: S101
    assert "https://imgbox.com/screen1.png" not in uploaded_urls  # noqa: S101
    assert "https://imgbox.com/screen2.png" not in uploaded_urls  # noqa: S101
    assert "https://imgbox.com/spectro.png" not in uploaded_urls  # noqa: S101
    assert "https://imgbox.com/dvplot.png" not in uploaded_urls  # noqa: S101


def test_avistaz_edit_desc_includes_spectrograms_and_dv_plots(tmp_path: Path) -> None:
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test-uuid",
        category="MOVIE",
        audio_spectrogram=True,
        spectrograms_images=[{"web_url": "https://imgbox.com/spec_web", "raw_url": "https://images2.imgbox.com/spec_raw.png"}],
        dynamic_hdr_plot=True,
        dynamic_hdr_plot_images=[{"web_url": "https://imgbox.com/plot_web", "raw_url": "https://images2.imgbox.com/plot_raw.png"}],
    )

    config = {
        "DEFAULT": {"audio_spectrogram_header": "[center][b]Audio Spectrogram[/b][/center]"},
        "TRACKERS": {"AVISTAZ": {"add_audio_spectrogram": True, "add_dynamic_hdr_plot": True}},
    }
    az = AvistaZ(config)

    html_desc = asyncio.run(az.edit_desc(meta))

    assert "Audio Spectrogram" in html_desc  # noqa: S101
    assert "https://imgbox.com/spec_web" in html_desc  # noqa: S101
    assert "https://images2.imgbox.com/spec_raw.png" in html_desc  # noqa: S101
    assert "Dynamic HDR Metadata" in html_desc  # noqa: S101
    assert "https://imgbox.com/plot_web" in html_desc  # noqa: S101
    assert "https://images2.imgbox.com/plot_raw.png" in html_desc  # noqa: S101
    assert "<img" in html_desc  # noqa: S101


def test_avistaz_edit_desc_deduplicates_imported_tonemapped_header(tmp_path: Path) -> None:
    header = "[center]Screenshots have been adapted for SDR viewing, for reference only.[/center]"
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test-uuid",
        description_file_content=f"Imported description\n{header}",
        tonemapped=True,
    )
    config = {
        "DEFAULT": {"tonemapped_header": header},
        "TRACKERS": {"AVISTAZ": {}},
    }

    html_desc = asyncio.run(AvistaZ(config).edit_desc(meta))

    assert html_desc.count("adapted for SDR viewing") == 1  # noqa: S101
    assert "Imported description" in html_desc  # noqa: S101
