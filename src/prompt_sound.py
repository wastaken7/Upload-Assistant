"""Deliver confirmation sounds without passing control characters through logging."""

import os
import sys

PROMPT_SOUND_STDOUT_MARKER = "UA_PROMPT_SOUND"


def play_prompt_sound() -> None:
    """Ring the CLI bell, or ask the WebUI client to play its notification sound."""
    # A printable record survives Windows ConPTY and ANSI-to-HTML conversion.
    # Leading/trailing newlines keep it separate from unterminated output.
    output = f"\n{PROMPT_SOUND_STDOUT_MARKER}\n" if os.environ.get("UA_WEBUI_PROMPT_SOUND_STDOUT") == "1" else "\x07"
    sys.stdout.write(output)
    sys.stdout.flush()
