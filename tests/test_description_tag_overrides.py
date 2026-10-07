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


def test_numeric_and_boolean_group_precedence_and_no_release_state_leak():
    config = {
        "DEFAULT": {
            "thumbnail_size": 350,
            "screens_per_row": 2,
            "episode_overview": True,
            "tag_overrides": {
                "FictionalGroup": {
                    "thumbnail_size": "400",
                    "screens_per_row": "3",
                    "episode_overview": False,
                    "multiScreens": 0,
                }
            },
        },
        "TRACKERS": {
            "TEST": {
                "thumbnail_size": 450,
                "screens_per_row": 4,
                "episode_overview": True,
                "tag_overrides": {"-FICTIONALGROUP": {"thumbnail_size": 500, "screens_per_row": None}},
            }
        },
    }
    builder = DescriptionBuilder("TEST", config)
    tagged = Meta(tag="-fictionalgroup")
    other = Meta(tag="-OtherGroup")
    assert builder._get_int_config("thumbnail_size", 350, tagged) == 500
    assert asyncio.run(builder.get_screens_per_row(tagged)) == 3
    assert builder._get_bool_config("episode_overview", True, tagged) is False
    assert builder._get_int_config("multiScreens", 2, tagged) == 0
    for meta in (other, Meta(), None):
        assert builder._get_int_config("thumbnail_size", 350, meta) == 450
        assert asyncio.run(builder.get_screens_per_row(meta)) == 4
        assert builder._get_bool_config("episode_overview", False, meta) is True
    assert config["TRACKERS"]["TEST"]["thumbnail_size"] == 450


def test_group_settings_reach_rendered_screenshots_logo_and_episode_info(tmp_path):
    async def run():
        builder = DescriptionBuilder(
            "TEST",
            {
                "DEFAULT": {
                    "thumbnail_size": 350,
                    "screens_per_row": 2,
                    "episode_overview": True,
                    "add_logo": True,
                    "logo_size": 300,
                    "tag_overrides": {
                        "FictionalGroup": {
                            "thumbnail_size": "400",
                            "screens_per_row": "3",
                            "episode_overview": False,
                            "add_logo": False,
                            "custom_signature": "Group signature",
                        }
                    },
                },
                "TRACKERS": {"TEST": {}},
            },
        )
        images = [{"web_url": f"https://example.test/{i}", "raw_url": f"https://example.test/{i}.png"} for i in range(6)]
        meta = Meta(
            tag="-FictionalGroup",
            category="TV",
            image_list=images,
            filelist=["Fictional.Series.mkv"],
            screens=6,
            tvmaze_episode_data={"episode_name": "Fictional episode", "overview": "Episode summary"},
            logo="https://example.test/logo.png",
            base_dir=str(tmp_path),
            uuid="release",
        )
        (tmp_path / "tmp" / "release").mkdir(parents=True)
        assert await builder.get_tv_info(meta) == ("", "")
        assert await builder.get_logo_section(meta) == ("", "")
        screenshots = await builder._handle_discs_and_screenshots(meta, [], images, 0, include_header=False)
        assert screenshots.count("[img=400]") == 6
        assert "2.png[/img][/url] \n" in screenshots
        assert "1.png[/img][/url] \n" not in screenshots
        assert await builder.get_custom_signature(meta) == "Group signature"
        meta.tag = "-OtherGroup"
        title, overview = await builder.get_tv_info(meta)
        assert title == "Fictional episode"
        assert overview == "Episode summary"
        assert await builder.get_logo_section(meta) == ("https://example.test/logo.png", "300")
        assert "[img=350]" in builder.format_screenshot(images[0]["web_url"], images[0]["raw_url"], meta=meta)

    asyncio.run(run())


def test_group_overrides_keep_tracker_mandatory_screenshot_format():
    builder = DescriptionBuilder(
        "TORRENTLEECH",
        {
            "DEFAULT": {"tag_overrides": {"FictionalGroup": {"screens_per_row": 3, "thumbnail_size": 400}}},
            "TRACKERS": {"TORRENTLEECH": {}},
        },
    )
    meta = Meta(tag="-FictionalGroup")
    assert asyncio.run(builder.get_screens_per_row(meta)) == 2
    assert "max-width: 350px;" in builder.format_screenshot("https://example.test/page", "https://example.test/raw.png", meta=meta)


def test_invalid_numeric_and_boolean_group_values_use_safe_defaults():
    builder = DescriptionBuilder(
        "TEST",
        {
            "DEFAULT": {"tag_overrides": {"FictionalGroup": {"thumbnail_size": "invalid", "episode_overview": []}}},
            "TRACKERS": {"TEST": {}},
        },
    )
    meta = Meta(tag="FictionalGroup")
    assert builder._get_int_config("thumbnail_size", 350, meta) == 350
    assert builder._get_bool_config("episode_overview", False, meta) is False


def test_group_settings_apply_through_general_generator(tmp_path):
    async def run():
        builder = DescriptionBuilder(
            "TEST",
            {
                "DEFAULT": {
                    "hide_screenshot_header_if_only_section": True,
                    "screenshot_header": "[b]Screenshots[/b]",
                    "tag_overrides": {
                        "FictionalGroup": {
                            "hide_screenshot_header_if_only_section": False,
                            "thumbnail_size": 400,
                            "custom_signature": "Group signature",
                        }
                    },
                },
                "TRACKERS": {"TEST": {}},
            },
        )
        (tmp_path / "tmp" / "release").mkdir(parents=True)
        meta = Meta(
            tag="FictionalGroup",
            category="MOVIE",
            base_dir=str(tmp_path),
            uuid="release",
            filelist=["Fictional.Movie.mkv"],
            screens=1,
            image_list=[{"web_url": "https://example.test/page", "raw_url": "https://example.test/image.png"}],
        )
        sections = dict.fromkeys(
            (
                "audio_spectrogram",
                "bluray",
                "book",
                "custom_header",
                "description",
                "dynamic_hdr_plot",
                "game",
                "languages",
                "logo",
                "mediainfo",
                "menu_screenshots",
                "music",
                "nfo",
                "tonemapped_header",
                "tv_info",
                "user_description",
            ),
            False,
        )
        result = await builder.general_description_generator(meta, **sections)
        assert "[b]Screenshots[/b]" in result
        assert "[img=400]" in result
        assert "Group signature" in result
        meta.tag = "OtherGroup"
        result = await builder.general_description_generator(meta, **sections)
        assert "[b]Screenshots[/b]" not in result
        assert "[img=350]" in result
        assert "Group signature" not in result

    asyncio.run(run())
