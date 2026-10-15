"""Write the release metadata without exposing a partial JSON file."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import aiofiles

from src.cogs.redaction import PathAwareEncoder
from src.meta import Meta

# Windows refuses to replace a file while another process (e.g. the Web UI
# preview poller) has it open for reading. Those reads are brief, so retry.
_REPLACE_ATTEMPTS = 10
_REPLACE_RETRY_DELAY = 0.1


async def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            await asyncio.sleep(_REPLACE_RETRY_DELAY * attempt)


async def write_meta_file(meta: Meta) -> None:
    meta_file = Path(meta.base_dir) / "tmp" / meta.uuid / "meta.json"
    content = json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder)
    fd, temp_name = tempfile.mkstemp(prefix=".meta-", suffix=".json", dir=meta_file.parent)
    os.close(fd)
    temp_file = Path(temp_name)
    try:
        async with aiofiles.open(temp_file, "w", encoding="utf-8") as snapshot:
            await snapshot.write(content)
        await _replace_with_retry(temp_file, meta_file)
    finally:
        temp_file.unlink(missing_ok=True)
