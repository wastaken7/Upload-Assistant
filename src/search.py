# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
from pathlib import Path
from typing import Any, cast

from src.console import logger


class Search:
    """
    Logic for searching
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def _get_search_dirs(self) -> list[str]:
        config_dir = self.config.get("DISCORD", {}).get("search_dir", [])
        if isinstance(config_dir, str):
            return [config_dir]
        if isinstance(config_dir, list):
            config_list = cast(list[Any], config_dir)
            return [str(entry) for entry in config_list]
        return []

    async def search_file(self, filename: str) -> list[str] | None:
        filename = filename.lower()
        files_total: list[str] = []
        if filename == "":
            logger.info("nothing entered")
            return None
        words = filename.split()

        async def search_file(search_dir: str) -> list[str]:
            files_total_search: list[str] = []
            logger.info(f"Searching {search_dir}")
            for root, _dirs, files in os.walk(search_dir, topdown=False):
                for name in files:
                    if not name.endswith(".nfo"):
                        l_name = name.lower()
                        if await self.file_search(l_name, words):
                            files_total_search.append(Path(root) / name)
            return files_total_search

        for each in self._get_search_dirs():
            files = await search_file(each)
            files_total.extend(files)
        return files_total

    async def search_folder(self, foldername: str) -> list[str] | None:
        foldername = foldername.lower()
        folders_total: list[str] = []
        if foldername == "":
            logger.info("nothing entered")
            return None
        words = foldername.split()

        async def search_dir(search_dir: str) -> list[str]:
            logger.info(f"Searching {search_dir}")
            folders_total_search: list[str] = []
            for root, dirs, _files in os.walk(search_dir, topdown=False):
                for name in dirs:
                    l_name = name.lower()

                    if await self.file_search(l_name, words):
                        folders_total_search.append(Path(root) / name)

            return folders_total_search

        for each in self._get_search_dirs():
            folders = await search_dir(each)
            folders_total.extend(folders)

        return folders_total

    async def file_search(self, name: str, name_words: list[str]) -> bool:
        check = True
        for word in name_words:
            if word not in name:
                check = False
                break
        return check
