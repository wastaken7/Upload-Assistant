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


def test_dvd_content_check_uses_pixels_instead_of_png_file_size(tmp_path) -> None:
    visible = tmp_path / "visible.png"
    blank = tmp_path / "blank.png"
    Image.linear_gradient("L").resize((854, 480)).save(visible)
    Image.new("L", (854, 480), 0).save(blank)

    assert visible.stat().st_size < 75_000
    assert dvd_screenshot_has_content(visible)
    assert not dvd_screenshot_has_content(blank)
