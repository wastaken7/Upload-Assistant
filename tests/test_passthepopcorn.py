from src.meta import Meta
from src.tracker_images import set_tracker_image_collection
from src.trackers.GAZELLE.passthepopcorn import PassThePopcorn


def test_convert_bbcode_removes_unsupported_font_tags() -> None:
    tracker = object.__new__(PassThePopcorn)

    converted = tracker.convert_bbcode("Before [font=Courier New]formatted text[/font] after")

    assert converted == "Before formatted text after"  # noqa: S101


def test_convert_bbcode_clamps_unsupported_size_tags() -> None:
    tracker = object.__new__(PassThePopcorn)

    converted = tracker.convert_bbcode("[size=4]Normal[/size] [size=16]Oversized[/size]")

    assert converted == "[size=4]Normal[/size] [size=10]Oversized[/size]"  # noqa: S101


def test_disc_menu_images_precede_movie_screenshots_in_description() -> None:
    tracker = object.__new__(PassThePopcorn)
    meta = Meta(
        is_disc="DVD",
        image_list=[{"raw_url": "https://imgbox.com/movie.png"}],
        menu_images=[{"raw_url": "https://imgbox.com/original-menu.png"}],
    )
    rehosted_menu = {"raw_url": "https://imgbox.com/menu.png"}
    set_tracker_image_collection(meta, tracker.tracker, "menu_images", [rehosted_menu])

    assert tracker._description_images(meta) == [rehosted_menu, meta.image_list[0]]  # noqa: S101
    assert tracker._description_image_limit(meta, 6) == 7  # noqa: S101
