# ruff: noqa: S101

import asyncio
from unittest.mock import patch

from src.clients import Clients
from src.configvalidator import DEFAULT_KEY_TYPES, validate_config
from src.meta import Meta


def test_empty_inject_delay_is_a_no_op() -> None:
    sleep_calls = 0

    async def fake_sleep(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1

    async def exercise() -> None:
        clients = Clients({"DEFAULT": {"inject_delay": 3}, "TRACKERS": {"TEST": {"inject_delay": ""}}})
        await clients.inject_delay(Meta(), "TEST", "qbit")

    with patch("src.clients.asyncio.sleep", new=fake_sleep):
        asyncio.run(exercise())

    assert sleep_calls == 0


def test_config_validator_declares_image_upload_types() -> None:
    assert DEFAULT_KEY_TYPES["image_upload_concurrency"] == (str, int)
    assert DEFAULT_KEY_TYPES["image_upload_delay"] == (str, float, int)


def test_config_validator_warns_for_invalid_image_upload_limits() -> None:
    is_valid, errors, warnings = validate_config(
        {
            "DEFAULT": {
                "tmdb_api": "test-key",
                "image_upload_concurrency": "not-an-int",
                "image_upload_delay": "-0.5",
            },
            "TRACKERS": {},
        }
    )

    warning_keys = {warning.key for warning in warnings}
    assert is_valid
    assert not errors
    assert {"image_upload_concurrency", "image_upload_delay"} <= warning_keys


def test_config_validator_warns_for_nonfinite_image_upload_delay() -> None:
    _, _, warnings = validate_config(
        {
            "DEFAULT": {"tmdb_api": "test-key", "image_upload_delay": float("nan")},
            "TRACKERS": {},
        }
    )

    assert any(warning.key == "image_upload_delay" for warning in warnings)


def test_config_validator_warns_for_infinite_image_upload_concurrency() -> None:
    _, _, warnings = validate_config(
        {
            "DEFAULT": {"tmdb_api": "test-key", "image_upload_concurrency": float("inf")},
            "TRACKERS": {},
        }
    )

    assert any(warning.key == "image_upload_concurrency" and "Cannot parse" in warning.message for warning in warnings)
