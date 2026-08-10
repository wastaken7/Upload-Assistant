# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import fnmatch
import math
import os
import platform
import random
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cli_ui
import torf
from rich.progress import BarColumn, TaskProgressColumn, TextColumn
from torf import Torrent

from bin.get_mkbrr import MkbrrBinaryManager
from src.console import console, is_cli_progress_suppressed, logger, progress_display
from src.meta import Meta
from src.webui_progress import complete_progress, has_progress_callback, publish_progress

PIECE_SIZE_MIN = 32 * 1024  # 32 KiB
PIECE_SIZE_MAX = 134_217_728  # 128 MiB
SUBTITLE_EXTENSIONS = (".srt", ".sub", ".vtt", ".ssa", ".ass", ".idx")


def calculate_piece_size(
    total_size: int,
    min_size: int,
    max_size: int,
    meta: Meta,
    piece_size: int | None = None,
) -> int:
    return TorrentCreator.calculate_piece_size(
        total_size=total_size,
        min_size=min_size,
        max_size=max_size,
        meta=meta,
        piece_size=piece_size,
    )


class CustomTorrent(torf.Torrent):
    def __init__(self, meta: Meta, *args: Any, **kwargs: Any) -> None:
        self._meta = meta

        # Extract and store the precalculated piece size
        self._precalculated_piece_size: int | None = kwargs.pop("piece_size", None)
        super().__init__(*args, **kwargs)

        # Set piece size directly
        if self._precalculated_piece_size is not None:
            self._piece_size = self._precalculated_piece_size
            self.metainfo["info"]["piece length"] = self._precalculated_piece_size

    @property
    def piece_size_min(self) -> int:
        return PIECE_SIZE_MIN

    @piece_size_min.setter
    def piece_size_min(self, piece_size_min: int | None) -> None:
        _ = piece_size_min
        return

    @property
    def piece_size_max(self) -> int:
        return PIECE_SIZE_MAX

    @piece_size_max.setter
    def piece_size_max(self, piece_size_max: int | None) -> None:
        _ = piece_size_max
        return

    @property
    def piece_size(self) -> int:
        return self._piece_size

    @piece_size.setter
    def piece_size(self, value: int | None) -> None:
        if self._precalculated_piece_size is not None:
            value = self._precalculated_piece_size
        if value is None:
            return

        self._piece_size = value
        self.metainfo["info"]["piece length"] = value

    def validate_piece_size(self, _meta: Meta | None = None) -> None:
        if self._precalculated_piece_size is not None:
            self._piece_size = self._precalculated_piece_size
            self.metainfo["info"]["piece length"] = self._precalculated_piece_size
            return


class TorrentCreator:
    # Limit concurrent torrent creation to avoid heavy parallel hashing
    _create_torrent_semaphore = asyncio.Semaphore(1)
    _create_torrent_inflight = 0
    _torf_start_time = time.time()

    @staticmethod
    def calculate_piece_size(
        total_size: int,
        min_size: int,
        max_size: int,
        meta: Meta,
        piece_size: int | None = None,
    ) -> int:
        # Set max_size
        if piece_size:
            try:
                max_size = min(piece_size * 1024 * 1024, PIECE_SIZE_MAX)
            except ValueError:
                max_size = 134217728  # Fallback to default if conversion fails
        else:
            max_size = 134217728  # 128 MiB default maximum

        logger.debug(f"Content size: {total_size / (1024 * 1024):.2f} MiB")
        logger.debug(f"Max size: {max_size}")

        total_size_mib = total_size / (1024 * 1024)

        if total_size_mib <= 60:  # <= 60 MiB
            piece_size = 32 * 1024  # 32 KiB
        elif total_size_mib <= 120:  # <= 120 MiB
            piece_size = 64 * 1024  # 64 KiB
        elif total_size_mib <= 240:  # <= 240 MiB
            piece_size = 128 * 1024  # 128 KiB
        elif total_size_mib <= 480:  # <= 480 MiB
            piece_size = 256 * 1024  # 256 KiB
        elif total_size_mib <= 960:  # <= 960 MiB
            piece_size = 512 * 1024  # 512 KiB
        elif total_size_mib <= 1920:  # <= 1.875 GiB
            piece_size = 1024 * 1024  # 1 MiB
        elif total_size_mib <= 3840:  # <= 3.75 GiB
            piece_size = 2 * 1024 * 1024  # 2 MiB
        elif total_size_mib <= 7680:  # <= 7.5 GiB
            piece_size = 4 * 1024 * 1024  # 4 MiB
        elif total_size_mib <= 15360:  # <= 15 GiB
            piece_size = 8 * 1024 * 1024  # 8 MiB
        elif total_size_mib <= 46080:  # <= 45 GiB
            piece_size = 16 * 1024 * 1024  # 16 MiB
        elif total_size_mib <= 92160:  # <= 90 GiB
            piece_size = 32 * 1024 * 1024  # 32 MiB
        elif total_size_mib <= 138240:  # <= 135 GiB
            piece_size = 64 * 1024 * 1024
        else:
            piece_size = 128 * 1024 * 1024  # 128 MiB

        if any(tracker in meta.trackers for tracker in ["HDBITS", "PASSTHEPOPCORN"]) and piece_size > 16 * 1024 * 1024:
            piece_size = 16 * 1024 * 1024

        # Enforce minimum and maximum limits
        piece_size = max(min_size, min(piece_size, max_size))

        # Calculate number of pieces for debugging
        num_pieces = math.ceil(total_size / piece_size)
        logger.debug(f"Selected piece size: {piece_size / 1024:.2f} KiB")
        logger.debug(f"Number of pieces: {num_pieces}")

        return piece_size

    @staticmethod
    def build_mkbrr_exclude_string(root_folder: str, filelist: Sequence[str], allow_subs: bool = False) -> str:
        if allow_subs:
            manual_patterns = ["*.nfo", "*.jpg", "*.png", "*.txt", "*.xml"]
        else:
            manual_patterns = ["*.nfo", "*.jpg", "*.png", "*.srt", "*.sub", "*.vtt", "*.ssa", "*.ass", "*.txt", "*.xml"]
        keep_set = {str(Path(f).resolve()) for f in filelist}

        exclude_files: set[str] = set()
        for dirpath, _, filenames in os.walk(root_folder):
            for fname in filenames:
                full_path = str(Path(Path(dirpath) / fname).resolve())
                if full_path in keep_set:
                    continue
                if any(fnmatch.fnmatch(fname, pat) for pat in manual_patterns):
                    continue
                exclude_files.add(fname)

        return ",".join(sorted(exclude_files) + manual_patterns)

    @classmethod
    async def create_torrent(
        cls,
        meta: Meta,
        path: str | os.PathLike[str],
        output_filename: str,
        tracker_url: str | None = None,
        piece_size: int = 0,
    ) -> str | Torrent:
        # Ensure only one torrent creation runs at a time
        wait_started: float | None = None
        if cls._create_torrent_semaphore.locked():
            wait_started = time.time()
            logger.debug("[yellow]Waiting for create_torrent slot...[/yellow]")

        async with cls._create_torrent_semaphore:
            cls._create_torrent_inflight += 1
            if meta.debug:
                wait_msg = ""
                if wait_started is not None:
                    waited = time.time() - wait_started
                    wait_msg = f" (waited {waited:.2f}s)"
                logger.debug(f"[cyan]create_torrent start | in-flight={cls._create_torrent_inflight}{wait_msg}[/cyan]")

            try:
                if not piece_size:
                    piece_size = meta.max_piece_size
                tracker_url = tracker_url or None
                include: list[str] = []
                exclude: list[str] = []

                is_subs = "BASE_SUBS" in output_filename
                creation_filelist = list(meta.filelist)
                if is_subs and meta.subtitle_files:
                    creation_filelist.extend(meta.subtitle_files)

                # A single-file release must use its parent as the creation root
                # when external subtitles are requested; otherwise neither torf nor
                # mkbrr can discover sibling subtitle files.
                if is_subs and Path(path).is_file():
                    path = Path(path).parent

                if meta.category not in ("MOVIE", "TV"):
                    if meta.isdir and len(meta.filelist) == 1 and not meta.keep_folder:
                        path = meta.filelist[0]
                    include = []
                    exclude = []
                elif meta.keep_folder:
                    logger.info("--keep-folder was specified. Using complete folder for torrent creation.")
                    # specific nfo catch for certain trackers. BASE catch should prevent unintentional inclusion by default
                    if meta.keep_nfo and "BASE" not in output_filename:
                        logger.info("--keep-nfo was specified. Including NFO files in torrent.")
                        include = ["*.mkv", "*.mp4", "*.ts", "*.nfo"]
                        exclude = ["*.*", "*sample.mkv"]
                        meta.mkbrr = False
                    elif not meta.tv_pack:
                        folder_name = Path(str(path)).name
                        include = [f"{folder_name}/{Path(f).name}" for f in creation_filelist]
                        exclude = ["*", "*/**"]

                elif meta.isdir:
                    if meta.keep_nfo and not meta.is_disc and "BASE" not in output_filename:
                        logger.info("--keep-nfo was specified. Including NFO files in torrent.")
                        include = ["*.mkv", "*.mp4", "*.ts", "*.nfo"]
                        exclude = ["*.*", "*sample.mkv"]
                        meta.mkbrr = False
                    elif meta.is_disc:
                        include = []
                        exclude = []
                    elif not meta.tv_pack:
                        path_dir = os.fspath(path)
                        path_dir_path = Path(path_dir)
                        globs = [f.name for f in path_dir_path.glob("*.mkv")] + [f.name for f in path_dir_path.glob("*.mp4")] + [f.name for f in path_dir_path.glob("*.ts")]
                        no_sample_globs = [
                            str(Path(f"{path_dir}{os.sep}{file}").resolve()) for file in globs if not file.lower().endswith("sample.mkv") or "!sample" in file.lower()
                        ]
                        if len(no_sample_globs) == 1 and not is_subs:
                            path = meta.filelist[0]
                        exclude = ["*.*", "*sample.mkv", "!sample*.*"] if not meta.is_disc else []
                        include = ["*.mkv", "*.mp4", "*.ts"] if not meta.is_disc else []
                    else:
                        folder_name = Path(str(path)).name
                        include = [f"{folder_name}/{Path(f).name}" for f in creation_filelist]
                        exclude = ["*", "*/**"]
                elif is_subs:
                    folder_name = Path(path).name
                    include = [f"{folder_name}/{Path(file).name}" for file in creation_filelist]
                    exclude = ["*", "*/**"]
                else:
                    exclude = ["*.*", "*sample.mkv", "!sample*.*"] if not meta.is_disc else []
                    include = ["*.mkv", "*.mp4", "*.ts"] if not meta.is_disc else []

                # If using mkbrr, run the external application
                if meta.mkbrr:
                    try:
                        # Validate input path to prevent potential command injection
                        if not Path(path).exists():
                            raise ValueError(f"Path does not exist: {path}")
                        mkbrr_binary = cls.get_mkbrr_path(meta)
                        # Validate mkbrr binary exists and is executable
                        if not Path(mkbrr_binary).exists():
                            raise FileNotFoundError(f"mkbrr binary not found: {mkbrr_binary}")
                        output_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"{output_filename}.torrent"

                        # Ensure executable permission for non-Windows systems
                        if not sys.platform.startswith("win"):
                            with contextlib.suppress(Exception):
                                Path(mkbrr_binary).chmod(0o700)

                        cmd = [mkbrr_binary, "create", os.fspath(path)]

                        if tracker_url:
                            cmd.extend(["-t", tracker_url])

                        if meta.randomized >= 1:
                            cmd.extend(["-e"])

                        if piece_size and not tracker_url:
                            try:
                                max_size_bytes = piece_size * 1024 * 1024

                                # Calculate the appropriate power of 2 (log2)
                                # We want the largest power of 2 that's less than or equal to max_size_bytes
                                power = min(27, max(16, math.floor(math.log2(max_size_bytes))))

                                cmd.extend(["-l", str(power)])
                                logger.info(f"[yellow]Setting mkbrr piece length to 2^{power} ({(2**power) / (1024 * 1024):.2f} MiB)")
                            except ValueError, TypeError:
                                logger.warning("[yellow]Warning: Invalid max_piece_size value, using default piece length")

                        if not piece_size and not tracker_url and not any(tracker in meta.trackers for tracker in ["HDBITS", "PASSTHEPOPCORN"]):
                            cmd.extend(["-m", "27"])

                        if meta.mkbrr_threads != "0":
                            cmd.extend(["--workers", str(meta.mkbrr_threads)])

                        if not meta.is_disc and meta.category in ("MOVIE", "TV"):
                            exclude_str = cls.build_mkbrr_exclude_string(str(path), creation_filelist, allow_subs=is_subs)
                            cmd.extend(["--exclude", exclude_str])

                        cmd.extend(["-o", str(output_path)])
                        logger.debug(f"[cyan]mkbrr cmd: {cmd}")

                        # Run mkbrr subprocess in thread to avoid blocking
                        def run_mkbrr() -> int:
                            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)  # noqa: S603

                            if process.stdout is None:
                                return process.wait()

                            total_pieces = 100  # Default to 100% for scaling progress
                            pieces_done = 0
                            mkbrr_start_time = time.time()

                            with progress_display(
                                TextColumn("[progress.description]{task.description}"),
                                BarColumn(),
                                TaskProgressColumn(),
                                console=console,
                                transient=False,
                                disable=has_progress_callback(),
                            ) as progress:
                                task = progress.add_task("mkbrr hashing...", total=total_pieces)
                                publish_progress("mkbrr-hash", "mkbrr hashing...", current=0, total=total_pieces, detail="Starting mkbrr hashing")

                                for line in process.stdout:
                                    line = line.strip()

                                    # Detect hashing progress, speed, and percentage
                                    match = re.search(r"Hashing pieces.*?\[(\d+(?:\.\d+)? (?:G|M)(?:B|iB)/s)\]\s+(\d+)%", line)
                                    if match:
                                        speed = match.group(1)  # Extract speed (e.g., "1.7 GiB/s")
                                        pieces_done = int(match.group(2))  # Extract percentage (e.g., "14")

                                        # Try to extract the ETA directly if it's in the format [elapsed:remaining]
                                        eta_match = re.search(r"\[(\d+)s:(\d+)s\]", line)
                                        if eta_match:
                                            eta_seconds = int(eta_match.group(2))
                                            eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
                                        else:
                                            # Fallback to calculating ETA if not directly available
                                            elapsed_time = time.time() - mkbrr_start_time
                                            if pieces_done > 0:
                                                estimated_total_time = elapsed_time / (pieces_done / 100)
                                                eta_seconds = int(max(0.0, estimated_total_time - elapsed_time))
                                                eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
                                            else:
                                                eta = "--:--"  # Placeholder if we can't estimate yet

                                        progress.update(task, description=f"mkbrr hashing... {speed} | ETA: {eta}", completed=pieces_done)
                                        publish_progress(
                                            "mkbrr-hash",
                                            "mkbrr hashing...",
                                            current=pieces_done,
                                            total=total_pieces,
                                            detail=f"{speed} | ETA: {eta}",
                                        )

                                    # Detect final output line
                                    if "Wrote" in line and ".torrent" in line and meta.debug:
                                        logger.info(f"[bold cyan]{line}")  # Print the final torrent file creation message

                                result = process.wait()
                                if result == 0 and Path(output_path).exists():
                                    progress.update(task, completed=total_pieces)
                                    complete_progress("mkbrr-hash", "mkbrr hashing...", current=total_pieces, total=total_pieces)
                                else:
                                    failure_detail = f"Expected torrent file {output_path} was not created" if result == 0 else f"mkbrr exited with status code {result}"
                                    publish_progress(
                                        "mkbrr-hash",
                                        "mkbrr hashing...",
                                        current=pieces_done,
                                        total=total_pieces,
                                        detail=failure_detail,
                                        status="failed",
                                    )
                                return result

                        result = await asyncio.to_thread(run_mkbrr)

                        # Verify the torrent was actually created
                        if result != 0:
                            logger.info(f"[bold red]mkbrr exited with non-zero status code: {result}")
                            raise RuntimeError(f"mkbrr exited with status code {result}")

                        if not Path(output_path).exists():
                            logger.info("[bold red]mkbrr did not create a torrent file!")
                            raise FileNotFoundError(f"Expected torrent file {output_path} was not created")
                        return output_path

                    except subprocess.CalledProcessError as e:
                        logger.info(f"[bold red]Error creating torrent with mkbrr: {e}")
                        logger.info("[yellow]Falling back to CustomTorrent method")
                        meta.mkbrr = False
                    except Exception as e:
                        logger.info(f"[bold red]Error using mkbrr: {e!s}")
                        logger.info("[yellow]Falling back to CustomTorrent method")
                        meta.mkbrr = False
                overall_start_time = time.time()

                # Calculate initial size
                def calculate_size() -> int:
                    size = 0
                    if Path(path).is_file():
                        size = Path(path).stat().st_size
                    elif Path(path).is_dir():
                        for root, _dirs, files in os.walk(path):
                            size += sum((Path(root) / f).stat().st_size for f in files if (Path(root) / f).is_file())
                    return size

                initial_size = await asyncio.to_thread(calculate_size)

                piece_size = cls.calculate_piece_size(initial_size, 32768, 134217728, meta, piece_size=piece_size)

                # Fallback to CustomTorrent if mkbrr is not used
                custom_include = include or []
                if is_subs and not meta.is_disc and meta.category in ("TV", "MOVIE"):
                    # Preserve the existing video include rules and add only the
                    # subtitle files selected for this upload, never every subtitle
                    # matching an extension below the creation root.
                    root = Path(path).resolve()
                    selected_subtitles: list[str] = []
                    for subtitle_file in meta.subtitle_files:
                        try:
                            selected_subtitles.append(Path(str(subtitle_file)).resolve().relative_to(root).as_posix())
                        except ValueError:
                            logger.warning(f"[yellow]Selected subtitle is outside torrent root and will be skipped: {subtitle_file}")
                    custom_include = list(dict.fromkeys([*custom_include, *selected_subtitles]))
                torrent = CustomTorrent(
                    meta=meta,
                    path=path,
                    trackers=["https://fake.tracker"],
                    source="UA",
                    private=True,
                    exclude_globs=exclude or [],
                    include_globs=custom_include,
                    creation_date=datetime.now(UTC),
                    comment=f"{meta.ua_name} (fork)",
                    created_by=f"{meta.ua_name} (fork)",
                    piece_size=piece_size,
                )
                progress_id = f"torrent-hash-{meta.uuid}"
                progress_label = f"Hashing {output_filename} torrent"
                torrent._webui_progress_id = progress_id
                torrent._webui_progress_label = progress_label
                publish_progress(progress_id, progress_label, current=0, total=1, detail="Starting torrent hash", group="media", unit="pieces")

                # Run torrent generation in thread to avoid blocking the event loop
                def generate_torrent() -> None:
                    torrent.generate(callback=cls.torf_cb, interval=5)
                    torrent.write(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{output_filename}.torrent", overwrite=True)
                    torrent.verify_filesize(path)

                try:
                    await asyncio.to_thread(generate_torrent)
                except Exception as error:
                    publish_progress(progress_id, progress_label, detail=str(error), status="failed", group="media", unit="pieces")
                    raise

                total_elapsed_time = time.time() - overall_start_time
                formatted_time = time.strftime("%H:%M:%S", time.gmtime(total_elapsed_time))

                torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{output_filename}.torrent"
                torrent_file_size = Path(torrent_file_path).stat().st_size / 1024
                logger.debug("")
                logger.debug(f"[bold green]torrent created in {formatted_time}")
                logger.debug(f"[green]Torrent file size: {torrent_file_size:.2f} KB")
                complete_progress(progress_id, progress_label, current=1, total=1, detail="Torrent created", group="media", unit="pieces")
                return torrent
            finally:
                cls._create_torrent_inflight -= 1
                logger.debug(f"[cyan]create_torrent end | in-flight={cls._create_torrent_inflight}[/cyan]")

    @staticmethod
    def torf_cb(torrent: Torrent, _filepath: str, pieces_done: int, pieces_total: int) -> None:
        if pieces_done == 0:
            TorrentCreator._torf_start_time = time.time()  # Reset start time when hashing starts

        elapsed_time = time.time() - TorrentCreator._torf_start_time

        # Calculate percentage done
        percentage_done = (pieces_done / pieces_total) * 100 if pieces_total > 0 else 0.0

        # Estimate ETA (if at least one piece is done)
        if pieces_done > 0 and pieces_total > 0:
            estimated_total_time = elapsed_time / (pieces_done / pieces_total)
            eta_seconds = max(0.0, estimated_total_time - elapsed_time)
            eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
        else:
            eta = "--:--"

        # Calculate hashing speed (MB/s)
        if elapsed_time > 0 and pieces_done > 0:
            piece_size_bytes = torrent.piece_size or 0
            piece_size = piece_size_bytes / (1024 * 1024)
            speed = (pieces_done * piece_size) / elapsed_time
            speed_str = f"{speed:.2f} MB/s"
        else:
            speed_str = "-- MB/s"

        # Display progress with percentage, speed, and ETA
        if not has_progress_callback() and not is_cli_progress_suppressed():
            cli_ui.info_progress(f"Hashing... {speed_str} | ETA: {eta}", int(percentage_done), 100)
        progress_id = getattr(torrent, "_webui_progress_id", "torrent-hash")
        progress_label = getattr(torrent, "_webui_progress_label", "Hashing torrent")
        publish_progress(
            progress_id,
            progress_label,
            current=pieces_done,
            total=pieces_total or 1,
            detail=f"{speed_str} | ETA: {eta}",
            group="media",
            unit="pieces",
        )

    @staticmethod
    def create_random_torrents(base_dir: str, uuid: str, num: int | str, path: str) -> None:
        manual_name = re.sub(r"[^0-9a-zA-Z\[\]\'\-]+", ".", Path(path).name)
        base_torrent = Torrent.read(f"{base_dir}{'/' + 'tmp' + '/'}{uuid}/BASE.torrent")
        for i in range(1, int(num) + 1):
            new_torrent = base_torrent
            new_torrent.metainfo["info"]["entropy"] = random.randint(1, 999999)  # type: ignore  # nosec B311  # noqa: S311
            Torrent.copy(new_torrent).write(f"{base_dir}{'/' + 'tmp' + '/'}{uuid}/[RAND-{i}]{manual_name}.torrent", overwrite=True)

    @staticmethod
    async def create_base_from_existing_torrent(torrentpath: str, base_dir: str, uuid: str) -> str | None:
        if Path(torrentpath).exists():
            base_torrent = Torrent.read(torrentpath)
            base_torrent.trackers = ["https://fake.tracker"]
            base_torrent.comment = "Upload-Assistant (fork)"
            base_torrent.created_by = "Upload-Assistant (fork)"
            info_dict = base_torrent.metainfo["info"]
            valid_keys = ["name", "piece length", "pieces", "private", "source"]

            # Add the correct key based on single vs multi file torrent
            if "files" in info_dict:
                valid_keys.append("files")
            elif "length" in info_dict:
                valid_keys.append("length")

            # Remove everything not in the whitelist
            for each in list(info_dict):
                if each not in valid_keys:
                    info_dict.pop(each, None)  # type: ignore
            for each in list(base_torrent.metainfo):
                if each not in (
                    "announce",
                    "comment",
                    "creation date",
                    "created by",
                    "encoding",
                    "info",
                    "imdb",
                    "tmdb",
                    "tvdb",
                    "tvmaze",
                    "mal",
                    "douban",
                    "igdb",
                    "asin",
                    "isbn",
                ):
                    base_torrent.metainfo.pop(each, None)  # type: ignore
            base_torrent.source = "L4G"
            base_torrent.private = True
            has_subs = any(Path(str(f)).suffix.lower() in SUBTITLE_EXTENSIONS for f in base_torrent.files)
            out_name = "BASE_SUBS.torrent" if has_subs else "BASE.torrent"
            output_path = Path(base_dir) / "tmp" / uuid / out_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Torrent.copy(base_torrent).write(output_path, overwrite=True)
            return str(output_path)
        return None

    @staticmethod
    def get_mkbrr_path(meta: Meta) -> str:
        """Determine the correct mkbrr binary based on OS and architecture."""
        existing_binary = MkbrrBinaryManager.find_existing_binary(meta.base_dir)
        if existing_binary:
            return existing_binary

        base_dir = Path(meta.base_dir) / "bin" / "mkbrr"

        # Detect OS & Architecture
        system = platform.system().lower()
        arch = platform.machine().lower()

        if system == "windows":
            if arch in {"x86_64", "amd64", "arm64", "aarch64"}:
                # Windows ARM currently uses the x86_64 mkbrr build via Windows emulation.
                binary_path = Path(base_dir) / "windows" / "x86_64" / "mkbrr.exe"
            else:
                raise Exception("Unsupported Windows architecture")
        elif system == "darwin":
            binary_path = Path(base_dir) / "macos" / "arm64" / "mkbrr" if "arm" in arch else Path(base_dir) / "macos" / "x86_64" / "mkbrr"
        elif system == "linux":
            if "x86_64" in arch:
                binary_path = Path(base_dir) / "linux" / "amd64" / "mkbrr"
            elif "armv6" in arch:
                binary_path = Path(base_dir) / "linux" / "armv6" / "mkbrr"
            elif "arm" in arch:
                binary_path = Path(base_dir) / "linux" / "arm" / "mkbrr"
            elif "aarch64" in arch or "arm64" in arch:
                binary_path = Path(base_dir) / "linux" / "arm64" / "mkbrr"
            else:
                raise Exception("Unsupported Linux architecture")
        else:
            raise Exception("Unsupported OS")

        if not Path(binary_path).exists():
            raise FileNotFoundError(f"mkbrr binary not found: {binary_path}")

        return str(binary_path)


def build_mkbrr_exclude_string(root_folder: str, filelist: Sequence[str], allow_subs: bool = False) -> str:
    return TorrentCreator.build_mkbrr_exclude_string(root_folder, filelist, allow_subs)


async def create_torrent(
    meta: Meta,
    path: str | os.PathLike[str],
    output_filename: str,
    tracker_url: str | None = None,
    piece_size: int = 0,
) -> str | Torrent:
    return await TorrentCreator.create_torrent(
        meta=meta,
        path=path,
        output_filename=output_filename,
        tracker_url=tracker_url,
        piece_size=piece_size,
    )


def torf_cb(torrent: Torrent, filepath: str, pieces_done: int, pieces_total: int) -> None:
    TorrentCreator.torf_cb(torrent, filepath, pieces_done, pieces_total)


def create_random_torrents(base_dir: str, uuid: str, num: int | str, path: str) -> None:
    TorrentCreator.create_random_torrents(base_dir, uuid, num, path)


async def create_base_from_existing_torrent(torrentpath: str, base_dir: str, uuid: str) -> str | None:
    return await TorrentCreator.create_base_from_existing_torrent(torrentpath, base_dir, uuid)


def get_mkbrr_path(meta: Meta) -> str:
    return TorrentCreator.get_mkbrr_path(meta)
