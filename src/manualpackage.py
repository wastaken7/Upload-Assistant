# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
import shutil
import tarfile
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx
from torf import Torrent

from src.console import logger
from src.meta import Meta
from src.temp_paths import artwork_dir
from src.torrent_manifest import TorrentManifest
from src.uploadscreens import UploadScreensManager


def _is_shareable(relative: Path, shareable_torrents: set[str]) -> bool:
    """Whether a release-folder entry may leave this machine in a manual package.

    Tracker torrents (``[TRACKER].torrent``) and the client's exported torrents
    (``torrents/.client``) hold passkeys in their announce URLs, and archives
    from earlier runs may still contain them. They stay in the release folder
    for the client and manual use, but are never shared.
    """
    if ".client" in relative.parts:
        return False
    if len(relative.parts) == 1:
        # Match the name, not Path.suffix: an archive for a title with no
        # ASCII characters is named ".tar", which has no suffix.
        name = relative.name.casefold()
        if name.endswith(".tar"):
            return False
        if name.endswith(".torrent") and not relative.name.startswith(("BASE", "[RAND")) and relative.name not in shareable_torrents:
            return False
    return True


def _write_archive(archive_path: str, release_dir: Path, shareable_torrents: set[str]) -> None:
    """Archive the shareable files of the release folder."""

    def keep(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
        return member if _is_shareable(Path(member.name), shareable_torrents) else None

    with tarfile.open(archive_path, "w") as tar:
        tar.add(release_dir, arcname=".", filter=keep)


def _stage_share(share_dir: Path, release_dir: Path, shareable_torrents: set[str], archive_path: str) -> None:
    """Copy the shareable files and the archive to the folder a Filebrowser link opens."""
    shutil.rmtree(share_dir, ignore_errors=True)
    for source in release_dir.rglob("*"):
        relative = source.relative_to(release_dir)
        if source.is_file() and _is_shareable(relative, shareable_torrents):
            target = share_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    share_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive_path, share_dir / Path(archive_path).name)


class ManualPackageManager:
    def __init__(self, config: Mapping[str, Any]) -> None:
        default_config = cast(Mapping[str, Any], config.get("DEFAULT", {}))
        if not isinstance(default_config, dict):
            raise ValueError("'DEFAULT' config section must be a dict")
        tracker_config = cast(Mapping[str, Any], config.get("TRACKERS", {}))
        if not isinstance(tracker_config, dict):
            raise ValueError("'TRACKERS' config section must be a dict")
        self.default_config = default_config
        self.tracker_config = tracker_config
        self.uploadscreens_manager = UploadScreensManager(cast(dict[str, Any], config))

    async def package(self, meta: Meta) -> str | bool:
        tag = "" if not meta.tag or meta.tag == "" else f" / {meta.tag[1:]}"
        res = meta.source if meta.is_disc == "DVD" else meta.resolution

        generic_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/GENERIC_INFO.txt"
        async with aiofiles.open(generic_path, "w", encoding="utf-8") as generic:
            await generic.write(f"Name: {meta.name}\n\n")
            await generic.write(f"Overview: {meta.overview}\n\n")
            await generic.write(f"{res} / {meta.type}{tag}\n\n")
            await generic.write(f"Category: {meta.category}\n")
            if meta.tmdb:
                await generic.write(f"TMDB: https://www.themoviedb.org/{meta.category.lower()}/{meta.tmdb}\n")
            if meta.imdb_tt:
                await generic.write(f"IMDb: https://www.imdb.com/title/{meta.imdb_tt}\n")
            if meta.tvdb_id != 0:
                await generic.write(f"TVDB: https://www.thetvdb.com/?id={meta.tvdb_id}&tab=series\n")
            if "tvmaze_id" in meta and meta.tvmaze_id != 0:
                await generic.write(f"TVMaze: https://www.tvmaze.com/shows/{meta.tvmaze_id}\n")
            configured_poster = Path(str(meta.artwork_path or ""))
            poster_img = str(configured_poster if configured_poster.is_file() else artwork_dir(meta.base_dir, meta.uuid) / "POSTER.png")
            if meta.artwork_url not in ["", None] and not Path(poster_img).exists():
                if meta.rehosted_artwork_url is None:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(meta.artwork_url)
                    if response.status_code == 200:
                        logger.info("[bold yellow]Rehosting Cover")
                        await asyncio.to_thread(Path(poster_img).write_bytes, response.content)
                        if not meta.skip_imghost_upload:
                            poster, _ = await self.uploadscreens_manager.upload_screens(meta, 1, 1, 0, 1, [poster_img], {})
                            poster = poster[0]
                            await generic.write(f"TMDB Cover: {poster.get('raw_url', poster.get('img_url'))}\n")
                            meta.rehosted_artwork_url = poster.get("raw_url", poster.get("img_url"))
                        meta_text = json.dumps(meta.to_dict(), indent=4)
                        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w") as metafile:
                            await metafile.write(meta_text)
                    else:
                        logger.info("[bold yellow]Cover could not be retrieved")
            elif Path(poster_img).exists() and meta.rehosted_artwork_url is not None:
                await generic.write(f"TMDB Cover: {meta.rehosted_artwork_url}\n")
            if len(meta.image_list) > 0:
                await generic.write("\nImage Webpage:\n")
                for each in meta.image_list:
                    await generic.write(f"{each['web_url']}\n")
                await generic.write("\nThumbnail Image:\n")
                for each in meta.image_list:
                    await generic.write(f"{each['img_url']}\n")
        title = re.sub(r"[^0-9a-zA-Z\[\\]]+", "", meta.title)
        archive = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{title}"
        release_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        shareable_torrents: set[str] = set()
        try:
            base_path = TorrentManifest(meta.base_dir, meta.uuid).default_path()
            if base_path is not None:
                base_torrent = Torrent.read(base_path)
                manual_name = re.sub(r"[^0-9a-zA-Z\[\]\'\-]+", ".", Path(meta.path or "").name)
                Torrent.copy(base_torrent).write(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{manual_name}.torrent", overwrite=True)
                shareable_torrents.add(f"{manual_name}.torrent")
            manual_tracker_raw = self.tracker_config.get("MANUAL")
            manual_tracker_cfg: dict[str, Any] = cast(dict[str, Any], manual_tracker_raw) if isinstance(manual_tracker_raw, dict) else {}
            manual_filebrowser = manual_tracker_cfg.get("filebrowser")
            filebrowser = manual_filebrowser if isinstance(manual_filebrowser, str) else None
            await asyncio.to_thread(_write_archive, f"{archive}.tar", release_dir, shareable_torrents)
            if filebrowser is not None:
                # The release folder keeps the tracker torrents, so the link
                # opens a separate copy holding only the shareable files.
                share_dir = Path(meta.base_dir) / "tmp" / "manual_packages" / meta.uuid
                await asyncio.to_thread(_stage_share, share_dir, release_dir, shareable_torrents, f"{archive}.tar")
                base_url = filebrowser.rstrip("/")
                path = f"{'/' + 'tmp' + '/'}manual_packages/{meta.uuid}"
                url = base_url + urllib.parse.quote(path, safe="/")
            else:
                tar_bytes = await asyncio.to_thread(Path(f"{archive}.tar").read_bytes)
                files = {"files[]": (f"{meta.title}.tar", tar_bytes)}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = (await client.post("https://uguu.se/upload.php", files=files)).json()
                logger.debug(f"[cyan]{response}")
                url = response["files"][0]["url"]
            return url
        except Exception:
            return False
