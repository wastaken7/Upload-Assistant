# ruff: noqa: S101

import asyncio

from src.args import Args
from src.get_desc import gen_desc
from src.meta import Meta


def test_description_argument_preserves_inline_bbcode(tmp_path) -> None:
    description = "[alert]Missing S01E10[/alert]"

    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(
        [str(tmp_path), "--description", description],
        Meta(),
    )

    assert meta.description_inline == description


def test_inline_description_replaces_imported_text_but_keeps_auto_nfo_available(tmp_path) -> None:
    async def run() -> None:
        temp_dir = tmp_path / "tmp" / "release"
        temp_dir.mkdir(parents=True)
        (temp_dir / "release.nfo").write_text("NFO contents", encoding="utf-8")
        meta = Meta(
            base_dir=str(tmp_path),
            uuid="release",
            path=str(tmp_path / "release.mkv"),
            description="imported tracker description",
            description_inline="[alert]Missing S01E10[/alert]",
            nfo=True,
            auto_nfo=True,
        )

        await gen_desc(meta, None, None)

        assert meta.description == "[alert]Missing S01E10[/alert]"
        assert "Scene NFO" not in meta.description
        assert meta.description_nfo_content == "NFO contents"

    asyncio.run(run())
