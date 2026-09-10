from src.trackers.GAZELLE.passthepopcorn import PassThePopcorn


def test_convert_bbcode_removes_unsupported_font_tags() -> None:
    tracker = object.__new__(PassThePopcorn)

    converted = tracker.convert_bbcode("Before [font=Courier New]formatted text[/font] after")

    assert converted == "Before formatted text after"  # noqa: S101


def test_convert_bbcode_clamps_unsupported_size_tags() -> None:
    tracker = object.__new__(PassThePopcorn)

    converted = tracker.convert_bbcode("[size=4]Normal[/size] [size=16]Oversized[/size]")

    assert converted == "[size=4]Normal[/size] [size=10]Oversized[/size]"  # noqa: S101
