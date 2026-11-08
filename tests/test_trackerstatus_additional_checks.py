from types import SimpleNamespace

import pytest

from src import trackerstatus
from src.meta import Meta


class _Helper:
    prompted = False
    answer = True

    async def prompt_yes_no(self, _message: str, default: bool = False) -> bool:
        del default
        self.prompted = True
        return self.answer


@pytest.mark.asyncio
async def test_failed_additional_check_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False, isatty=lambda: False))

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(), helper)

    assert result is True  # noqa: S101
    assert helper.prompted is True  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_is_not_overridden_when_stdin_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=True))

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(), helper)

    assert result is False  # noqa: S101
    assert helper.prompted is False  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_is_not_overridden_when_prompt_reaches_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)

    async def prompt_yes_no(_message: str, default: bool = False) -> bool:
        del default
        helper.prompted = True
        raise EOFError

    monkeypatch.setattr(helper, "prompt_yes_no", prompt_yes_no)

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(), helper)

    assert result is False  # noqa: S101
    assert helper.prompted is True  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_is_skipped_in_unattended_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(unattended=True), helper)

    assert result is False  # noqa: S101
    assert helper.prompted is False  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_can_be_overridden_with_unattended_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False))

    async def check(_meta: Meta) -> bool:
        return False

    meta = Meta(unattended=True, unattended_confirm=True)
    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), meta, helper)

    assert result is True  # noqa: S101
    assert helper.prompted is True  # noqa: S101


@pytest.mark.asyncio
async def test_rule_warning_is_asked_about_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.trackers.UNIT3D.seedpool import Seedpool

    questions: list[str] = []

    class Helper:
        async def prompt_yes_no(self, message: str, default: bool = False) -> bool:
            del default
            questions.append(message)
            return True

    def ask_yes_no(question: str, *_args: object, **_kwargs: object) -> bool:
        questions.append(question)
        return True

    monkeypatch.setattr("src.manual_input.cli_ui.ask_yes_no", ask_yes_no)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False))
    tracker = Seedpool({"DEFAULT": {}, "TRACKERS": {"SEEDPOOL": {}}})
    meta = Meta(category="MOVIE", resolution="720p", name="Fictional Film 2001 720p WEB-DL-NOGRP")

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("SEEDPOOL", tracker, meta, Helper())

    assert result is True  # noqa: S101
    assert questions == ["SEEDPOOL: one or more upload checks failed. Do you want to proceed with the upload anyway?"]  # noqa: S101


def test_tracker_checks_leave_the_override_question_to_tracker_status() -> None:
    """Tracker rules only report failures; asking to upload anyway happens once, in TrackerStatusManager."""
    import ast
    from pathlib import Path

    override_calls = {"confirm_override", "prompt_user_for_confirmation", "ask_yes_no", "prompt_yes_no"}
    offenders: list[str] = []
    for path in Path("src/trackers").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        pending, seen = ["get_additional_checks"], set()
        while pending:
            name = pending.pop()
            if name in seen or name not in functions:
                continue
            seen.add(name)
            for node in ast.walk(functions[name]):
                if not isinstance(node, ast.Call):
                    continue
                called = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                if called in override_calls:
                    offenders.append(f"{path}:{node.lineno} {called}")
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    pending.append(node.func.attr)

    assert offenders == []  # noqa: S101
