# ruff: noqa: S101
import asyncio
import threading

import pytest

from src.dupe_checking import DupeChecker
from src.meta import Meta
from src.uphelper import DupeEntry, UploadHelper


@pytest.mark.asyncio
async def test_prompt_yes_no_serializes_concurrent_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def ask_yes_no(question: str, default: bool = False) -> bool:
        if question == "first":
            first_started.set()
            assert release_first.wait(timeout=1)
        else:
            second_started.set()
        return default

    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", ask_yes_no)
    helper = UploadHelper({"DEFAULT": {}})

    first = asyncio.create_task(helper.prompt_yes_no("first"))
    second = asyncio.create_task(helper.prompt_yes_no("second", default=True))

    assert await asyncio.to_thread(first_started.wait, 1)
    await asyncio.sleep(0)
    assert not second_started.is_set()

    release_first.set()
    assert await asyncio.gather(first, second) == [False, True]
    assert second_started.is_set()


@pytest.mark.asyncio
async def test_dupe_check_keeps_each_result_list_with_its_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    first_started = threading.Event()
    release_first = threading.Event()
    messages: list[str] = []
    prompts: list[str] = []

    class Tracker:
        async def get_name(self, meta: Meta) -> dict[str, str]:
            return {"name": meta.name}

    def ask_yes_no(question: str, default: bool = False) -> bool:
        del default
        prompts.append(question)
        if len(prompts) == 1:
            first_started.set()
            assert release_first.wait(timeout=1)
        return True

    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {"FIRST": lambda **_kwargs: Tracker(), "SECOND": lambda **_kwargs: Tracker()}
    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", ask_yes_no)
    monkeypatch.setattr("src.uphelper.logger.info", lambda message, **_kwargs: messages.append(message))

    first = asyncio.create_task(helper.dupe_check(["first dupe"], Meta(category="TV", name="First"), "FIRST"))
    assert await asyncio.to_thread(first_started.wait, 1)

    second = asyncio.create_task(helper.dupe_check(["second dupe"], Meta(category="TV", name="Second"), "SECOND"))
    await asyncio.sleep(0)
    assert messages == ["[bold blue]FIRST[/bold blue]: Check if these are actually dupes:", "", "[bold cyan]first dupe[/bold cyan]"]

    release_first.set()
    await asyncio.gather(first, second)

    assert prompts == ["Upload to FIRST anyway?", "Upload to SECOND anyway?"]
    assert messages[-3:] == ["[bold blue]SECOND[/bold blue]: Check if these are actually dupes:", "", "[bold cyan]second dupe[/bold cyan]"]


@pytest.mark.asyncio
async def test_bdinfo_comparison_prompt_uses_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    question: str | None = None

    async def prompt_yes_no(value: str, *, default: bool = False) -> bool:
        nonlocal question
        question = value
        return False

    monkeypatch.setattr("src.uphelper.has_bdinfo_content", lambda _entry: True)
    helper = UploadHelper({"DEFAULT": {}})
    monkeypatch.setattr(helper, "prompt_yes_no", prompt_yes_no)

    await helper.ask_bdinfo_comparison({}, [{}], "AITHER")

    assert question == "Found BDInfo content in potential duplicates. Perform a comparison?"
    assert "\033" not in question


@pytest.mark.asyncio
async def test_dupe_check_rejects_episode_when_tracker_prefers_existing_season_pack() -> None:
    class SeasonPackTracker:
        reject_episode_if_season_pack_exists = True

        async def get_name(self, meta: Meta) -> dict[str, str]:
            return {"name": meta.name}

    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {"DARKPEERS": lambda config: SeasonPackTracker()}
    meta = Meta(category="TV", name="Yowayowa Sensei S01E01", season_pack_exists=True, season_pack_name="Yowayowa Sensei S01 1080p WEB-DL")
    dupes: list[DupeEntry | str] = [meta.season_pack_name]

    is_dupe, result_meta = await helper.dupe_check(dupes, meta, "DARKPEERS")

    assert is_dupe is True
    assert result_meta is meta


@pytest.mark.asyncio
async def test_dupe_check_honors_skip_dupe_check_for_existing_season_pack() -> None:
    class SeasonPackTracker:
        reject_episode_if_season_pack_exists = True

        async def get_name(self, meta: Meta) -> dict[str, str]:
            return {"name": meta.name}

    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {"DARKPEERS": lambda **_kwargs: SeasonPackTracker()}
    meta = Meta(category="TV", name="Yowayowa Sensei S01E01", dupe=True, season_pack_exists=True, season_pack_name="Yowayowa Sensei S01 1080p WEB-DL")

    is_dupe, result_meta = await helper.dupe_check([meta.season_pack_name], meta, "DARKPEERS")

    assert is_dupe is False
    assert result_meta is meta


@pytest.mark.asyncio
async def test_dupe_check_keeps_existing_prompt_policy_for_other_trackers(monkeypatch: pytest.MonkeyPatch) -> None:
    class SeasonPackTracker:
        reject_episode_if_season_pack_exists = False

        async def get_name(self, meta: Meta) -> dict[str, str]:
            return {"name": meta.name}

    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {"OTHER": lambda config: SeasonPackTracker()}
    monkeypatch.setattr(helper, "prompt_yes_no", lambda question, default=False: asyncio.sleep(0, result=True))
    meta = Meta(category="TV", name="Show S01E01", season_pack_exists=True, season_pack_name="Show S01")

    dupes: list[DupeEntry | str] = [meta.season_pack_name]
    is_dupe, _ = await helper.dupe_check(dupes, meta, "OTHER")

    assert is_dupe is False


@pytest.mark.asyncio
async def test_dupe_filter_resets_season_pack_state_between_trackers() -> None:
    meta = Meta(
        category="TV",
        season_pack_exists=True,
        season_pack_id=123,
        season_pack_link="https://example.com/123",
        season_pack_name="Previous Tracker Pack",
    )

    await DupeChecker({"DEFAULT": {}}).filter_dupes([], meta, "OTHER")

    assert meta.season_pack_exists is False
    assert meta.season_pack_id is None
    assert meta.season_pack_link is None
    assert meta.season_pack_name == ""
