# ruff: noqa: S101

from PIL import Image

from src.takescreens import discard_smallest_capture_result, dvd_screenshot_has_content


def test_discard_smallest_capture_result_only_removes_current_batch(tmp_path) -> None:
    existing = tmp_path / "disc-0.png"
    captured_large = tmp_path / "disc-1.png"
    captured_small = tmp_path / "disc-2.png"
    existing.write_bytes(b"x")
    captured_large.write_bytes(b"x" * 30)
    captured_small.write_bytes(b"x" * 20)
    capture_results = [str(captured_large), str(captured_small)]

    removed = discard_smallest_capture_result(capture_results)

    assert removed == str(captured_small)
    assert existing.exists()
    assert captured_large.exists()
    assert not captured_small.exists()
    assert capture_results == [str(captured_large)]


def test_dvd_content_check_requires_size_and_visible_pixels(tmp_path) -> None:
    visible = tmp_path / "visible.png"
    blank = tmp_path / "blank.png"
    small_visible = tmp_path / "small-visible.png"
    Image.effect_noise((854, 480), 20).save(visible)
    Image.new("L", (854, 480), 0).save(blank, compress_level=0)
    Image.linear_gradient("L").resize((854, 480)).save(small_visible)

    assert visible.stat().st_size >= 20 * 1024
    assert blank.stat().st_size >= 20 * 1024
    assert small_visible.stat().st_size < 20 * 1024
    assert dvd_screenshot_has_content(visible)
    assert not dvd_screenshot_has_content(blank)
    assert not dvd_screenshot_has_content(small_visible)
