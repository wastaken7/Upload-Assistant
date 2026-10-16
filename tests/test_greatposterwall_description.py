import pytest

from src.get_desc import gen_desc
from src.meta import Meta
from src.trackers.GAZELLE.greatposterwall import GreatPosterWall


@pytest.mark.asyncio
@pytest.mark.parametrize("release_notes", ["", "Release notes"])
async def test_scene_nfo_is_rendered_once(tmp_path, release_notes):
    temp_dir = tmp_path / "tmp" / "release"
    temp_dir.mkdir(parents=True)
    nfo_content = "Sample.Movie.2026.1080p.WEB.x264-GROUP\nSource: Sample Service\n"
    (temp_dir / "release.nfo").write_text(nfo_content, encoding="utf-8")
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        category="MOVIE",
        scene=True,
        auto_nfo=True,
        nfo=True,
        language_checked=True,
    )
    await gen_desc(meta, None, None)
    if release_notes:
        meta.description += f"\n{release_notes}"
    base_description = meta.description
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {}}})

    description = await tracker.get_release_desc(meta)

    assert description.count(nfo_content) == 1
    assert f"[pre]{nfo_content}[/pre]" in description
    assert "Scene NFO:" not in description
    assert release_notes in description
    assert meta.description == base_description
    assert meta.description_nfo_content == nfo_content
    assert await tracker.get_release_desc(meta) == description
