# ruff: noqa: S101
import asyncio
import json
import re
import threading
from pathlib import Path
from typing import Any

import pytest

from src import manual_input, webui_events
from src.manual_input import Choice, Question, ask, confirm_override, load_saved_answers, parse_answer
from src.manual_questions import QUESTION_KEYS, game_platform, game_subcategory, parse_answer_arg
from src.meta import Meta

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _meta(tmp_path: Path, **values: Any) -> Meta:
    return Meta(base_dir=str(tmp_path), uuid="fictional-release", name="Fictional Release 2001", unattended=False, **values)


def _question(**values: Any) -> Question:
    defaults: dict[str, Any] = {"key": "xxx.tags", "kind": "list", "prompt": "Enter tags", "tracker": "FICTIONAL"}
    return Question(**{**defaults, **values})


def _answers(monkeypatch: pytest.MonkeyPatch, name: str, answers: list[Any]) -> list[str]:
    queue = iter(answers)
    asked: list[str] = []

    def fake(question: str, *_args: Any, **_kwargs: Any) -> Any:
        asked.append(question)
        return next(queue)

    monkeypatch.setattr(f"src.manual_input.cli_ui.{name}", fake)
    return asked


def test_interactive_answer_is_split_and_remembered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_string", ["first tag, Second Tag; first tag"])
    meta = _meta(tmp_path)

    assert asyncio.run(ask(meta, _question())) == ["first tag", "Second Tag"]
    assert meta.manual_answers["xxx.tags"] == ["first tag", "Second Tag"]


def test_pre_answer_wins_over_saved_answer_and_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answers(monkeypatch, "ask_string", [])
    meta = _meta(tmp_path, answers={"xxx.tags": "from cli"}, manual_answers={"xxx.tags": ["saved"]})

    assert asyncio.run(ask(meta, _question())) == ["from cli"]
    assert asked == []


def test_saved_answer_is_reused_without_asking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answers(monkeypatch, "ask_string", [])
    meta = _meta(tmp_path, manual_answers={"xxx.tags": ["saved"]})

    assert asyncio.run(ask(meta, _question())) == ["saved"]
    assert asked == []


def test_saved_answer_that_no_longer_fits_is_asked_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_choice", ["Beta"])
    question = _question(key="exoticaz.category", kind="choice", choices=(Choice("alpha", "Alpha"), Choice("beta", "Beta")))
    meta = _meta(tmp_path, manual_answers={"exoticaz.category": "gamma"})

    assert asyncio.run(ask(meta, question)) == "beta"
    assert meta.manual_answers["exoticaz.category"] == "beta"


def test_invalid_pre_answer_falls_back_to_the_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_string", ["2001"])
    question = _question(key="bjshare.year", kind="text", validate=lambda year: None if year.isdigit() else "Not a year")
    meta = _meta(tmp_path, answers={"bjshare.year": "soon"})

    assert asyncio.run(ask(meta, question)) == "2001"


def test_validation_repeats_the_question_until_it_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answers(monkeypatch, "ask_string", ["unknown", "known"])

    async def known(words: list[str]) -> str | None:
        await asyncio.sleep(0)
        return None if words == ["known"] else "Unknown tag"

    assert asyncio.run(ask(_meta(tmp_path), _question(validate=known))) == ["known"]
    assert len(asked) == 2


def test_empty_answer_without_default_is_no_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_string", [""])
    meta = _meta(tmp_path)

    assert asyncio.run(ask(meta, _question())) is None
    assert "xxx.tags" not in meta.manual_answers


def test_empty_answer_can_be_a_valid_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "select_choices", [None])
    question = _question(key="exoticaz.flags", kind="multi_choice", choices=(Choice("asian", "Asian"),), empty_ok=True)

    assert asyncio.run(ask(_meta(tmp_path), question)) == []


def test_empty_answer_uses_the_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_string", [""])

    assert asyncio.run(ask(_meta(tmp_path), _question(key="bjshare.synopsis", kind="text", default="N/A"))) == "N/A"


def test_choice_maps_the_label_back_to_its_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_choice", ["Full Game + DLC"])
    meta = _meta(tmp_path, category="GAME")

    assert asyncio.run(game_subcategory(meta, tracker="FICTIONAL")) == "full_game_dlc"
    assert meta.game_subcategory == "full_game_dlc"


def test_known_platform_is_not_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answers(monkeypatch, "ask_choice", [])
    meta = _meta(tmp_path, platform="ps4")

    assert asyncio.run(game_platform(meta, tracker="FICTIONAL", supported=["PC", "PS4"], default="PC")) == "PS4"
    assert asked == []


@pytest.mark.parametrize(
    ("question", "skipping"),
    [
        (_question(), "FICTIONAL"),
        (_question(unattended="fail"), None),
    ],
)
def test_unattended_without_default_does_not_ask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, question: Question, skipping: str | None) -> None:
    asked = _answers(monkeypatch, "ask_string", [])
    meta = _meta(tmp_path)
    meta.unattended = True

    assert asyncio.run(ask(meta, question)) is None
    assert meta.skipping == skipping
    assert asked == []


def test_unattended_default_is_used_but_not_remembered(tmp_path: Path) -> None:
    meta = _meta(tmp_path, platform="")
    meta.unattended = True

    assert asyncio.run(game_platform(meta, tracker="FICTIONAL", supported=["PC", "PS4"], default="PC")) == "PC"
    assert meta.platform == "PC"
    assert meta.manual_answers == {}


def test_unattended_confirm_still_asks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, "ask_string", ["asked"])
    meta = _meta(tmp_path, unattended_confirm=True)
    meta.unattended = True

    assert asyncio.run(ask(meta, _question())) == ["asked"]


def test_confirm_override_never_continues_unattended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answers(monkeypatch, "ask_yes_no", [True])
    meta = _meta(tmp_path)
    meta.unattended = True

    assert asyncio.run(confirm_override(meta)) is False
    meta.unattended = False
    assert asyncio.run(confirm_override(meta)) is True
    assert asked == ["Do you want to upload anyway?"]


def test_prompts_are_announced_to_the_gui_as_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contexts: list[dict[str, Any] | None] = []

    def fake(*_args: Any, **_kwargs: Any) -> str:
        contexts.append(webui_events._context_payload())
        return "tag"

    monkeypatch.setattr("src.manual_input.cli_ui.ask_string", fake)
    asyncio.run(ask(_meta(tmp_path), _question(title="Tags", hint="Comma-separated", summary={"Release": "Fictional"})))

    assert contexts[0] is not None
    assert contexts[0]["kind"] == "field"
    assert contexts[0]["title"] == "Tags"
    assert contexts[0]["hint"] == "Comma-separated"


def test_concurrent_questions_are_asked_one_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    overlap = False
    lock = threading.Lock()

    def fake(*_args: Any, **_kwargs: Any) -> str:
        nonlocal active, overlap
        with lock:
            active += 1
            overlap = overlap or active > 1
        threading.Event().wait(0.05)
        with lock:
            active -= 1
        return "tag"

    monkeypatch.setattr("src.manual_input.cli_ui.ask_string", fake)

    async def run() -> None:
        await asyncio.gather(*(ask(_meta(tmp_path), _question(tracker=f"FICTIONAL{index}")) for index in range(3)))

    asyncio.run(run())
    assert overlap is False


def test_saved_answers_are_reloaded_from_meta_json(tmp_path: Path) -> None:
    meta_dir = tmp_path / "tmp" / "fictional-release"
    meta_dir.mkdir(parents=True)
    (meta_dir / "meta.json").write_text(json.dumps({"manual_answers": {"xxx.tags": ["saved"], "game.platform": "PC"}}), encoding="utf-8")
    meta = _meta(tmp_path, manual_answers={"game.platform": "PS4"})

    asyncio.run(load_saved_answers(meta))

    assert meta.manual_answers == {"game.platform": "PS4", "xxx.tags": ["saved"]}


def test_unreadable_meta_json_is_ignored(tmp_path: Path) -> None:
    meta_dir = tmp_path / "tmp" / "fictional-release"
    meta_dir.mkdir(parents=True)
    (meta_dir / "meta.json").write_text("{not json", encoding="utf-8")
    meta = _meta(tmp_path)

    asyncio.run(load_saved_answers(meta))

    assert meta.manual_answers == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("yes", True), ("Não", False), ("2", "beta"), ("ALPHA", "alpha"), ("Beta", "beta")],
)
def test_parse_answer_accepts_numbers_values_and_labels(raw: str, expected: Any) -> None:
    kind = "confirm" if isinstance(expected, bool) else "choice"
    question = _question(kind=kind, choices=(Choice("alpha", "Alpha"), Choice("beta", "Beta")))

    assert parse_answer(question, raw) == (expected, None)


def test_answer_argument_rejects_unknown_keys_and_values() -> None:
    assert parse_answer_arg(" Game.Subcategory = dlc ") == ("game.subcategory", "dlc")
    with pytest.raises(ValueError, match="unknown key"):
        parse_answer_arg("fictional.key=1")
    with pytest.raises(ValueError, match="not one of"):
        parse_answer_arg("game.subcategory=expansion")
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_answer_arg("game.subcategory")


def test_every_question_key_is_listed_in_the_catalog() -> None:
    used: set[str] = set()
    for path in SRC_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        used.update(re.findall(r'key="([a-z_]+\.[a-z_]+)"', text))
    # BJShare builds these from its credit roles: key=f"credits.{role}".
    used.update({"credits.director", "credits.creator", "credits.cast"})

    assert used
    assert sorted(used - set(QUESTION_KEYS)) == []


def test_prompt_lock_is_reentrant_for_the_holder() -> None:
    async def run() -> bool:
        async with manual_input.prompt_session(), manual_input.prompt_session():
            return True

    assert asyncio.run(run()) is True


def test_confirm_override_treats_closed_stdin_as_no(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def closed(*_args: Any, **_kwargs: Any) -> bool:
        raise EOFError

    monkeypatch.setattr("src.manual_input.cli_ui.ask_yes_no", closed)

    assert asyncio.run(confirm_override(_meta(tmp_path))) is False


def test_invalid_answer_argument_is_a_parser_error(tmp_path: Path) -> None:
    from src.args import Args

    with pytest.raises(SystemExit):
        Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--answer", "fictional.key=1"], Meta())
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--answer", "game.subcategory=dlc"], Meta())
    assert meta.answers == {"game.subcategory": "dlc"}
