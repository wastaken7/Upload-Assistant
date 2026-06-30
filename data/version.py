# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0

__version__ = "v1.9"

"""
Changelog for version v1.9 (2026-06-29):

## What's Changed
* **Features**:
  * Added support and banned groups list for MidnightScene tracker.
  * Added qBittorrent API authentication support.
  * Added automated environment and dependency validation during startup.
  * Added warning for slow qBittorrent search speeds.
  * Added write/read torrent metadata support.
  * Added screenshot support to CRP tracker.
  * Added aligned tracker naming changes below Base Name in confirmation prompt.
* **Refactoring & Improvements**:
  * Parallelized tracker search and pre-checks.
  * Refactored Meta class and improved type safety.
  * Centralized duplicate check error handling and TMDB localization prep.
  * Centralized and refactored genre and keyword handling to use lists instead of strings.
  * Improved local upload cache checks in `search_existing` for USENET trackers.
  * Improved console output formatting for tracker checks and upload prompts.
  * Enhanced meta.tag handling and TMDB None-value checks.
* **Fixes**:
  * Fixed Qui Proxy support, .torrent resume, and endpoint priority.
  * Resolved and suppressed CodeQL / code scanning alerts (including URL substring sanitization).
  * Fixed signature sizes.
  * Fixed `UnboundLocalError` for `is_tracker_comment`.
* **Documentation**:
  * Updated README and added local documentation copies / wiki pages.
* **Dependencies**:
  * Bumped various package dependencies (cryptography, urllib3, pillow, lxml, js-yaml, etc.).
"""

__version__ = "v1.8"

"""
Changelog for version v1.8 (2026-06-24):

## What's Changed
* feat: automatic `-personalrelease` detection based on group tags.
* fix: ensure that a torrent is not created for a folder when there is only one file.
* feat: make Usenet posting and torrent tracker uploads concurrent by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/32
"""

__version__ = "v1.7"

"""
Changelog for version v1.7 (2026-06-23):

## What's Changed
* Metadata & Trackers: Centralized description generation, simplified tracker logic using new `basename_no_ext` metadata, and refactored book description and signature size settings (BT, BJS).
* Usenet: Added pesto uploader support, skip_archive mode, automatic binary downloads (nyuu, par2cmdline-turbo, pesto, 7-Zip), and refactored indexers.
* SUIO Tracker: Replaced encryption with base_url validation.
* Bitrate Option: Added 64kbps option for BJS bitrate.
* Dupe Check: Added deduplication in `dupe_check`, display of duplicate size differences, and embedded links for duplicates search.
"""

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
