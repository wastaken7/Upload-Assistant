# ruff: noqa: S101

from src.args import Args
from src.meta import Meta


def test_archive_password_cli_override_preserves_random_mode(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--archive-password", "random"], Meta())

    assert meta.archive_password == "random"
    assert meta.usenet_archive_password_is_random is True


def test_archive_password_cli_override_marks_static_password(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--archive-password", "per-run-password"], Meta())

    assert meta.archive_password == "per-run-password"
    assert meta.usenet_archive_password_is_random is False
