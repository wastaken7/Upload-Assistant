# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0

__version__ = "v1.6"

"""
Changelog for version v1.6 (2026-06-20):

## What's Changed
* Usenet: Added archive encryption, obfuscation, and NZB password injection support.
* Usenet: Added fully random poster name and email generation.
* Usenet: Fixed 260-character path limit on Windows with PAR2.
* Trackers: Refactored title formatting and cleaned up redundant type casts (ASC, BJS, BT).
* Repository links updated in README.
"""

__version__ = "v1.5"

"""
Changelog for version v1.5 (2026-06-17):

## What's Changed
* Added support for Usenet and Indexer posting.
* Updated README and Documentation for Usenet & Indexer Posting.
"""

__version__ = "v1.4"

"""
Changelog for version v1.4 (2026-06-17):

## What's Changed
* Usenet pipeline added.
"""

__version__ = "v1.3"

"""
Changelog for version v1.3 (2026-06-16):

## What's Changed
* trackers(BJS): Added `m4b` file extension support.
"""

__version__ = "v1.2"

"""
Changelog for version v1.2 (2026-06-12):

## What's Changed
* Added filtering of translator names from audiobook/book metadata authors.
* Added ASIN (Amazon Standard Identification Number) to title for the Zenith (ZNTH) tracker.
"""

__version__ = "v1.1"

"""
Changelog for version v1.1 (2026-06-11):

## What's Changed
* Refactored and consolidated BOOK category description building logic across multiple trackers (ASC, BJS, BT, CBR, DC, TL) into a single, highly customizable formatting method in DescriptionBuilder.
* Added auto-detection and cleaning of "Unabridged" and "Abridged" edition strings from audiobook metadata, preserving them for BOOK category uploads.
* Added support for ASIN (Amazon Standard Identification Number) metadata extraction via MyAnonamouse (MAM) API and MediaInfo general tracks, including CLI overrides and tracker display/formatting support.
* Enhanced game support, including console game detection, optimized mapping of categories/types for CBR, and skipped cover uploads for games on UNIT3D.
* Added support for custom unRAR executable paths in configuration.
* Added support for the Zenith (ZNTH) tracker.
* Updated README to reflect project status and fork-specific features.
* Removed FearNoPeer.
* Refactored adult content detection logic.
* Various bugfixes and payload optimizations for trackers including ACM, HUNO, and UNIT3D.
"""

__version__ = "v1.0"

"""
"""
