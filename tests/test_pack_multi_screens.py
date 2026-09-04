# ruff: noqa: S101
import asyncio

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.tracker_images import set_tracker_image_collection


def test_pack_multi_screens_only_zeroed_by_tracker_override() -> None:
    async def run() -> None:
        tracker = "TEST"
        builder = DescriptionBuilder(tracker, {"DEFAULT": {"multiScreens": 4}, "TRACKERS": {tracker: {}}})
        release_images = [{"web_url": "https://example.com/release", "raw_url": "https://example.com/release.jpg"}]
        override_images = [{"web_url": "https://example.com/override", "raw_url": "https://example.com/override.jpg"}]
        meta = Meta(category="TV", season=1, filelist=["episode-1.mkv", "episode-2.mkv"], image_list=release_images)
        calls = []

        async def capture_screenshot_args(_meta, _approved_image_hosts, images, multi_screens, _include_header=True):
            calls.append((images, multi_screens))
            return ""

        builder._handle_discs_and_screenshots = capture_screenshot_args
        disabled_sections = {
            "audio_spectrogram": False,
            "bluray": False,
            "book": False,
            "custom_header": False,
            "custom_signature": False,
            "description": False,
            "dynamic_hdr_plot": False,
            "game": False,
            "languages": False,
            "logo": False,
            "mediainfo": False,
            "menu_screenshots": False,
            "music": False,
            "nfo": False,
            "tonemapped_header": False,
            "tv_info": False,
            "ua_signature": False,
            "user_description": False,
        }

        await builder.general_description_generator(meta, **disabled_sections)
        set_tracker_image_collection(meta, tracker, "screenshots", override_images)
        await builder.general_description_generator(meta, **disabled_sections)

        assert calls == [(release_images, 4), (override_images, 0)]

    asyncio.run(run())
