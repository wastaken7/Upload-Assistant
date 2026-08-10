import pytest

from src.takescreens import LOSTIMG_MAX_SIZE, LOSTIMG_MIN_SIZE, is_valid_lostimg_image_size


@pytest.mark.parametrize(
    ("image_size", "valid"),
    [
        (LOSTIMG_MIN_SIZE, False),
        (LOSTIMG_MIN_SIZE + 1, True),
        (LOSTIMG_MAX_SIZE, True),
        (LOSTIMG_MAX_SIZE + 1, False),
    ],
)
def test_lostimg_size_boundaries(image_size: int, valid: bool) -> None:
    assert is_valid_lostimg_image_size(image_size) is valid
