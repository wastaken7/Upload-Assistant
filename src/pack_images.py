"""Coordinate the per-file pack images that concurrent tracker uploads share."""

import asyncio
import weakref

from src.meta import Meta

# Locks belong to one event loop, and Web UI runs each start a new one.
_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[str, str], asyncio.Lock]] = weakref.WeakKeyDictionary()


def pack_image_lock(meta: Meta) -> asyncio.Lock:
    """Return the lock that lets one tracker at a time create a release's pack images.

    Trackers upload concurrently. The first one to need the per-file pack
    screenshots captures, hosts and records them; the others wait here and
    reuse the recorded images instead of hosting duplicates or racing on
    ``pack_image_links.json`` and ``meta.json``.
    """
    loop_locks = _locks.setdefault(asyncio.get_running_loop(), {})
    return loop_locks.setdefault((str(meta.base_dir), str(meta.uuid)), asyncio.Lock())
