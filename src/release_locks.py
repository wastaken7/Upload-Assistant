"""Coordinate the work that concurrent tracker uploads share for one release."""

import asyncio
import weakref

from src.meta import Meta

# Locks belong to one event loop, and Web UI runs each start a new one.
_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[str, str, str], asyncio.Lock]] = weakref.WeakKeyDictionary()


def _release_lock(meta: Meta, purpose: str) -> asyncio.Lock:
    loop_locks = _locks.setdefault(asyncio.get_running_loop(), {})
    return loop_locks.setdefault((purpose, str(meta.base_dir), str(meta.uuid)), asyncio.Lock())


def release_language_lock(meta: Meta) -> asyncio.Lock:
    """Return the lock that lets one tracker at a time detect or ask for a release's languages.

    The first tracker records the result on ``meta``; the others wait, then
    reuse it instead of prompting again.
    """
    return _release_lock(meta, "languages")


def release_image_lock(meta: Meta) -> asyncio.Lock:
    """Return the lock that lets one tracker at a time capture or host a release's images.

    Trackers upload concurrently, but capturing and hosting images uses state
    they all share: ``meta.imghost``, ``meta.frame_overlay`` and
    ``meta.force_tonemap`` are switched while it runs, and the screenshot
    manifest, ``pack_image_links.json`` and ``meta.json`` are rewritten. The
    first tracker to need pack images or a rehost does that work here; the
    others wait and then reuse what it recorded.

    The lock is not reentrant: never take it while already holding it.
    """
    return _release_lock(meta, "images")
