# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
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

Meta = dict[str, Any]


def generate_random_poster() -> str:
    """Generate a realistic random poster name and email for Usenet anonymity."""
    first_names = [
        "alpha", "beta", "gamma", "delta", "epsilon", "omega", "zeta", "eta",
        "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron",
        "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi"
    ]
    last_names = [
        "post", "upload", "share", "news", "net", "bin", "nntp", "user",
        "agent", "peer", "node", "seed", "stream", "pack", "dist"
    ]
    domains = [
        "anon.org", "usenet.net", "nntp.org", "binaries.com", "privacy.net",
        "obfuscated.com", "newsgroup.co", "sslpost.org", "nntp2.net"
    ]

    first = random.choice(first_names)
    last = random.choice(last_names)
    num = random.randint(100, 999)
    email_user = f"{first}{num}"
    domain = random.choice(domains)

    return f"{first.capitalize()} {last.capitalize()} <{email_user}@{domain}>"


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
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    pass
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


async def check_binary(binary_name: str, config_path: Optional[str] = None) -> str:
    """Ensure binary exists, returning the resolved path or raising FileNotFoundError."""
    path = config_path or binary_name
    resolved = shutil.which(path)
    if not resolved:
        raise FileNotFoundError(f"Binary '{path}' not found in PATH or config. Please install it.")
    return resolved


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
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
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


async def run_par2_with_progress(cmd: list[str], debug: bool = False) -> None:
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
        console.print(f"[cyan]Running command: {redacted_str}[/cyan]")

    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

        stdout_accum = []
        last_percent = 0

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


async def run_nyuu_with_progress(cmd: list[str], debug: bool = False) -> None:
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
        console.print(f"[cyan]Running command: {redacted_str}[/cyan]")

    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

        stdout_accum = []
        last_percent = 0

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


async def prepare_and_upload_usenet(meta: Meta, config: dict[str, Any]) -> Optional[str]:
    """
    Prepare files (7z + PAR2) and upload them to Usenet via Nyuu.
    Returns the absolute path to the generated NZB file if successful.
    """
    usenet_cfg = config.get("USENET", {})
    if not usenet_cfg:
        console.print("[red]Error: USENET section is missing from configuration.[/red]")
        return None

    # Determine paths and names
    base_dir = meta["base_dir"]
    input_path = meta["path"]
    uuid = meta["uuid"]
    name = meta.get("name") or os.path.basename(input_path)

    # Sanitize name for filenames
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
    safe_name = safe_name.replace(" ", ".")

    # Determine the directory/folder being processed for the NZB file name
    folder_name = os.path.basename(input_path) if os.path.isdir(input_path) else os.path.basename(os.path.dirname(input_path))

    if folder_name:
        safe_nzb_name = "".join(c for c in folder_name if c.isalnum() or c in "._- ")
        safe_nzb_name = safe_nzb_name.replace(" ", ".")
    else:
        safe_nzb_name = safe_name

    if not safe_nzb_name:
        safe_nzb_name = safe_name

    # Determine tmp base directory
    usenet_tmp_dir = usenet_cfg.get("usenet_tmp_dir")
    if usenet_tmp_dir:
        try:
            os.makedirs(usenet_tmp_dir, exist_ok=True)
            tmp_base = usenet_tmp_dir
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create usenet_tmp_dir '{usenet_tmp_dir}' ({e}). Falling back to default tmp dir.[/yellow]")
            tmp_base = os.path.join(base_dir, "tmp")
    else:
        tmp_base = os.path.join(base_dir, "tmp")

    # Check if a valid NZB file already exists to skip the upload process
    nzb_file = os.path.join(tmp_base, uuid, f"{safe_nzb_name}.nzb")
    nzb_output_dir = usenet_cfg.get("nzb_output_dir")
    final_nzb_path = None
    if nzb_output_dir and await aiofiles.ospath.exists(nzb_output_dir):
        final_nzb_path = os.path.join(nzb_output_dir, f"{safe_nzb_name}.nzb")

    for path_to_check in [final_nzb_path, nzb_file]:
        if path_to_check and await is_valid_nzb(path_to_check):
            return path_to_check

    # Temp Usenet directory
    usenet_dir = os.path.join(tmp_base, uuid, "usenet")
    await aiofiles.os.makedirs(usenet_dir, exist_ok=True)

    is_debug = meta.get("debug", False)
    path_7z: Optional[str] = None
    path_par2: Optional[str] = None
    path_nyuu: Optional[str] = None

    # 1. Resolve Binaries
    try:
        path_7z = await check_binary("7z", usenet_cfg.get("7z_path"))
    except FileNotFoundError as e:
        if is_debug:
            console.print(f"[yellow]Warning: {e} Using simulation mode for 7z.[/yellow]")
        else:
            console.print(f"[bold red]Configuration Error: {e}[/bold red]")
            return None

    try:
        path_par2 = await check_binary("par2", usenet_cfg.get("par2_path"))
    except FileNotFoundError as e:
        if is_debug:
            console.print(f"[yellow]Warning: {e} Using simulation mode for par2.[/yellow]")
        else:
            console.print(f"[bold red]Configuration Error: {e}[/bold red]")
            return None

    try:
        path_nyuu = await check_binary("nyuu", usenet_cfg.get("nyuu_path"))
    except FileNotFoundError as e:
        if is_debug:
            console.print(f"[yellow]Warning: {e} Using simulation mode for nyuu.[/yellow]")
        else:
            console.print(f"[bold red]Configuration Error: {e}[/bold red]")
            return None

    # 2. Archive and Split with 7z (mx=0 to store without compression)
    volume_size = usenet_cfg.get("rar_volume_size")
    total_size = await asyncio.to_thread(get_path_size, input_path)
    if volume_size and volume_size.lower() == "auto":
        volume_size = get_dynamic_volume_size(total_size)
        if is_debug:
            console.print(f"[cyan]Dynamic volume size chosen based on upload size ({total_size / (1024 * 1024 * 1024):.2f} GB): {volume_size.upper()}[/cyan]")
        else:
            console.print(f"[cyan]Dynamic volume size chosen: {volume_size.upper()}[/cyan]")

    archive_out = os.path.join(usenet_dir, f"{safe_name}.7z")

    if await aiofiles.ospath.isdir(input_path) or volume_size:
        cmd_7z = [path_7z or "7z", "a", "-mx=0"]
        if volume_size:
            # E.g. -v100m
            cmd_7z.append(f"-v{volume_size.lower()}")
        cmd_7z.extend([archive_out, input_path])

        if is_debug and not path_7z:
            console.print(f"[yellow][DEBUG SIMULATION] Would run: {' '.join(cmd_7z)}[/yellow]")
            # Create a mock 7z file so PAR2 step has a target file
            mock_7z = f"{archive_out}.001" if volume_size else archive_out
            async with aiofiles.open(mock_7z, "wb") as f:
                await f.write(b"mock 7z volume content")
        else:
            await run_7z_with_progress(cmd_7z, usenet_dir, safe_name, volume_size, total_size, debug=is_debug)
    else:
        # Single file and no volume size -> just copy/link to usenet dir
        console.print("[cyan]Copying single file for upload...[/cyan]")
        dest_file = os.path.join(usenet_dir, os.path.basename(input_path))
        if is_debug and not await aiofiles.ospath.exists(input_path):
            console.print(f"[yellow][DEBUG SIMULATION] Input path '{input_path}' doesn't exist, writing dummy file to '{dest_file}'[/yellow]")
            async with aiofiles.open(dest_file, "wb") as f:
                await f.write(b"mock single file content")
        else:
            await asyncio.to_thread(shutil.copy, input_path, dest_file)

    # 3. Create PAR2 Recovery Files
    par2_percentage = usenet_cfg.get("par2_percentage", "10")
    # Identify files in the usenet directory to parity-protect
    target_files = []
    for f in await aiofiles.os.listdir(usenet_dir):
        file_path = os.path.join(usenet_dir, f)
        if await aiofiles.ospath.isfile(file_path) and not f.endswith(".par2"):
            target_files.append(file_path)

    if target_files:
        console.print("[cyan]Generating PAR2 parity files...[/cyan]")
        par2_file = os.path.join(usenet_dir, f"{safe_name}.par2")
        cmd_par2 = [path_par2 or "par2", "c", f"-r{par2_percentage}", "-n1", par2_file] + target_files
        if is_debug and not path_par2:
            console.print(f"[yellow][DEBUG SIMULATION] Would run: {' '.join(cmd_par2)}[/yellow]")
            # Create a mock par2 file
            async with aiofiles.open(par2_file, "wb") as f:
                await f.write(b"mock par2 content")
        else:
            await run_par2_with_progress(cmd_par2, debug=is_debug)

    # 4. Generate Poster / From
    poster = usenet_cfg.get("poster", "Uploader <upload@assistant.org>")
    if usenet_cfg.get("random_poster", True):
        poster = generate_random_poster()
        # Clean up output: just display the name rather than full email unless debugging
        display_name = poster.split("<")[0].strip()
        if is_debug:
            console.print(f"[cyan]Generated anonymous poster: {display_name}[/cyan]")

    # 5. Generate Subject Line
    obscure_subject = usenet_cfg.get("obscure_subject", True)
    custom_subject = meta.get("usenet_subject")

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

    # 6. Perform Upload using Nyuu
    nzb_file = os.path.join(tmp_base, uuid, f"{safe_nzb_name}.nzb")

    cmd_nyuu = [
        path_nyuu or "nyuu",
        "-h",
        usenet_cfg.get("host"),
        "-P",
        str(usenet_cfg.get("port", 563)),
        "-u",
        usenet_cfg.get("username"),
        "-p",
        usenet_cfg.get("password"),
        "-n",
        str(usenet_cfg.get("connections", 20)),
        "-g",
        usenet_cfg.get("newsgroups"),
        "-f",
        poster,
        "-s",
        subject,
        "-o",
        nzb_file,
    ]

    if usenet_cfg.get("ssl", True):
        cmd_nyuu.append("-S")

    # Add all files in the Usenet directory as targets to upload
    all_upload_files = []
    for f in await aiofiles.os.listdir(usenet_dir):
        file_path = os.path.join(usenet_dir, f)
        if await aiofiles.ospath.isfile(file_path):
            all_upload_files.append(file_path)
    cmd_nyuu.extend(all_upload_files)

    console.print(f"[yellow]Posting {len(all_upload_files)} files to Usenet via NNTP...[/yellow]")
    if is_debug:
        console.print(f"[yellow][DEBUG SIMULATION] Would run Nyuu upload: {' '.join(cmd_nyuu)}[/yellow]")
        # Write a mock/dummy NZB file (valid XML structure containing a comment)
        mock_nzb_content = (
            "<?xml version=\"1.0\" encoding=\"utf-8\" ?>\n"
            "<!DOCTYPE nzb PUBLIC \"-//newzBin//DTD NZB 1.1//EN\" \"http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd\">\n"
            "<nzb xmlns=\"http://www.newzbin.com/DTD/2003/nzb\">\n"
            "  <!-- Mock NZB file generated in debug/simulation mode -->\n"
            "  <meta type=\"title\">Mock Upload</meta>\n"
            "</nzb>\n"
        )
        async with aiofiles.open(nzb_file, "w", encoding="utf-8") as f:
            await f.write(mock_nzb_content)
    else:
        await run_nyuu_with_progress(cmd_nyuu, debug=is_debug)

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

    # 8. Relocate NZB output if requested
    nzb_output_dir = usenet_cfg.get("nzb_output_dir")
    if nzb_output_dir and await aiofiles.ospath.exists(nzb_output_dir):
        final_nzb_path = os.path.join(nzb_output_dir, f"{safe_nzb_name}.nzb")
        await asyncio.to_thread(shutil.move, nzb_file, final_nzb_path)

        # Clean up empty parent uuid folder
        uuid_dir = os.path.join(tmp_base, uuid)
        try:
            if not is_debug and await aiofiles.ospath.exists(uuid_dir) and not os.listdir(uuid_dir):
                await asyncio.to_thread(os.rmdir, uuid_dir)
        except Exception:
            pass

        if is_debug:
            console.print(f"[bold green]NZB file saved to: {final_nzb_path}[/bold green]")
        return final_nzb_path
    else:
        if is_debug:
            console.print(f"[bold green]NZB file saved to: {nzb_file}[/bold green]")
        return nzb_file
