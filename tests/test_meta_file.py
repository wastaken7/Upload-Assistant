# ruff: noqa: S101

import asyncio
import json
from unittest.mock import Mock

import pytest

from src.meta import Meta
from src.meta_file import write_meta_file
from src.prep import Prep


def _meta(tmp_path):
    directory = tmp_path / "tmp" / "Fictional.Release"
    directory.mkdir(parents=True)
    return Meta(base_dir=str(tmp_path), uuid=directory.name, path="Fictional.Release"), directory / "meta.json"


def test_initial_snapshot_preserves_existing_meta(tmp_path):
    meta, meta_file = _meta(tmp_path)
    previous = '{"title": "Previous fictional release"}'
    meta_file.write_text(previous, encoding="utf-8")
    prep = Prep.__new__(Prep)
    prep.publish_preview = Mock()

    asyncio.run(prep._publish_initial_webui_snapshot(meta))

    assert meta_file.read_text(encoding="utf-8") == previous
    prep.publish_preview.assert_not_called()


def test_processed_meta_replaces_existing_file(tmp_path):
    meta, meta_file = _meta(tmp_path)
    meta_file.write_text('{"title": "Previous fictional release"}', encoding="utf-8")
    meta.title = "New fictional release"

    asyncio.run(write_meta_file(meta))

    assert json.loads(meta_file.read_text(encoding="utf-8"))["title"] == "New fictional release"
    assert list(meta_file.parent.glob(".meta-*.json")) == []


def test_failed_replace_preserves_existing_meta(tmp_path, monkeypatch):
    meta, meta_file = _meta(tmp_path)
    previous = '{"title": "Previous fictional release"}'
    meta_file.write_text(previous, encoding="utf-8")

    def fail_replace(_source, _destination):
        assert meta_file.read_text(encoding="utf-8") == previous
        raise OSError("replacement failed")

    monkeypatch.setattr("src.meta_file.Path.replace", fail_replace)

    with pytest.raises(OSError, match="replacement failed"):
        asyncio.run(write_meta_file(meta))

    assert meta_file.read_text(encoding="utf-8") == previous
    assert list(meta_file.parent.glob(".meta-*.json")) == []
