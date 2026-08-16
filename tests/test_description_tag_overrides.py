# ruff: noqa: S101

import asyncio

from src.get_desc import DescriptionBuilder
from src.meta import Meta


def test_tag_overrides_apply_to_description_text_fields():
    async def run():
        builder = DescriptionBuilder(
            "TEST",
            {
                "DEFAULT": {
                    "custom_signature": "default signature",
                    "screenshot_header": "default screenshots",
                    "tag_overrides": {
                        "MyAwesomeGroupTag": {
                            "custom_signature": "group signature",
                            "screenshot_header": "group screenshots",
                            "disc_menu_header": "",
                        },
                    },
                },
                "TRACKERS": {"TEST": {}},
            },
        )
        meta = Meta({"tag": "-myawesomegrouptag"})

        assert await builder.get_custom_signature(meta) == "group signature"
        assert await builder.screenshot_header(meta) == "group screenshots"
        assert builder._get_str_config("disc_menu_header", "default menu", meta) == ""

    asyncio.run(run())


def test_tracker_tag_override_has_precedence_and_untagged_releases_keep_existing_config():
    async def run():
        builder = DescriptionBuilder(
            "TEST",
            {
                "DEFAULT": {
                    "custom_signature": "default signature",
                    "tag_overrides": {"MyAwesomeGroupTag": {"custom_signature": "default group signature"}},
                },
                "TRACKERS": {
                    "TEST": {
                        "custom_signature": "tracker signature",
                        "tag_overrides": {"-myawesomegrouptag": {"custom_signature": "tracker group signature"}},
                    },
                },
            },
        )

        assert await builder.get_custom_signature(Meta({"tag": "MyAwesomeGroupTag"})) == "tracker group signature"
        assert await builder.get_custom_signature(Meta({"tag": "-OTHER"})) == "tracker signature"

    asyncio.run(run())
