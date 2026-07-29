# ruff: noqa: S101

import asyncio

from src.clients import Clients
from src.configvalidator import DEFAULT_KEY_TYPES
from src.meta import Meta


def test_empty_inject_delay_is_a_no_op() -> None:
    async def exercise() -> None:
        clients = Clients({"DEFAULT": {"inject_delay": 0}, "TRACKERS": {"TEST": {"inject_delay": ""}}})
        await clients.inject_delay(Meta(), "TEST", "qbit")

    asyncio.run(exercise())


def test_config_validator_declares_image_upload_types() -> None:
    assert DEFAULT_KEY_TYPES["image_upload_concurrency"] == (str, int)
    assert DEFAULT_KEY_TYPES["image_upload_delay"] == (str, float, int)
