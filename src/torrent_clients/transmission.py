# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from pathlib import Path
from typing import Any

import transmission_rpc
from torf import Torrent

from src.console import logger
from src.meta import Meta
from src.torrent_clients.path_utils import map_save_path


class TransmissionClientMixin:
    def transmission(self, path: str, torrent: Torrent, local_path: str, remote_path: str, client: dict[str, Any], meta: Meta) -> None:
        try:
            tr_client = transmission_rpc.Client(
                protocol=client["transmission_protocol"],
                host=client["transmission_host"],
                port=int(client["transmission_port"]),
                username=client["transmission_username"],
                password=client["transmission_password"],
                path=client.get("transmission_path", "/transmission/rpc"),
            )
        except Exception as e:
            logger.info(f"[bold red]Unable to connect to transmission: {e}")
            return

        logger.info("Connected to Transmission")
        # Remote path mount
        path = map_save_path(path, local_path, remote_path, trailing_slash=False)

        path = Path(path).parent.as_posix()

        if meta.transmission_label is not None:
            label = [meta.transmission_label]
        elif client.get("transmission_label") is not None:
            label = [client["transmission_label"]]
        else:
            label = None

        tr_client.add_torrent(torrent=torrent.dump(), download_dir=path, labels=label)

        logger.debug(f"[cyan]Path: {path}")
