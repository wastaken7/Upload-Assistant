"""Exercise real executor threads and interpreter exit in isolated processes."""

# ruff: noqa: S101

import subprocess
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryFile
from unittest.mock import Mock

import pytest

CHILD = textwrap.dedent("""\
    import atexit
    import asyncio
    import signal
    import sys
    import threading
    from types import SimpleNamespace

    import upload
    from src.console import prompt_in_thread

    mode, signal_name = sys.argv[1:]
    signum = getattr(signal, signal_name)
    started = threading.Event()
    release = threading.Event()
    atexit.register(lambda: print('ATEXIT', flush=True))
    for level in ('debug', 'info', 'warning', 'error', 'critical'):
        setattr(upload.logger, level, lambda message, *args, **kwargs: print(message % args if args else message, flush=True))
    upload.cleanup_manager.reset_terminal = lambda: print('TERMINAL_RESET', flush=True)

    async def cleanup():
        print('CLEANUP', flush=True)
        if mode == 'cooperative':
            release.set()
        if mode == 'second-signal':
            signal.raise_signal(signum)
        print('CLEANUP_DONE', flush=True)

    upload.cleanup_manager.cleanup = cleanup

    def blocked_prompt():
        started.set()
        return input('PROMPT> ')

    def blocked_worker():
        started.set()
        release.wait()

    async def main():
        upload._reset_shutdown_state()
        if mode in ('normal', 'normal-verbose'):
            if mode == 'normal-verbose':
                print('x' * 1_000_000, flush=True)
            print(await asyncio.to_thread(lambda: 'NORMAL_DONE'), flush=True)
            return
        if mode == 'webui':
            upload._is_webui_mode = True
            upload._webui_server = SimpleNamespace(close=lambda: print('SERVER_CLOSED', flush=True))
            signal.raise_signal(signum)
            return
        task = asyncio.create_task(
            prompt_in_thread(blocked_prompt) if mode == 'prompt'
            else asyncio.to_thread(blocked_worker)
        )
        while not started.is_set():
            await asyncio.sleep(0.001)
        try:
            if mode == 'exception':
                raise RuntimeError('Fictional shutdown failure')
            if mode == 'system-exit':
                raise SystemExit(2)
            if mode == 'keyboard-interrupt':
                raise KeyboardInterrupt
            asyncio.get_running_loop().call_soon(signal.raise_signal, signum)
            await task
        finally:
            # Runner must cancel tasks and let their finalizers use to_thread.
            await asyncio.to_thread(lambda: print('FINALIZER_DONE', flush=True))

    upload.main = main
    upload.run()
""")


def run_child(mode: str, signal_name: str = "SIGINT") -> tuple[int, str]:
    # Keep stdin open while waiting without letting verbose output fill a pipe.
    with TemporaryFile(mode="w+", encoding="utf-8") as log:
        proc = subprocess.Popen(  # noqa: S603 - fixed Python executable and test-only arguments
            [sys.executable, "-u", "-c", CHILD, mode, signal_name],
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        timed_out = False
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            if proc.stdin is not None:
                proc.stdin.close()
        log.seek(0)
        output = log.read()
        if timed_out:
            pytest.fail(f"Shutdown hung with {mode}/{signal_name}:\n{output}")
        return proc.returncode, output


@pytest.mark.parametrize("mode", ["prompt", "worker"])
@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGTERM"])
def test_first_signal_exits_with_blocked_thread_after_cleanup(mode: str, signal_name: str) -> None:
    code, output = run_child(mode, signal_name)

    assert code == 0, output
    assert "FINALIZER_DONE" in output
    assert "CLEANUP_DONE" in output
    assert "TERMINAL_RESET" in output
    assert "Shutdown complete" in output
    assert "ATEXIT" not in output
    assert "RuntimeWarning" not in output
    assert output.index("FINALIZER_DONE") < output.index("CLEANUP_DONE") < output.index("Shutdown complete")


def test_interrupted_cooperative_worker_preserves_interpreter_cleanup() -> None:
    code, output = run_child("cooperative")

    assert code == 0, output
    assert "CLEANUP_DONE" in output
    assert "ATEXIT" in output
    assert "RuntimeWarning" not in output


@pytest.mark.parametrize("mode", ["normal", "normal-verbose"])
def test_normal_run_preserves_interpreter_cleanup(mode: str) -> None:
    code, output = run_child(mode)

    assert code == 0, output
    assert "NORMAL_DONE" in output
    assert "CLEANUP_DONE" in output
    assert "ATEXIT" in output


def test_webui_shutdown_preserves_server_and_interpreter_cleanup() -> None:
    code, output = run_child("webui")

    assert code == 0, output
    assert "SERVER_CLOSED" in output
    assert "Shutdown complete" in output
    assert "CLEANUP_DONE" not in output
    assert "ATEXIT" in output


def test_second_signal_still_forces_immediate_exit() -> None:
    code, output = run_child("second-signal")

    assert code == 1, output
    assert "Forced exit" in output
    assert "CLEANUP_DONE" not in output
    assert "ATEXIT" not in output


@pytest.mark.parametrize("mode", ["exception", "system-exit", "keyboard-interrupt"])
def test_exception_exits_with_blocked_thread_after_cleanup(mode: str) -> None:
    code, output = run_child(mode)

    assert code == 0, output  # Preserve run()'s existing exit status.
    assert "FINALIZER_DONE" in output
    assert "CLEANUP_DONE" in output
    assert "TERMINAL_RESET" in output
    assert "ATEXIT" not in output
    assert "RuntimeWarning" not in output
    if mode == "exception":
        assert "Critical error: Fictional shutdown failure" in output


def test_run_child_kills_process_when_wait_is_interrupted(monkeypatch) -> None:
    proc = Mock()
    proc.wait.side_effect = [KeyboardInterrupt, 0]
    proc.poll.return_value = None
    logs = []

    def start_child(*_args, **kwargs):
        logs.append(kwargs["stdout"])
        return proc

    monkeypatch.setattr(subprocess, "Popen", start_child)

    with pytest.raises(KeyboardInterrupt):
        run_child("prompt")

    proc.kill.assert_called_once_with()
    assert proc.wait.call_count == 2
    proc.stdin.close.assert_called_once_with()
    assert logs[0].closed
