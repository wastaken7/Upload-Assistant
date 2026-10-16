"""WebUI prompt timeouts keep their documented numeric semantics when saved."""
import pytest

import web_ui.server as server


@pytest.mark.parametrize("raw,expected", [("0", 0), (0, 0), (0.0, 0), (" 0 ", 0), ("0.5", 0.5), (0.5, 0.5), ("150.5", 150.5), ("1440", 1440)])
def test_webui_prompt_timeout_saves_without_truncating_minutes(raw, expected):
    example = {"DEFAULT": {"webui_unattended_prompt_timeout": 60}}
    source = f"config = {example!r}\n"
    path = ["DEFAULT", "webui_unattended_prompt_timeout"]

    updated_source, result = server._apply_config_update(source, example, {"path": path, "value": raw})

    assert result["value"] == expected
    assert server._parse_config_source(updated_source)["DEFAULT"][path[-1]] == expected


@pytest.mark.parametrize("raw", ["-1", "nan", "inf", "-inf", "invalid", None, "", " \t ", False, True, [], {}])
def test_webui_prompt_timeout_rejects_negative_non_finite_or_invalid_values(raw):
    example = {"DEFAULT": {"webui_unattended_prompt_timeout": 60}}
    source = f"config = {example!r}\n"

    with pytest.raises(ValueError):
        server._apply_config_update(source, example, {"path": ["DEFAULT", "webui_unattended_prompt_timeout"], "value": raw})


def test_webui_prompt_timeout_rejects_an_omitted_value():
    example = {"DEFAULT": {"webui_unattended_prompt_timeout": 60}}
    source = f"config = {example!r}\n"

    with pytest.raises(ValueError):
        server._apply_config_update(source, example, {"path": ["DEFAULT", "webui_unattended_prompt_timeout"]})
