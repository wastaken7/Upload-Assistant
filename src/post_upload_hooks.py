"""Run user-managed post-upload hook scripts without coupling them to the core."""

import asyncio
import copy
import importlib.util
import inspect
import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.app_paths import STATE_DIR
from src.cogs.redaction import PathAwareEncoder
from src.console import logger
from src.meta import Meta

HOOKS_DIR = STATE_DIR / "custom_hooks"
DEFAULT_TIMEOUT_SECONDS = 30.0


def _configured_hook_names(config: Mapping[str, Any], setting: str) -> list[str]:
    configured = config.get("DEFAULT", {}).get(setting, [])
    if not isinstance(configured, Sequence) or isinstance(configured, str):
        logger.warning(f"{setting} must be a list of script names; ignoring it.")
        return []
    return [name for name in configured if isinstance(name, str) and name.strip()]


def _hook_path(name: str) -> Path | None:
    root = HOOKS_DIR.resolve()
    path = (root / name).resolve()
    if path.suffix != ".py" or not path.is_relative_to(root):
        logger.warning(f"Ignoring invalid post-upload hook: {name!r}")
        return None
    return path


def _timeout_seconds(config: Mapping[str, Any]) -> float:
    value = config.get("DEFAULT", {}).get("post_upload_hook_timeout", DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(value)
    except TypeError, ValueError:
        logger.warning(f"Invalid post_upload_hook_timeout {value!r}; using {DEFAULT_TIMEOUT_SECONDS:g} seconds.")
        return DEFAULT_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_TIMEOUT_SECONDS


async def _relay(stream: asyncio.StreamReader | None, hook_name: str, error: bool = False) -> None:
    if stream is None:
        return
    log = logger.error if error else logger.info
    async for raw_line in stream:
        line = raw_line.decode(errors="replace").rstrip()
        if line:
            log(f"[hook: {hook_name}] {line}", extra={"markup": False})


def _hook_process_group_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def _terminate_hook_process_tree(process: asyncio.subprocess.Process) -> None:
    """Terminate the hook and every process that can retain its output pipes."""
    if process.returncode is not None:
        return
    try:
        if os.name == "nt":
            taskkill = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await taskkill.wait()
        elif process.pid is not None:
            os.killpg(process.pid, signal.SIGTERM)
    except OSError, ProcessLookupError:
        pass

    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except TimeoutError:
        try:
            if os.name == "nt":
                process.kill()
            elif process.pid is not None:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError, ProcessLookupError:
            pass
        await process.wait()


async def _run_inprocess_hook(path: Path, meta: Meta, config: Mapping[str, Any]) -> None:
    module_name = f"_ua_post_upload_hook_{path.stem}_{abs(hash(path))}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError("could not create a module specification")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        callback = getattr(module, "on_upload_finished", None)
        if not callable(callback):
            logger.error(f"[hook: {path.stem}] Missing callable on_upload_finished(meta, config).", extra={"markup": False})
            return
        result = callback(meta.copy(), copy.deepcopy(config))
        if inspect.isawaitable(result):
            await result
        logger.info(f"[hook: {path.stem}] Finished.", extra={"markup": False})
    except Exception as exc:
        logger.exception(f"[hook: {path.stem}] Failed: {exc}", extra={"markup": False})


async def _run_inprocess_hooks(meta: Meta, config: Mapping[str, Any], names: list[str]) -> None:
    for name in names:
        path = _hook_path(name.strip())
        if path is None:
            continue
        if not path.is_file():
            logger.warning(f"Configured in-process post-upload hook was not found: {path}")
            continue
        logger.info(f"[hook: {path.stem}] Starting in-process.", extra={"markup": False})
        await _run_inprocess_hook(path, meta, config)


async def run_post_upload_hooks(meta: Meta, config: Mapping[str, Any]) -> None:
    """Send the final metadata snapshot to each configured user hook.

    Subprocess hooks receive JSON; in-process hooks receive an isolated
    ``meta.copy()`` and a deep copy of the active configuration. Hook failures
    never fail an upload.
    """
    names = _configured_hook_names(config, "post_upload_hooks")
    inprocess_names = _configured_hook_names(config, "post_upload_inprocess_hooks")
    if not names and not inprocess_names:
        return

    HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    if names:
        payload = json.dumps(
            {"schema_version": 1, "event": "upload.finished", "meta": meta.to_dict()},
            cls=PathAwareEncoder,
        ).encode("utf-8")
        timeout = _timeout_seconds(config)

        for name in names:
            path = _hook_path(name.strip())
            if path is None:
                continue
            if not path.is_file():
                logger.warning(f"Configured post-upload hook was not found: {path}")
                continue

            logger.info(f"[hook: {path.stem}] Starting.", extra={"markup": False})
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(path),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=HOOKS_DIR,
                    **_hook_process_group_kwargs(),
                )
                if process.stdin is not None:
                    process.stdin.write(payload)
                    await process.stdin.drain()
                    process.stdin.close()

                stdout_task = asyncio.create_task(_relay(process.stdout, path.stem))
                stderr_task = asyncio.create_task(_relay(process.stderr, path.stem, error=True))
                try:
                    returncode = await asyncio.wait_for(process.wait(), timeout=timeout)
                except TimeoutError:
                    await _terminate_hook_process_tree(process)
                    logger.error(f"[hook: {path.stem}] Timed out after {timeout:g} seconds.", extra={"markup": False})
                    continue
                finally:
                    await asyncio.gather(stdout_task, stderr_task)

                if returncode != 0:
                    logger.error(f"[hook: {path.stem}] Exited with code {returncode}.", extra={"markup": False})
                else:
                    logger.info(f"[hook: {path.stem}] Finished.", extra={"markup": False})
            except (OSError, BrokenPipeError) as exc:
                logger.error(f"[hook: {path.stem}] Could not run: {exc}", extra={"markup": False})

    await _run_inprocess_hooks(meta, config, inprocess_names)
