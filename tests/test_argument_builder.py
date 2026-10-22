# ruff: noqa: S101, S603
import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

BUILDER = Path(__file__).resolve().parents[1] / "web_ui" / "static" / "js" / "argument_builder.js"
CASES = [
    "--tmdb movie/123 --debug",
    "--name 'Example Title 2024' --tag \"Group One\"",
    'a\\ b "c \\"d\\" \\e" \'f\\g\'',
    "--descfile 'C:\\Media\\desc.txt'",
    "  --x=1   --y='two words'\t--z \"\"  ",
    "mixed'quo'ted\"parts\"",
]
VALUES = ["plain", "two words", "it's", "", "C:\\dir\\file.txt", 'say "hi"', "$HOME", "a=b,c"]


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser argument tests")
    return node


def _run_builder(script: str) -> object:
    program = f"const vm=require('vm');const fs=require('fs');const c={{window:{{}}}};vm.runInNewContext(fs.readFileSync({json.dumps(str(BUILDER))},'utf8'),c);const b=c.window.UAArgumentBuilder;{script}"
    result = subprocess.run([_node(), "-e", program], check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def test_browser_argument_builder() -> None:
    subprocess.run([_node(), "--test", str(Path(__file__).with_name("webui_argument_builder.test.cjs"))], check=True)


def test_tokenizer_matches_shlex_split() -> None:
    tokens = _run_builder(f"console.log(JSON.stringify({json.dumps(CASES)}.map((t)=>b.tokenize(t).tokens.map((x)=>x.value))))")

    assert tokens == [shlex.split(case) for case in CASES]


def test_quoted_values_round_trip_through_shlex() -> None:
    quoted = _run_builder(f"console.log(JSON.stringify({json.dumps(VALUES)}.map((v)=>b.quoteArgument(v))))")

    assert isinstance(quoted, list)
    assert [shlex.split(item) for item in quoted] == [[value] for value in VALUES]
    assert quoted == [shlex.quote(value) for value in VALUES]
