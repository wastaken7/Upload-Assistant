# ruff: noqa: S101

from src.meta import Meta


def test_populate_cast_merges_sources_in_priority_order() -> None:
    meta = Meta(
        manual_cast=["Manual Name", "Shared Name"],
        imdb_info={"stars": ["IMDb Name", "shared name"]},
        tmdb_cast=["TMDb Name", "IMDb Name"],
    )

    meta.populate_cast()

    assert meta.cast == ["Manual Name", "Shared Name", "IMDb Name", "TMDb Name"]


def test_populate_cast_normalizes_and_limits_entries() -> None:
    meta = Meta(
        manual_cast=" One , Two ",
        imdb_info={"stars": ["Three", "Four", "Five", "Six"]},
        tmdb_cast=["Seven"],
    )

    meta.populate_cast()

    assert meta.cast == ["One", "Two", "Three", "Four", "Five"]


def test_meta_base_dir_defaults_to_state_dir() -> None:
    from src.app_paths import STATE_DIR

    assert Meta().base_dir == str(STATE_DIR)
    assert Meta(base_dir="").base_dir == str(STATE_DIR)
    assert Meta({"base_dir": ""}).base_dir == str(STATE_DIR)
    assert Meta(base_dir="/custom/dir").base_dir == "/custom/dir"
