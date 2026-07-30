# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import base64
from pathlib import Path
from typing import Any

from deluge_client import DelugeRPCClient
from torf import Torrent

from src.console import logger
from src.torrent_clients.path_utils import map_save_path


class DelugeClientMixin:
    def deluge(self, path: str, torrent_path: str, torrent: Torrent, local_path: str, remote_path: str, client: dict[str, Any]) -> None:
        deluge_client: Any = DelugeRPCClient(client["deluge_url"], int(client["deluge_port"]), client["deluge_user"], client["deluge_pass"])
        # deluge_client = LocalDelugeRPCClient()
        deluge_client.connect()
        if deluge_client.connected:
            logger.info("Connected to Deluge")
            # Remote path mount
            path = map_save_path(path, local_path, remote_path, trailing_slash=False)

            path = Path(path).parent.as_posix()

            deluge_client.call("core.add_torrent_file", torrent_path, base64.b64encode(torrent.dump()), {"download_location": path, "seed_mode": True})
            logger.debug(f"[cyan]Path: {path}")
        else:
            logger.info("[bold red]Unable to connect to deluge")
