# ruff: noqa: S101

from types import SimpleNamespace

from src.screenshot_manifest import files, register
from src.temp_paths import screenshots_dir


def test_files_preserve_registration_order_across_batches_and_groups(tmp_path, monkeypatch):
    directory = screenshots_dir(tmp_path, "release")
    paths = [directory / name for name in ("first.jpg", "second.png", "extra.webp", "third.jpeg")]
    for path in paths:
        path.write_bytes(b"image")
    ids = iter(["f" * 32, "0" * 32, "8" * 32, "4" * 32])
    monkeypatch.setattr("src.screenshot_manifest.uuid.uuid4", lambda: SimpleNamespace(hex=next(ids)))

    primary = register(tmp_path, "release", paths[:2], "main")
    extra = register(tmp_path, "release", [paths[2]], "FILE_1")
    last = register(tmp_path, "release", [paths[3]], "main")

    assert files(tmp_path, "release", "main") == [*primary, *last]
    assert files(tmp_path, "release", "FILE_1") == extra
    primary[1].unlink()
    assert files(tmp_path, "release") == [primary[0], *extra, *last]
