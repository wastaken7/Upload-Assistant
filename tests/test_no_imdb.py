import pytest

from src.args import Args
from src.meta import Meta
from src.prep_helpers import _clear_imdb_metadata


def test_no_imdb_argument_enables_opt_out(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 4}}).parse([str(tmp_path), "--no-imdb"], Meta())

    assert meta.no_imdb is True  # noqa: S101


def test_clear_imdb_metadata_removes_stale_values():
    meta = Meta(imdb_manual="tt1234567", imdb_id=1234567, imdb_info={"title": "Example"}, imdb="1234567", imdb_tt="tt1234567", imdb_rating="8.0")

    _clear_imdb_metadata(meta)

    assert (meta.imdb_manual, meta.imdb_id, meta.imdb_info, meta.imdb, meta.imdb_tt, meta.imdb_rating) == (0, 0, {}, "0", "", "")  # noqa: S101


def test_no_imdb_cannot_be_combined_with_manual_imdb(tmp_path):
    with pytest.raises(SystemExit):
        Args({"DEFAULT": {"screens": 4}}).parse([str(tmp_path), "--no-imdb", "--imdb", "tt1234567"], Meta())
