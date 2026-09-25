"""Write the release metadata without exposing a partial JSON file."""

import json
import os
import tempfile
from pathlib import Path

import aiofiles

from src.cogs.redaction import PathAwareEncoder
from src.meta import Meta


async def write_meta_file(meta: Meta) -> None:
    meta_file = Path(meta.base_dir) / "tmp" / meta.uuid / "meta.json"
    content = json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder)
    fd, temp_name = tempfile.mkstemp(prefix=".meta-", suffix=".json", dir=meta_file.parent)
    os.close(fd)
    temp_file = Path(temp_name)
    try:
        async with aiofiles.open(temp_file, "w", encoding="utf-8") as snapshot:
            await snapshot.write(content)
        temp_file.replace(meta_file)
    finally:
        temp_file.unlink(missing_ok=True)
