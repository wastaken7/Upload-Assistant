# ruff: noqa: S101

from src.takescreens import discard_smallest_capture_result


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
