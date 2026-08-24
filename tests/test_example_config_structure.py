import ast
from pathlib import Path
from typing import Any, cast


EXAMPLE_CONFIG_PATH = Path(__file__).parents[1] / "data" / "example_config.py"


def load_example_config() -> dict[str, Any]:
    tree = ast.parse(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), filename=str(EXAMPLE_CONFIG_PATH))

    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            config = ast.literal_eval(node.value)
            assert isinstance(config, dict)
            return cast(dict[str, Any], config)

    raise AssertionError("data/example_config.py must define config as a literal dictionary")


def load_available_tracker_names() -> list[str]:
    lines = EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    marker_index = lines.index("        # Available trackers:")
    listed_names: list[str] = []

    for line in lines[marker_index + 1 :]:
        if not line.startswith("        #   "):
            break
        listed_names.extend(name.strip() for name in line.removeprefix("        #   ").split(",") if name.strip())

    return listed_names


def test_example_config_tracker_templates_are_alphabetical() -> None:
    trackers = load_example_config()["TRACKERS"]
    tracker_names = [name for name, settings in trackers.items() if isinstance(settings, dict) and name != "MANUAL"]

    assert tracker_names == sorted(tracker_names)
    assert load_available_tracker_names() == tracker_names
    assert list(trackers)[-1] == "MANUAL"
