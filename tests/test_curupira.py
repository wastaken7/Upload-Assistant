import asyncio

from src.meta import Meta
from src.trackers.USENET.curupira import Curupira


def test_dynamic_hdr_plots_are_preserved_in_curupira_screenshot_limit() -> None:
    meta = Meta(
        image_list=[{"raw_url": f"https://images.example/screenshot-{index}.png"} for index in range(6)],
        dynamic_hdr_plot_images=[{"raw_url": "https://images.example/dynamic-hdr.png"}],
    )
    tracker = Curupira({"TRACKERS": {"CURUPIRA": {}}})

    urls = asyncio.run(tracker.get_screens(meta))

    assert len(urls) == 6  # noqa: S101
    assert urls[-1] == "https://images.example/dynamic-hdr.png"  # noqa: S101
