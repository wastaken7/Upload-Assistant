# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import math
import os
import random
import re
import secrets
import shutil
from typing import Any, Optional

import aiofiles
import aiofiles.os
import aiofiles.ospath
import cli_ui

from src.console import console
from src.meta import Meta


def generate_random_poster() -> str:
    """Generate a fully random poster name and email for Usenet anonymity."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"

    first_len = random.randint(5, 10)
    last_len = random.randint(5, 10)
    user_len = random.randint(6, 12)
    domain_len = random.randint(5, 10)

    first = "".join(random.choice(letters) for _ in range(first_len))
    last = "".join(random.choice(letters) for _ in range(last_len))
    email_user = "".join(random.choice(letters + digits) for _ in range(user_len))
    domain = "".join(random.choice(letters) for _ in range(domain_len))
    tld = random.choice(["com", "net", "org", "info", "biz", "xyz", "io"])

    return f"{first.capitalize()} {last.capitalize()} <{email_user}@{domain}.{tld}>"


def get_path_size(path: str) -> int:
    """Calculate the total size of a file or directory in bytes."""
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                with contextlib.suppress(OSError):
                    total_size += os.path.getsize(fp)
    return total_size


def get_dynamic_volume_size(total_bytes: int) -> str:
    """Determine a dynamic volume size based on the total size in bytes."""
    gb = 1024 * 1024 * 1024
    if total_bytes < 2 * gb:
        return "100m"
    elif total_bytes < 10 * gb:
        return "200m"
    elif total_bytes < 50 * gb:
        return "500m"
    else:
        return "1g"


async def check_binary(binary_name: str, config_path: Optional[str] = None, meta: Optional[Meta] = None, path_7z: Optional[str] = None) -> str:
    """Ensure binary exists, returning the resolved path or raising FileNotFoundError."""
    path = config_path or binary_name
    resolved = shutil.which(path)
    if resolved:
        return resolved

    # If the binary is not found, attempt to download it automatically if meta is provided
    if meta and meta.base_dir:
        base_dir = meta.base_dir
        debug = meta.debug
        try:
            if binary_name == "7z":
                from bin.get_7z import SevenZipBinaryManager

                console.print("[yellow]Binary '7z' not found. Attempting to download automatically...[/yellow]")
                return await SevenZipBinaryManager.ensure_7z_binary(base_dir, debug)
            elif binary_name == "nyuu":
                from bin.get_nyuu import NyuuBinaryManager

                console.print("[yellow]Binary 'nyuu' not found. Attempting to download automatically...[/yellow]")
                return await NyuuBinaryManager.ensure_nyuu_binary(base_dir, debug, path_7z=path_7z)
            elif binary_name == "par2":
                from bin.get_par2 import Par2BinaryManager

                console.print("[yellow]Binary 'par2' not found. Attempting to download automatically...[/yellow]")
                return await Par2BinaryManager.ensure_par2_binary(base_dir, debug)
            elif binary_name == "pesto":
                from bin.get_pesto import PestoBinaryManager

                console.print("[yellow]Binary 'pesto' not found. Attempting to download automatically...[/yellow]")
                return await PestoBinaryManager.ensure_pesto_binary(base_dir, debug)
        except Exception as e:
            if debug:
                console.print(f"[yellow]Automatic download of '{binary_name}' failed: {e}[/yellow]")

    raise FileNotFoundError(f"Binary '{path}' not found in PATH or config. Please install it.")



async def run_command_with_logging(cmd: list[str], description: str, debug: bool = False) -> None:
    """Execute a shell command asynchronously and log its output in debug mode."""
    # Redact sensitive info (like password/username) in the printed command
    redacted_cmd = []
    skip_next = False
    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-p", "-u", "--password", "--username") and i + 1 < len(cmd):
            redacted_cmd.append(arg)
            redacted_cmd.append("********")
            skip_next = True
        else:
            redacted_cmd.append(arg)
    redacted_str = " ".join(redacted_cmd)

    if debug:
        console.print(f"[cyan]Running command: {redacted_str}[/cyan]")
    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            console.print(f"[red]Error running {description} (exit code {process.returncode}):[/red]")
            if stdout:
                console.print(f"[red]STDOUT:[/red]\n{stdout.decode(errors='replace')}")
            if stderr:
                console.print(f"[red]STDERR:[/red]\n{stderr.decode(errors='replace')}")
            raise RuntimeError(f"Command '{redacted_str}' failed with exit code {process.returncode}")

    except Exception as e:
        raise RuntimeError(f"Failed to execute command '{redacted_str}': {e}") from e


def parse_volume_size(vol_size: str) -> int:
    """Parse volume size string (e.g. '100m', '1g') into bytes."""
    if not vol_size:
        return 0
    vol_size = vol_size.lower().strip()
    try:
        if vol_size.endswith("g"):
            return int(vol_size[:-1]) * 1024 * 1024 * 1024
        elif vol_size.endswith("m"):
            return int(vol_size[:-1]) * 1024 * 1024
        elif vol_size.endswith("k"):
            return int(vol_size[:-1]) * 1024
        elif vol_size.isdigit():
            return int(vol_size)
    except ValueError:
        pass
    return 0


async def run_7z_with_progress(cmd: list[str], usenet_dir: str, safe_name: str, volume_size: Optional[str], total_size: int, debug: bool = False) -> None:
    """Execute 7z archiving/splitting with real-time volume progress monitoring."""
    redacted_cmd = []
    skip_next = False
    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-p", "-u", "--password", "--username") and i + 1 < len(cmd):
            redacted_cmd.append(arg)
            redacted_cmd.append("********")
            skip_next = True
        else:
            redacted_cmd.append(arg)
    redacted_str = " ".join(redacted_cmd)

    if debug:
        console.print(f"[cyan]Running command: {redacted_str}[/cyan]")

    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        vol_bytes = parse_volume_size(volume_size) if volume_size else 0
        expected_volumes = math.ceil(total_size / vol_bytes) if vol_bytes > 0 else 1

        async def monitor_progress():
            while process.returncode is None:
                try:
                    files = os.listdir(usenet_dir)
                    parts = []
                    for f in files:
                        if f.startswith(safe_name):
                            if f == f"{safe_name}.7z":
                                parts.append(1)
                            else:
                                m = re.search(r"\.7z\.(\d+)$", f)
                                if m:
                                    parts.append(int(m.group(1)))
                    current_part = max(parts) if parts else 0
                    nonlocal expected_volumes
                    if current_part > expected_volumes:
                        expected_volumes = current_part
                    cli_ui.info_progress(f"Archiving/Splitting with 7z: {current_part}/{expected_volumes}", current_part, expected_volumes)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        monitor_task = asyncio.create_task(monitor_progress())
        stdout, stderr = await process.communicate()
        monitor_task.cancel()

        if process.returncode != 0:
            console.print(f"[red]Error running 7z Archiver (exit code {process.returncode}):[/red]")
            if stdout:
                console.print(f"[red]STDOUT:[/red]\n{stdout.decode(errors='replace')}")
            if stderr:
                console.print(f"[red]STDERR:[/red]\n{stderr.decode(errors='replace')}")
            raise RuntimeError(f"Command '{redacted_str}' failed with exit code {process.returncode}")

        # Finish progress display cleanly
        cli_ui.info_progress(f"Archiving/Splitting with 7z: {expected_volumes}/{expected_volumes}", expected_volumes, expected_volumes)

    except Exception as e:
        raise RuntimeError(f"Failed to execute command '{redacted_str}': {e}") from e


async def run_par2_with_progress(cmd: list[str], cwd: Optional[str] = None, debug: bool = False) -> None:
    """Execute par2 c with real-time percentage progress parsing."""
    redacted_cmd = []
    skip_next = False
    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-p", "-u", "--password", "--username") and i + 1 < len(cmd):
            redacted_cmd.append(arg)
            redacted_cmd.append("********")
            skip_next = True
        else:
            redacted_cmd.append(arg)
    redacted_str = " ".join(redacted_cmd)

    if debug:
        cwd_str = f" in {cwd}" if cwd else ""
        console.print(f"[cyan]Running command: {redacted_str}{cwd_str}[/cyan]")

    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=cwd)

        stdout_accum = []
        last_percent = 0

        if process.stdout is None:
            raise RuntimeError("Process stdout is None")

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace")
            stdout_accum.append(line)
            line = line.strip()

            match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if match:
                percent = float(match.group(1))
                last_percent = int(percent)
                action = "Generating PAR2"
                if "Computing" in line:
                    action = "Computing PAR2"
                elif "Writing" in line:
                    action = "Writing PAR2"
                elif "Loading" in line:
                    action = "Loading PAR2"
                cli_ui.info_progress(f"{action}... {percent:.1f}%", int(percent), 100)

        await process.wait()

        if process.returncode != 0:
            console.print(f"[red]Error running PAR2 Creator (exit code {process.returncode}):[/red]")
            stdout_str = "".join(stdout_accum)
            if stdout_str:
                console.print(f"[red]OUTPUT:[/red]\n{stdout_str}")
            raise RuntimeError(f"Command '{redacted_str}' failed with exit code {process.returncode}")

        # Finish progress display cleanly
        if last_percent < 100:
            cli_ui.info_progress("Generating PAR2... 100.0%", 100, 100)

    except Exception as e:
        raise RuntimeError(f"Failed to execute command '{redacted_str}': {e}") from e


async def run_nyuu_with_progress(cmd: list[str], cwd: Optional[str] = None, debug: bool = False) -> None:
    """Execute nyuu upload with real-time speed, ETA, and percentage progress parsing."""
    redacted_cmd = []
    skip_next = False
    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-p", "-u", "--password", "--username") and i + 1 < len(cmd):
            redacted_cmd.append(arg)
            redacted_cmd.append("********")
            skip_next = True
        else:
            redacted_cmd.append(arg)
    redacted_str = " ".join(redacted_cmd)

    if debug:
        cwd_str = f" in {cwd}" if cwd else ""
        console.print(f"[cyan]Running command: {redacted_str}{cwd_str}[/cyan]")

    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=cwd)

        stdout_accum = []
        last_percent = 0

        if process.stdout is None:
            raise RuntimeError("Process stdout is None")

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace")
            stdout_accum.append(line)
            line = line.strip()

            if "Upload:" in line:
                match = re.search(r"\((\d+(?:\.\d+)?)\%\)", line)
                if match:
                    percent = float(match.group(1))
                    last_percent = int(percent)
                    # Extract speed and ETA if possible
                    speed_match = re.search(r"\|\s*([\d\.]+\s*\w+/s)", line)
                    eta_match = re.search(r"ETA:\s*([\d:]+)", line)

                    speed_str = f" ({speed_match.group(1)})" if speed_match else ""
                    eta_str = f" | ETA: {eta_match.group(1)}" if eta_match else ""

                    cli_ui.info_progress(f"Posting to Usenet...{speed_str}{eta_str}", int(percent), 100)

        await process.wait()

        if process.returncode != 0:
            console.print(f"[red]Error running Nyuu Uploader (exit code {process.returncode}):[/red]")
            stdout_str = "".join(stdout_accum)
            if stdout_str:
                console.print(f"[red]OUTPUT:[/red]\n{stdout_str}")
            raise RuntimeError(f"Command '{redacted_str}' failed with exit code {process.returncode}")

        # Finish progress display cleanly
        if last_percent < 100:
            cli_ui.info_progress("Posting to Usenet... 100.0%", 100, 100)

    except Exception as e:
        raise RuntimeError(f"Failed to execute command '{redacted_str}': {e}") from e


async def run_pesto_with_progress(cmd: list[str], cwd: Optional[str] = None, debug: bool = False) -> None:
    """Execute pesto upload consuming its JSON event stream for progress reporting."""
    redacted_cmd = []
    skip_next = False
    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-p", "-u", "--auth-password", "--username") and i + 1 < len(cmd):
            redacted_cmd.append(arg)
            redacted_cmd.append("********")
            skip_next = True
        else:
            redacted_cmd.append(arg)
    redacted_str = " ".join(redacted_cmd)

    if debug:
        cwd_str = f" in {cwd}" if cwd else ""
        console.print(f"[cyan]Running command: {redacted_str}{cwd_str}[/cyan]")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        last_percent = 0
        stderr_accum = []

        if process.stdout is None or process.stderr is None:
            raise RuntimeError("Process stdout or stderr is None")

        async def drain_stderr():
            while True:
                assert process.stderr is not None
                line = await process.stderr.readline()
                if not line:
                    break
                stderr_accum.append(line.decode(errors="replace"))

        stderr_task = asyncio.create_task(drain_stderr())

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                etype = event.get("type")
                if etype == "segment_done":
                    pct = float(event.get("progress_pct", 0))
                    last_percent = int(pct)
                    cli_ui.info_progress(f"Posting to Usenet... {pct:.1f}%", last_percent, 100)
                elif etype == "status":
                    text = event.get("text", "").strip()
                    if text and debug:
                        console.print(f"[cyan]{text}[/cyan]")
                elif etype == "failed":
                    desc = event.get("description", "unknown failure")
                    console.print(f"[red]Pesto segment failed: {desc}[/red]")
            except json.JSONDecodeError:
                pass

        await stderr_task
        await process.wait()

        if process.returncode != 0:
            console.print(f"[red]Error running Pesto Uploader (exit code {process.returncode}):[/red]")
            stderr_str = "".join(stderr_accum)
            if stderr_str:
                console.print(f"[red]STDERR:[/red]\n{stderr_str}")
            raise RuntimeError(f"Command '{redacted_str}' failed with exit code {process.returncode}")

        if last_percent < 100:
            cli_ui.info_progress("Posting to Usenet... 100.0%", 100, 100)

    except Exception as e:
        raise RuntimeError(f"Failed to execute command '{redacted_str}': {e}") from e


async def is_valid_nzb(path: str) -> bool:
    """Check if an NZB file exists, is non-empty, and ends with proper XML/NZB closing tag."""
    if not await aiofiles.ospath.isfile(path):
        return False
    try:
        size = await aiofiles.ospath.getsize(path)
        if size < 100:
            return False
        async with aiofiles.open(path, "rb") as f:
            if size > 1024:
                await f.seek(size - 1024)
                chunk = await f.read(1024)
            else:
                chunk = await f.read()
            content_sample = chunk.decode("utf-8", errors="ignore").strip()
            return "</nzb>" in content_sample
    except Exception:
        return False


async def inject_nzb_password(nzb_path: str, password: str) -> None:
    """Inject <meta type="password">password</meta> into the NZB's <head> section."""
    if not await aiofiles.ospath.exists(nzb_path):
        return
    try:
        async with aiofiles.open(nzb_path, encoding="utf-8", errors="ignore") as f:
            content = await f.read()

        head_match = re.search(r"<head\b[^>]*>", content, re.IGNORECASE)
        if head_match:
            idx = head_match.end()
            new_content = content[:idx] + f'\n    <meta type="password">{password}</meta>' + content[idx:]
        else:
            nzb_match = re.search(r"<nzb\b[^>]*>", content, re.IGNORECASE)
            if nzb_match:
                idx = nzb_match.end()
                inserted = f'\n  <head>\n    <meta type="password">{password}</meta>\n  </head>'
                new_content = content[:idx] + inserted + content[idx:]
            else:
                return

        async with aiofiles.open(nzb_path, "w", encoding="utf-8") as f:
            await f.write(new_content)
    except Exception as e:
        console.print(f"[red]Error injecting password into NZB file: {e}[/red]")


async def verify_nzb_has_password(nzb_path: str) -> bool:
    """Verify that the NZB file contains a password tag inside the head section."""
    if not await aiofiles.ospath.isfile(nzb_path):
        return False
    try:
        # Read the first 4096 bytes (the head section is always at the beginning)
        async with aiofiles.open(nzb_path, encoding="utf-8", errors="ignore") as f:
            header_sample = await f.read(4096)

        head_match = re.search(r"<head\b[^>]*>(.*?)</head>", header_sample, re.IGNORECASE | re.DOTALL)
        if head_match:
            head_content = head_match.group(1)
            if re.search(r'<meta\s+type=["\']password["\']', head_content, re.IGNORECASE):
                return True
    except Exception:
        pass
    return False


async def prepare_and_upload_usenet(meta: Meta, config: dict[str, Any]) -> Optional[str]:
    """
    Prepare files (7z + PAR2) and upload them to Usenet via nyuu or pesto.
    Returns the absolute path to the generated NZB file if successful.
    """
    usenet_cfg = config.get("USENET", {})
    if not usenet_cfg:
        console.print("[red]Error: USENET section is missing from configuration.[/red]")
        return None

    # Handle Usenet archive encryption/password
    archive_password = usenet_cfg.get("archive_password")
    if archive_password:
        if str(archive_password).lower() == "random":
            archive_password = secrets.token_urlsafe(16)
            if meta.debug:
                console.print(f"[cyan]Generated random Usenet archive password: {archive_password}[/cyan]")
            else:
                console.print("[cyan]Generated unique random password for Usenet archive encryption.[/cyan]")
        else:
            console.print("[cyan]Using configured static password for Usenet archive encryption.[/cyan]")
        meta.archive_password = archive_password

    # Determine paths and names
    base_dir = meta.base_dir
    input_path = meta.path
    import hashlib

    # Shorten the UUID to prevent path-length issues (MAX_PATH limit of 260) on Windows specifically for Usenet staging
    clean_uuid = "".join(c for c in meta.uuid if c.isalnum() or c in "._-")[:30]
    uuid_hash = hashlib.md5(meta.uuid.encode("utf-8")).hexdigest()[:8]
    uuid = f"{clean_uuid}_{uuid_hash}" if clean_uuid else uuid_hash
    name = meta.basename_no_ext

    # Sanitize name for filenames
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
    safe_name = safe_name.replace(" ", ".")

    # Determine obfuscated archive name if password protection is enabled
    archive_name = safe_name
    if archive_password:
        archive_name = secrets.token_hex(16)
        if meta.debug:
            console.print(f"[cyan]Obfuscating archive filenames to: {archive_name}[/cyan]")
        else:
            console.print("[cyan]Obfuscating archive filenames for security.[/cyan]")

    # NZB filename: prefer meta name (already properly constructed by UA).
    # For directories, fall back to the directory basename only when meta name is absent.
    if safe_name:
        safe_nzb_name = safe_name
    elif os.path.isdir(input_path):
        folder_name = os.path.basename(input_path)
        safe_nzb_name = "".join(c for c in folder_name if c.isalnum() or c in "._- ").replace(" ", ".") or safe_name
    else:
        safe_nzb_name = safe_name

    # Determine NZB output directory (falls back to default tmp dir if empty)
    nzb_output_dir = usenet_cfg.get("nzb_output_dir")
    if not nzb_output_dir:
        nzb_output_dir = os.path.join(base_dir, "tmp", os.path.basename(meta.path))

    try:
        os.makedirs(nzb_output_dir, exist_ok=True)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not create nzb_output_dir '{nzb_output_dir}' ({e}). Falling back to default tmp dir.[/yellow]")
        nzb_output_dir = os.path.join(base_dir, "tmp", os.path.basename(meta.path))
        with contextlib.suppress(Exception):
            os.makedirs(nzb_output_dir, exist_ok=True)

    # Determine tmp base directory for staging (falls back to default tmp dir if empty)
    usenet_tmp_dir = usenet_cfg.get("usenet_tmp_dir")
    if usenet_tmp_dir:
        try:
            os.makedirs(usenet_tmp_dir, exist_ok=True)
            tmp_base = usenet_tmp_dir
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create usenet_tmp_dir '{usenet_tmp_dir}' ({e}). Falling back to default tmp dir.[/yellow]")
            tmp_base = os.path.join(base_dir, "tmp", os.path.basename(meta.path))
    else:
        tmp_base = os.path.join(base_dir, "tmp", os.path.basename(meta.path))

    # Check if a valid NZB file already exists to skip the upload process
    final_nzb_path = os.path.join(nzb_output_dir, f"{safe_nzb_name}.nzb")
    nzb_file = os.path.join(tmp_base, uuid, f"{safe_nzb_name}.nzb")

    for path_to_check in [final_nzb_path, nzb_file]:
        if path_to_check and await is_valid_nzb(path_to_check):
            return path_to_check

    # Temp Usenet directory
    usenet_dir = os.path.join(tmp_base, uuid, "usenet")
    await aiofiles.os.makedirs(usenet_dir, exist_ok=True)

    is_debug = meta.debug
    uploader = str(usenet_cfg.get("usenet_uploader", "nyuu")).lower()
    use_pesto = uploader == "pesto"

    path_7z: Optional[str] = None
    path_par2: Optional[str] = None
    path_nyuu: Optional[str] = None
    path_pesto: Optional[str] = None

    # 1. Resolve Binaries
    try:
        path_7z = await check_binary("7z", usenet_cfg.get("7z_path"), meta=meta)
    except FileNotFoundError as e:
        if is_debug:
            console.print(f"[yellow]Warning: {e} Using simulation mode for 7z.[/yellow]")
        else:
            console.print(f"[bold red]Configuration Error: {e}[/bold red]")
            return None

    if use_pesto:
        try:
            path_pesto = await check_binary("pesto", usenet_cfg.get("pesto_path"), meta=meta)
        except FileNotFoundError as e:
            if is_debug:
                console.print(f"[yellow]Warning: {e} Using simulation mode for pesto.[/yellow]")
            else:
                console.print(f"[bold red]Configuration Error: {e}[/bold red]")
                return None
    else:
        try:
            path_par2 = await check_binary("par2", usenet_cfg.get("par2_path"), meta=meta)
        except FileNotFoundError as e:
            if is_debug:
                console.print(f"[yellow]Warning: {e} Using simulation mode for par2.[/yellow]")
            else:
                console.print(f"[bold red]Configuration Error: {e}[/bold red]")
                return None

        try:
            path_nyuu = await check_binary("nyuu", usenet_cfg.get("nyuu_path"), meta=meta, path_7z=path_7z)
        except FileNotFoundError as e:
            if is_debug:
                console.print(f"[yellow]Warning: {e} Using simulation mode for nyuu.[/yellow]")
            else:
                console.print(f"[bold red]Configuration Error: {e}[/bold red]")
                return None

    # 2. Archive and Split with 7z (mx=0 to store without compression)
    skip_archive = usenet_cfg.get("skip_archive", False)
    volume_size = usenet_cfg.get("rar_volume_size")
    total_size = await asyncio.to_thread(get_path_size, input_path)

    if skip_archive:
        # Skip 7z entirely — copy files/dir contents straight to usenet_dir
        console.print("[cyan]Skipping archive step; copying files directly for upload...[/cyan]")
        if await aiofiles.ospath.isdir(input_path):
            for entry in await aiofiles.os.listdir(input_path):
                src = os.path.join(input_path, entry)
                dst = os.path.join(usenet_dir, entry)
                if os.path.isfile(src):
                    if is_debug and not await aiofiles.ospath.exists(src):
                        async with aiofiles.open(dst, "wb") as f:
                            await f.write(b"mock file content")
                    else:
                        await asyncio.to_thread(shutil.copy2, src, dst)
        else:
            dest_file = os.path.join(usenet_dir, os.path.basename(input_path))
            if is_debug and not await aiofiles.ospath.exists(input_path):
                async with aiofiles.open(dest_file, "wb") as f:
                    await f.write(b"mock single file content")
            else:
                await asyncio.to_thread(shutil.copy2, input_path, dest_file)
    else:
        if volume_size and volume_size.lower() == "auto":
            volume_size = get_dynamic_volume_size(total_size)
            if is_debug:
                console.print(f"[cyan]Dynamic volume size chosen based on upload size ({total_size / (1024 * 1024 * 1024):.2f} GB): {volume_size.upper()}[/cyan]")
            else:
                console.print(f"[cyan]Dynamic volume size chosen: {volume_size.upper()}[/cyan]")

        archive_out = os.path.join(usenet_dir, f"{archive_name}.7z")

        if await aiofiles.ospath.isdir(input_path) or volume_size or archive_password:
            cmd_7z = [path_7z or "7z", "a", "-mx=0"]
            if volume_size:
                cmd_7z.append(f"-v{volume_size.lower()}")
            if archive_password:
                cmd_7z.extend([f"-p{archive_password}", "-mhe=on"])
            cmd_7z.extend([archive_out, input_path])

            if is_debug and not path_7z:
                console.print(f"[yellow][DEBUG SIMULATION] Would run: {' '.join(cmd_7z)}[/yellow]")
                mock_7z = f"{archive_out}.001" if volume_size else archive_out
                async with aiofiles.open(mock_7z, "wb") as f:
                    await f.write(b"mock 7z volume content")
            else:
                await run_7z_with_progress(cmd_7z, usenet_dir, archive_name, volume_size, total_size, debug=is_debug)
        else:
            console.print("[cyan]Copying single file for upload...[/cyan]")
            dest_file = os.path.join(usenet_dir, os.path.basename(input_path))
            if is_debug and not await aiofiles.ospath.exists(input_path):
                console.print(f"[yellow][DEBUG SIMULATION] Input path '{input_path}' doesn't exist, writing dummy file to '{dest_file}'[/yellow]")
                async with aiofiles.open(dest_file, "wb") as f:
                    await f.write(b"mock single file content")
            else:
                await asyncio.to_thread(shutil.copy, input_path, dest_file)

    par2_percentage = usenet_cfg.get("par2_percentage", "10")

    # 3. PAR2 — only when using nyuu (pesto handles PAR2 internally)
    if not use_pesto:
        target_files = []
        for f in await aiofiles.os.listdir(usenet_dir):
            file_path = os.path.join(usenet_dir, f)
            if await aiofiles.ospath.isfile(file_path) and not f.endswith(".par2"):
                target_files.append(file_path)

        if target_files:
            console.print("[cyan]Generating PAR2 parity files...[/cyan]")
            par2_file = f"{archive_name}.par2"
            relative_target_files = [os.path.basename(f) for f in target_files]
            cmd_par2 = [path_par2 or "par2", "c", f"-r{par2_percentage}", "-n1", par2_file] + relative_target_files
            if is_debug and not path_par2:
                console.print(f"[yellow][DEBUG SIMULATION] Would run: {' '.join(cmd_par2)}[/yellow]")
                mock_par2 = os.path.normpath(os.path.join(usenet_dir, par2_file))
                async with aiofiles.open(mock_par2, "wb") as f:
                    await f.write(b"mock par2 content")
            else:
                await run_par2_with_progress(cmd_par2, cwd=usenet_dir, debug=is_debug)

    # 4. Poster / From header
    random_poster = usenet_cfg.get("random_poster", True)
    poster = usenet_cfg.get("poster", "Uploader <upload@assistant.org>")
    if random_poster:
        poster = generate_random_poster()
        display_name = poster.split("<")[0].strip()
        if is_debug:
            console.print(f"[cyan]Generated anonymous poster: {display_name}[/cyan]")

    # 5. Subject line
    obscure_subject = usenet_cfg.get("obscure_subject", True)
    custom_subject = meta.usenet_subject

    if custom_subject:
        subject = custom_subject
    elif obscure_subject:
        subject = secrets.token_hex(16)
        if is_debug:
            console.print(f"[cyan]Obfuscating post subject: {subject}[/cyan]")
        else:
            console.print("[cyan]Obfuscating post subject...[/cyan]")
    else:
        subject = name

    # 6. Collect files to upload
    nzb_file = os.path.join(tmp_base, uuid, f"{safe_nzb_name}.nzb")

    all_upload_files = []
    for f in await aiofiles.os.listdir(usenet_dir):
        file_path = os.path.join(usenet_dir, f)
        if await aiofiles.ospath.isfile(file_path):
            all_upload_files.append(f)

    console.print(f"[yellow]Posting {len(all_upload_files)} files to Usenet via NNTP ({uploader})...[/yellow]")

    # Build mock NZB content used in debug/simulation mode
    mock_nzb_password_tag = f'  <meta type="password">{archive_password}</meta>\n' if archive_password else ""
    mock_nzb_content = (
        '<?xml version="1.0" encoding="utf-8" ?>\n'
        '<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.1//EN" "http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">\n'
        '<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">\n'
        "  <!-- Mock NZB file generated in debug/simulation mode -->\n"
        f"  <head>\n{mock_nzb_password_tag}  </head>\n"
        '  <meta type="title">Mock Upload</meta>\n'
        "</nzb>\n"
    )

    if use_pesto:
        # 6a. Upload via pesto
        cmd_pesto = [
            path_pesto or "pesto",
            "-s", usenet_cfg.get("host"),
            "-P", str(usenet_cfg.get("port", 563)),
            "-u", usenet_cfg.get("username"),
            "-p", usenet_cfg.get("password"),
            "-n", str(usenet_cfg.get("connections", 20)),
            "-g", usenet_cfg.get("newsgroups"),
            "--out", nzb_file,
            "--par2", str(par2_percentage),
            "--output-format", "json",
        ]

        if not usenet_cfg.get("ssl", True):
            cmd_pesto.append("--no-ssl")

        if not random_poster:
            cmd_pesto.extend(["-f", poster])

        if obscure_subject and not custom_subject:
            cmd_pesto.append("--obfuscate=full")

        if archive_password:
            cmd_pesto.extend(["--nzb-password", archive_password])

        cmd_pesto.extend(all_upload_files)

        if is_debug:
            console.print(f"[yellow][DEBUG SIMULATION] Would run Pesto upload: {' '.join(cmd_pesto)}[/yellow]")
            async with aiofiles.open(nzb_file, "w", encoding="utf-8") as f:
                await f.write(mock_nzb_content)
        else:
            await run_pesto_with_progress(cmd_pesto, cwd=usenet_dir, debug=is_debug)
    else:
        # 6b. Upload via nyuu
        cmd_nyuu = [
            path_nyuu or "nyuu",
            "-h", usenet_cfg.get("host"),
            "-P", str(usenet_cfg.get("port", 563)),
            "-u", usenet_cfg.get("username"),
            "-p", usenet_cfg.get("password"),
            "-n", str(usenet_cfg.get("connections", 20)),
            "-g", usenet_cfg.get("newsgroups"),
            "-f", poster,
            "-s", subject,
            "-o", nzb_file,
        ]

        if usenet_cfg.get("ssl", True):
            cmd_nyuu.append("-S")

        cmd_nyuu.extend(all_upload_files)

        if is_debug:
            console.print(f"[yellow][DEBUG SIMULATION] Would run Nyuu upload: {' '.join(cmd_nyuu)}[/yellow]")
            async with aiofiles.open(nzb_file, "w", encoding="utf-8") as f:
                await f.write(mock_nzb_content)
        else:
            await run_nyuu_with_progress(cmd_nyuu, cwd=usenet_dir, debug=is_debug)

        # nyuu doesn't inject the password into the NZB — do it manually
        if archive_password and await aiofiles.ospath.exists(nzb_file):
            if is_debug:
                console.print(f"[cyan][DEBUG SIMULATION] Injecting password '{archive_password}' into NZB file...[/cyan]")
            else:
                console.print("[cyan]Injecting password into NZB metadata...[/cyan]")
            await inject_nzb_password(nzb_file, archive_password)

    # 7. Cleanup compressed volumes after successful upload
    try:
        if await aiofiles.ospath.exists(usenet_dir):
            if is_debug:
                console.print(f"[cyan][DEBUG SIMULATION] Would delete temporary Usenet folder: {usenet_dir}[/cyan]")
            else:
                await asyncio.to_thread(shutil.rmtree, usenet_dir)
                console.print("[green]Cleaned up temporary compressed Usenet files.[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not clean up temporary Usenet folder '{usenet_dir}' ({e})[/yellow]")

    # 8. Relocate NZB output
    if await aiofiles.ospath.exists(nzb_file):
        try:
            await asyncio.to_thread(shutil.move, nzb_file, final_nzb_path)
            if is_debug:
                console.print(f"[bold green]NZB file saved to: {final_nzb_path}[/bold green]")
        except Exception as e:
            console.print(f"[red]Error moving NZB file to final destination: {e}[/red]")
            final_nzb_path = nzb_file

    # Clean up empty parent uuid folder
    uuid_dir = os.path.join(tmp_base, uuid)
    try:
        if not is_debug and await aiofiles.ospath.exists(uuid_dir) and not os.listdir(uuid_dir):
            await asyncio.to_thread(os.rmdir, uuid_dir)
    except Exception:
        pass

    return final_nzb_path
