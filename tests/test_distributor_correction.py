# ruff: noqa: S101
from unittest.mock import AsyncMock, Mock

import pytest

from src.get_name import NameManager
from src.meta import Meta


@pytest.mark.asyncio
async def test_unsupported_supplied_distributor_is_preserved_and_required_tracker_skipped(monkeypatch):
    manager = NameManager({})
    manager._prompt_for_field = AsyncMock()
    warning = Mock()
    monkeypatch.setattr("src.get_name.logger.warning", warning)
    meta = Meta(is_disc="BDMV", region="USA", distributor="UNLISTED STUDIO", unattended=True)
    region, distributor, removed = await manager.missing_disc_info(meta, ["ULCX", "OLDTOONSWORLD"])
    assert (region, distributor, removed) == ("USA", "UNLISTED STUDIO", ["ULCX"])
    manager._prompt_for_field.assert_not_awaited()
    assert any("Skipping upload to ULCX" in call.args[0] and "UNLISTED STUDIO" in call.args[0] for call in warning.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("unattended, confirm", [(False, False), (True, True)])
async def test_unsupported_distributor_can_be_corrected_interactively(unattended, confirm):
    manager = NameManager({})
    manager._prompt_for_field = AsyncMock(side_effect=["ANOTHER UNLISTED STUDIO", "SUPPORTED STUDIO"])
    manager.common.unit3d_distributor_ids = AsyncMock(side_effect=lambda name, tracker: "970" if name == "SUPPORTED STUDIO" and tracker == "ULCX" else "")
    meta = Meta(is_disc="BDMV", region="USA", distributor="UNLISTED STUDIO", unattended=unattended, unattended_confirm=confirm)

    region, distributor, removed = await manager.missing_disc_info(meta, ["ULCX", "OLDTOONSWORLD"])

    assert (region, distributor, removed) == ("USA", "SUPPORTED STUDIO", [])
    assert manager._prompt_for_field.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["SKIPPED", ""])
async def test_skipping_distributor_correction_preserves_value_and_warns(monkeypatch, replacement):
    manager = NameManager({})
    manager._prompt_for_field = AsyncMock(return_value=replacement)
    warning = Mock()
    monkeypatch.setattr("src.get_name.logger.warning", warning)
    meta = Meta(is_disc="BDMV", region="USA", distributor="UNLISTED STUDIO")

    region, distributor, removed = await manager.missing_disc_info(meta, ["ULCX", "OLDTOONSWORLD"])

    assert (region, distributor, removed) == ("USA", "UNLISTED STUDIO", ["ULCX"])
    manager._prompt_for_field.assert_awaited_once()
    assert any("Skipping upload to ULCX" in call.args[0] for call in warning.call_args_list)


@pytest.mark.asyncio
async def test_optional_distributor_does_not_prompt_for_unknown_name():
    manager = NameManager({})
    manager._prompt_for_field = AsyncMock()
    meta = Meta(is_disc="BDMV", region="USA", distributor="UNLISTED STUDIO")

    assert await manager.missing_disc_info(meta, ["OLDTOONSWORLD", "SHAREISLAND"]) == ("USA", "UNLISTED STUDIO", [])
    manager._prompt_for_field.assert_not_awaited()
