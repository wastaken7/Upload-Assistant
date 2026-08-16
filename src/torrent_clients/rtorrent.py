# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import errno
import os
import platform
import shutil
import ssl
import time
import traceback
import xmlrpc.client  # nosec B411 - Secured with defusedxml.xmlrpc.monkey_patch() below
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import bencode
import defusedxml.xmlrpc
from torf import Torrent

from src.cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.torrent_clients.path_utils import coerce_str_list, is_path_under, map_save_path, tracker_directory
from src.torrentcreate import TorrentCreator

# Secure XML-RPC client using defusedxml to prevent XML attacks
defusedxml.xmlrpc.monkey_patch()


bencode_any = cast(Any, bencode)
_bencode_bread = cast(Callable[[str], dict[str, Any]], bencode_any.bread)
_bencode_bencode = cast(Callable[[Any], bytes], bencode_any.bencode)
_bencode_bwrite = cast(Callable[[Any, str], None], bencode_any.bwrite)


class RtorrentClientMixin:
    config: dict[str, Any]

    async def is_valid_torrent(self, meta: Meta, torrent_path: str, torrenthash: str, torrent_client: str, client: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    def _extract_tracker_ids_from_comment(self, comment: str) -> dict[str, Any]:
        raise NotImplementedError

    def rtorrent(self, path: str, torrent_path: str, torrent: Torrent, meta: Meta, local_path: str, remote_path: str, client: dict[str, Any], tracker: str) -> None:
        # Get the appropriate source path (same as in qbittorrent method)
        tracker_dir: str | None = None
        dst = path
        filelist = coerce_str_list(meta.filelist)
        src = filelist[0] if len(filelist) == 1 and Path(filelist[0]).is_file() and not meta.keep_folder else meta.path

        if not src:
            error_msg = "[red]No source path found in meta."
            logger.info(f"[bold red]{error_msg}")
            raise ValueError(error_msg)

        # Determine linking method
        linking_method = client.get("linking")  # "symlink", "hardlink", or None
        logger.debug(f"Linking method: {linking_method}")
        use_symlink = linking_method == "symlink"
        use_hardlink = linking_method == "hardlink"

        # Process linking if enabled
        if use_symlink or use_hardlink:
            # Get linked folder for this drive
            linked_folder = coerce_str_list(client.get("linked_folder", []))
            logger.debug(f"Linked folders: {linked_folder}")

            # Determine drive letter (Windows) or root (Linux)
            if platform.system() == "Windows":
                src_drive = os.path.splitdrive(src)[0]
            else:
                # On Unix/Linux, use the root directory or first directory component
                src_drive = "/"
                # Extract the first directory component for more specific matching
                src_parts = src.strip("/").split("/")
                if src_parts:
                    src_root_dir = "/" + src_parts[0]
                    # Check if any linked folder contains this root
                    for folder in linked_folder:
                        if src_root_dir in folder or folder in src_root_dir:
                            src_drive = src_root_dir
                            break

            # Find a linked folder that matches the drive
            link_target = None
            if platform.system() == "Windows":
                # Windows matching based on drive letters
                for folder in linked_folder:
                    folder_drive = os.path.splitdrive(folder)[0]
                    if folder_drive == src_drive:
                        link_target = folder
                        break
            else:
                # Unix/Linux matching based on path containment
                for folder in linked_folder:
                    # Check if source path is in the linked folder or vice versa
                    if src.startswith(folder) or folder.startswith(src) or folder.startswith(src_drive):
                        link_target = folder
                        break

            logger.debug(f"Source drive: {src_drive}")
            logger.debug(f"Link target: {link_target}")

            # If using symlinks and no matching drive folder, allow any available one
            if use_symlink and not link_target and linked_folder:
                link_target = linked_folder[0]

            if (use_symlink or use_hardlink) and not link_target:
                error_msg = f"No suitable linked folder found for drive {src_drive}"
                logger.info(f"[bold red]{error_msg}")
                raise ValueError(error_msg)

            # Create tracker-specific directory inside linked folder
            if use_symlink or use_hardlink:
                # allow overridden folder name with link_dir_name config var
                tracker_cfg = cast(dict[str, Any], self.config.get("TRACKERS", {})).get(tracker.upper(), {})
                link_dir_name = str(tracker_cfg.get("link_dir_name", "")).strip()
                if link_target is None:
                    raise RuntimeError("link_target cannot be None")
                tracker_dir = tracker_directory(link_target, link_dir_name, tracker)
                Path(tracker_dir).mkdir(parents=True, exist_ok=True)

                logger.debug(f"[bold yellow]Linking to tracker directory: {tracker_dir}")
                logger.debug(f"[cyan]Source path: {src}")

                # Extract only the folder or file name from `src`
                src_name = Path(src.rstrip(os.sep)).name  # Ensure we get just the name
                dst = Path(tracker_dir) / src_name  # Destination inside linked folder

                # path magic
                if Path(dst).exists() or Path(dst).is_symlink():
                    logger.debug(f"[yellow]Skipping linking, path already exists: {dst}")
                else:
                    if use_hardlink:
                        try:
                            # Check if we're linking a file or directory
                            if Path(src).is_file():
                                # For a single file, create a hardlink directly
                                try:
                                    os.link(src, dst)
                                    logger.debug(f"[green]Hard link created: {dst} -> {src}")
                                except OSError as e:
                                    # If hardlink fails, try to copy the file instead
                                    logger.info(f"[yellow]Hard link failed: {e}")
                                    logger.info(f"[yellow]Falling back to file copy for: {src}")
                                    shutil.copy2(src, dst)  # copy2 preserves metadata
                                    logger.info(f"[green]File copied instead: {dst}")
                            else:
                                # For directories, we need to link each file inside
                                Path(dst).mkdir(parents=True, exist_ok=True)

                                for root, _, files in os.walk(src):
                                    # Get the relative path from source
                                    rel_path = os.path.relpath(root, src)

                                    dst_dir = dst

                                    # Create corresponding directory in destination
                                    if rel_path != ".":
                                        dst_dir = Path(dst) / rel_path
                                        Path(dst_dir).mkdir(parents=True, exist_ok=True)

                                    # Create hardlinks for each file
                                    for idx, file in enumerate(files):
                                        src_file = Path(root) / file
                                        dst_file = Path(dst if rel_path == "." else dst_dir) / file
                                        try:
                                            os.link(src_file, dst_file)
                                            if meta.debug and idx == 0:
                                                logger.info(f"[green]Hard link created for file: {dst_file} -> {src_file}")
                                        except OSError as e:
                                            # If hardlink fails, copy file instead
                                            logger.info(f"[yellow]Hard link failed for file {file}: {e}")
                                            shutil.copy2(src_file, dst_file)  # copy2 preserves metadata
                                            logger.info(f"[yellow]File copied instead: {dst_file}")

                                logger.debug(f"[green]Directory structure and files processed: {dst}")
                        except OSError as e:
                            error_msg = f"Failed to create link: {e}"
                            logger.info(f"[bold red]{error_msg}")
                            if meta.debug:
                                logger.debug(f"[yellow]Source: {src} (exists: {Path(src).exists()})")
                                logger.debug(f"[yellow]Destination: {dst}")
                            # Don't raise exception - just warn and continue
                            logger.info("[yellow]Continuing with rTorrent addition despite linking failure")

                    elif use_symlink:
                        try:
                            if platform.system() == "Windows":
                                Path(dst).symlink_to(src, target_is_directory=Path(src).is_dir())
                            else:
                                Path(dst).symlink_to(src)

                            logger.debug(f"[green]Symbolic link created: {dst} -> {src}")

                        except OSError as e:
                            error_msg = f"Failed to create symlink: {e}"
                            logger.info(f"[bold red]{error_msg}")
                            # Don't raise exception - just warn and continue
                            logger.info("[yellow]Continuing with rTorrent addition despite linking failure")

                # Use the linked path for rTorrent if linking was successful
                if (use_symlink or use_hardlink) and Path(dst).exists():
                    path = str(dst)

        # Apply remote pathing to `tracker_dir` before assigning `save_path`
        if use_symlink or use_hardlink:
            if tracker_dir is None:
                raise ValueError("Linking enabled but tracker_dir was not set")
            save_path = str(tracker_dir)  # Default to linked directory
        else:
            save_path = str(path)  # Default to the original path

        save_path = map_save_path(save_path, local_path, remote_path)

        logger.debug(f"[cyan]Original path: {path}")
        logger.debug(f"[cyan]Mapped save path: {save_path}")

        rtorrent = xmlrpc.client.Server(client["rtorrent_url"], context=ssl.create_default_context())
        metainfo = _bencode_bread(torrent_path)
        logger.debug(f"rtorrent: {Redaction.redact_private_info(str(rtorrent))}", extra={"markup": False})
        logger.debug(f"metainfo: {Redaction.redact_private_info(str(metainfo))}", extra={"markup": False})

        original_meta_bytes = _bencode_bencode(metainfo)
        try:
            # Use dst path if linking was successful, otherwise use original path
            resume_path = dst if (use_symlink or use_hardlink) and Path(dst).exists() else path
            logger.debug(f"[cyan]Using resume path: {resume_path}")
            fast_resume = self.add_fast_resume(metainfo, resume_path, torrent)
        except OSError as exc:
            logger.error(f"[red]Error making fast-resume data ({exc})")
            raise

        fr_file = torrent_path
        new_meta = _bencode_bencode(fast_resume)
        if new_meta != original_meta_bytes:
            fr_file = torrent_path.replace(".torrent", "-resume.torrent")
            logger.debug(f"Creating fast resume file: {fr_file}")
            _bencode_bwrite(fast_resume, fr_file)

        # Use dst path if linking was successful, otherwise use original path
        path = dst if (use_symlink or use_hardlink) and Path(dst).exists() else path

        isdir = Path(path).is_dir()
        # Remote path mount
        modified_fr = False
        path_dir = ""
        path = str(path)
        if is_path_under(path, local_path) and os.path.normcase(local_path) != os.path.normcase(remote_path):
            path_dir = str(Path(path).parent)
            path = map_save_path(path, local_path, remote_path, trailing_slash=False)
            shutil.copy(fr_file, f"{path_dir}/fr.torrent")
            fr_file = f"{Path(path).parent.as_posix()}/fr.torrent"
            modified_fr = True
            logger.debug(f"[cyan]Modified fast resume file path because path mapping: {fr_file}")
        if (meta.category in ("BOOK", "GAME") and len(filelist) > 1 and isdir) or isdir is False:
            path = Path(path).parent.as_posix()
        logger.debug(f"[cyan]Final path for rTorrent: {path}")

        logger.info("[bold yellow]Adding and starting torrent")
        rtorrent.load.start_verbose("", fr_file, f"d.directory_base.set={path}")
        logger.debug(f"[green]rTorrent load start for {fr_file} with d.directory_base.set={path}")
        time.sleep(1)
        # Add labels
        if client.get("rtorrent_label") is not None:
            logger.debug(f"[cyan]Setting rTorrent label: {client['rtorrent_label']}")
            rtorrent.d.custom1.set(torrent.infohash, client["rtorrent_label"])
        if meta.rtorrent_label is not None:
            rtorrent.d.custom1.set(torrent.infohash, meta.rtorrent_label)
            logger.debug(f"[cyan]Setting rTorrent label from meta: {meta.rtorrent_label}")

        # Delete modified fr_file location
        if modified_fr:
            logger.debug(f"[cyan]Removing modified fast resume file: {fr_file}")
            try:
                Path(f"{path_dir}/fr.torrent").unlink()
            except OSError as e:
                logger.debug(f"[yellow]Warning: Could not remove modified fast resume file: {e}[/yellow]")
        logger.debug(f"[cyan]Path: {path}")
        return

    def add_fast_resume(self, metainfo: dict[str, Any], datapath: str, _torrent: Torrent) -> dict[str, Any]:
        """Add fast resume data to a metafile dict."""
        # Get list of files
        files = metainfo["info"].get("files", None)
        single = files is None
        if single:
            if Path(datapath).is_dir():
                datapath = Path(datapath) / metainfo["info"]["name"]
            files = [
                {
                    "path": [str(Path(datapath).resolve())],
                    "length": metainfo["info"]["length"],
                }
            ]

        # Prepare resume data
        resume = metainfo.setdefault("libtorrent_resume", {})
        resume["bitfield"] = len(metainfo["info"]["pieces"]) // 20
        resume["files"] = []
        piece_length_value = metainfo["info"]["piece length"]
        piece_length = int(piece_length_value) if isinstance(piece_length_value, (int, float, str)) else 0
        if piece_length <= 0:
            raise ValueError(f"Invalid piece length: {piece_length_value!r}")
        offset = 0

        for fileinfo in files:
            # Get the path into the filesystem
            filepath = str(Path(*fileinfo["path"]))
            if not single:
                filepath = Path(datapath) / filepath.strip(os.sep)

            # Check file size
            file_length_value = fileinfo["length"]
            file_length = int(file_length_value) if isinstance(file_length_value, (int, float, str)) else 0
            if Path(filepath).stat().st_size != file_length:
                raise OSError(
                    errno.EINVAL,
                    f"File size mismatch for {filepath!r} [is {Path(filepath).stat().st_size}, expected {file_length}]",
                )

            # Add resume data for this file
            resume["files"].append(
                {
                    "priority": 1,
                    "mtime": int(Path(filepath).stat().st_mtime),
                    "completed": ((offset + file_length + piece_length - 1) // piece_length - offset // piece_length),
                }
            )
            offset += file_length

        return metainfo

    async def get_ptp_from_hash_rtorrent(self, meta: Meta, pathed: bool = False, client: dict[str, Any] | None = None) -> Meta:
        default_cfg = cast(dict[str, Any], self.config.get("DEFAULT", {}))
        default_client_value = default_cfg.get("default_torrent_client")
        if client is None:
            if not isinstance(default_client_value, str) or not default_client_value:
                logger.info("[yellow]Missing default torrent client for rTorrent")
                return meta
            clients_cfg = cast(dict[str, Any], self.config.get("TORRENT_CLIENTS", {}))
            client = cast(dict[str, Any], clients_cfg.get(default_client_value, {}))
        torrent_storage_dir_value = client.get("torrent_storage_dir")
        torrent_storage_dir = torrent_storage_dir_value if isinstance(torrent_storage_dir_value, str) else None
        info_hash_value = meta.infohash
        info_hash_v1 = info_hash_value if isinstance(info_hash_value, str) else None

        if not torrent_storage_dir or not info_hash_v1 or not meta.path:
            logger.info("[yellow]Missing torrent storage directory, infohash, or meta path")
            return meta

        # Normalize info hash format for rTorrent (uppercase)
        info_hash_v1 = info_hash_v1.upper().strip()
        torrent_path = Path(torrent_storage_dir) / f"{info_hash_v1}.torrent"

        # Extract folder ID for use in temporary file path
        folder_id = Path(meta.path).name
        if not meta.uuid:
            meta.uuid = folder_id

        extracted_torrent_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        Path(extracted_torrent_dir).mkdir(parents=True, exist_ok=True)

        # Check if the torrent file exists directly
        if Path(torrent_path).exists():
            logger.info(f"[green]Found matching torrent file: {torrent_path}")
        else:
            # Try to find the torrent file in storage directory (case insensitive)
            found = False
            logger.info(f"[yellow]Searching for torrent file with hash {info_hash_v1} in {torrent_storage_dir}")

            if Path(torrent_storage_dir).exists():
                for filename in (p.name for p in Path(torrent_storage_dir).iterdir()):
                    filename_str = filename
                    if filename_str.lower().endswith(".torrent"):
                        file_hash = Path(filename_str).stem  # Remove .torrent extension
                        if file_hash.upper() == info_hash_v1:
                            torrent_path = Path(torrent_storage_dir) / filename_str
                            found = True
                            logger.info(f"[green]Found torrent file with matching hash: {filename_str}")
                            break

            if not found:
                logger.info(f"[bold red]No torrent file found for hash: {info_hash_v1}")
                return meta

        # Parse the torrent file to get the comment
        try:
            torrent = Torrent.read(torrent_path)
            comment = torrent.comment or ""

            # Try to find tracker IDs in the comment
            logger.debug(f"[cyan]Torrent comment: {comment}")

            torrent_comments_value = meta.torrent_comments
            torrent_comments_list = torrent_comments_value if isinstance(torrent_comments_value, list) else []
            torrent_comments = [cast(dict[str, Any], entry) for entry in torrent_comments_list if isinstance(entry, dict)]
            meta.torrent_comments = torrent_comments

            comment_data = {
                "hash": getattr(torrent, "infohash_v1", "") or "",
                "name": getattr(torrent, "name", "") or "",
                "comment": comment,
            }
            torrent_comments.append(comment_data)

            logger.debug(f"[cyan]Stored comment for torrent: {comment[:100]}...")

            # Handle various tracker URL formats in the comment
            tracker_ids = self._extract_tracker_ids_from_comment(comment)
            meta.set_tracker_ids(tracker_ids)

            # If we found a tracker ID, log it
            for tracker_name, torrent_id in tracker_ids.items():
                logger.info(f"[bold cyan]meta updated with {tracker_name.upper()} ID: {torrent_id}")

            if torrent_comments and meta.debug:
                logger.info(f"[green]Stored {len(torrent_comments)} torrent comments for later use")

            if not pathed:
                valid, resolved_path = await self.is_valid_torrent(meta, torrent_path, info_hash_v1, "rtorrent", client)

                if valid:
                    base_torrent_path = Path(extracted_torrent_dir) / "BASE.torrent"

                    try:
                        await TorrentCreator.create_base_from_existing_torrent(resolved_path, meta.base_dir, meta.uuid)
                        logger.debug("[green]Created BASE.torrent from existing torrent")
                    except Exception as e:
                        logger.info(f"[bold red]Error creating BASE.torrent: {e}")
                        try:
                            shutil.copy2(resolved_path, base_torrent_path)
                            logger.info(f"[yellow]Created simple torrent copy as fallback: {base_torrent_path}")
                        except Exception as copy_err:
                            logger.info(f"[bold red]Failed to create backup copy: {copy_err}")

        except Exception as e:
            logger.info(f"[bold red]Error reading torrent file: {e}")
            logger.info(f"[dim]{traceback.format_exc()}[/dim]")
        return meta
