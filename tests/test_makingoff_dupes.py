from src.trackers.makingoff import MakingOff


def test_extracts_height_from_current_and_legacy_post_layouts():
    assert MakingOff._extract_post_height("Resolução: 640x480") == 480  # noqa: S101
    assert MakingOff._extract_post_height("Release Movie.1951.480p.AMZN.WEB-DL") == 480  # noqa: S101
