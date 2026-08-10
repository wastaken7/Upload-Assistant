from src.takescreens import round_to_even, screenshot_par_scale_factors, should_scale_screenshots_for_par


def test_screenshot_par_scaling_is_disabled_by_default() -> None:
    assert should_scale_screenshots_for_par({}) is False


def test_screenshot_par_scaling_preserves_coded_dimensions_when_disabled() -> None:
    width_scale, height_scale = screenshot_par_scale_factors(1920.0, 1040.0, 481 / 480, 1.85, apply_par_scaling=False)

    assert (width_scale, height_scale) == (1.0, 1.0)


def test_screenshot_par_scaling_restores_square_pixel_conversion_when_enabled() -> None:
    width_scale, height_scale = screenshot_par_scale_factors(1920.0, 1040.0, 481 / 480, 1.85, apply_par_scaling=True)

    assert width_scale == 481 / 480
    assert height_scale == 1.0
    assert round_to_even(1920.0 * width_scale) == 1924
