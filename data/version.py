# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0

__version__ = "v2.4"

"""
Changelog for version v2.4 (2026-07-17):

## What's Changed
* **Upgrade Alert**:
  * This release renames tracker config keys to match the new descriptive tracker modules.
  * If you are upgrading from `v2.3` or earlier, run `python config-generator.py` and review your `TRACKERS` section before uploading.
* **Merged Pull Requests**:
  * refactor: apply Ruff fixes and rename trackers to descriptive modules by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/59
  * feat(usenet): add duplicate search support by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/60
  * fix(tmdb): tighten anime detection from TMDB by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/62
  * Add daily API hit limits for USENET duplicate search by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/61
  * fix: avoid Path.replace error when adding torrents to qBittorrent by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/64
  * feat(seedbox): add no-root Linux installer by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/66
  * feat(webui): add live execution preview by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/65
  * Fix Usenet posting when indexer dupe check fails by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/69
  * feat(webui): stream live upload progress by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/70
* **Direct Commits Since v2.3**:
  * ci: add PR validation workflow
  * add option to disable tracker name markup
  * docs: align tracker names with modules
  * remove check for drunkenslug upload URL
  * fix: tighten tracker typing checks
  * fix: keep rtorrent save path as string
  * feat(webui): show missing CLI args
  * fix(web-ui): support annotated config dicts
  * fix(bjshare): normalize and dedupe credit names
  * feat(discord): make bot deps optional
  * feat(args): add `--multi` for GAME uploads
* **Full Changelog**: https://github.com/wastaken7/Upload-Assistant/compare/v2.3...v2.4
"""

"""
Changelog for version v2.3 (2026-07-15):

## What's Changed
* **Features & Improvements**:
  * feat: add support to MakingOff (MKO) by @heatoz in https://github.com/wastaken7/Upload-Assistant/pull/47
  * Replaced `print` statements with a proper `logger` throughout the codebase by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/48.
  * Added `upload_order` option to control Usenet and torrent upload sequence.
  * Run bandwidth check on tracker upload order regardless of `qbit_bandwidth_control`.
  * Implemented automatic DVD menu capture.
  * Improved console game support, prompts, and description formatting.
  * Config generator now preserves comments in generated configuration file.
  * Improved BJS title, tags, and overview extraction.
  * feat(ZNTH): adjust book titles, narrators, covers, and series by @znth-dev in https://github.com/wastaken7/Upload-Assistant/pull/54
  * refactor: move tracker attributes to class level by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/56
  * refact(lint): resolve ruff linter issues and prepare for Python 3.14 by @wastaken7 in https://github.com/wastaken7/Upload-Assistant/pull/50
* **Fixes**:
  * fix(usenet): adapt pesto integration to v0.3.53+'s streaming --check by @franzopl in https://github.com/wastaken7/Upload-Assistant/pull/57
  * fix(DS): add new required header api_key by @fabricionaweb in https://github.com/wastaken7/Upload-Assistant/pull/58
  * fix(MKO): get the correct release name by @heatoz in https://github.com/wastaken7/Upload-Assistant/pull/55
  * usenet: fix pesto --check repost, add --check-post-retries by @franzopl in https://github.com/wastaken7/Upload-Assistant/pull/53
  * Brought nyuu to parity with pesto's article-check and fixed filename obfuscation.
  * Fixed `Meta.copy` to use `deepcopy` and prevent sharing mutable fields.
  * BT: skip asking tags when uploading books.
  * SUIO: normalize upload name by stripping accents.
  * Usenet: honor `skip_archive` over `archive_password`; use exponential PAR2 volumes.
  * Usenet: do not use passwords that begin with `-`.
  * Decoded HTML entities in extracted book/audiobook metadata.
  * Escaped glob paths and added ZNTH book search support.
  * Clients: respect the `--skip_auto_torrent` argument.
  * Fixed empty line in config.
"""

"""
Changelog for version v2.2 (2026-07-03):

## What's Changed
* **Features & Improvements**:
  * Added duplicate size tolerance checks.
  * Add enhanced rich progress bar display for mkbrr.
  * Added search caching support for book preparation.
  * Added automatic stripping of brackets from book titles during book preparation.
  * feat: enable pesto --check article verification and rework Usenet upload progress by @franzopl in https://github.com/wastaken7/Upload-Assistant/pull/43
  * Updated tracker configurations and the config generator.
  * Enhanced genre mapping to include untranslated genres.
  * Added resolution ID mapping and retrieval method for SAM tracker.
  * Cleaned up and modernized codebase to remove `Optional` type usage.
"""

__version__ = "v2.1"

"""
Changelog for version v2.1 (2026-07-02):

## What's Changed
* **Features & Improvements**:
  * Added support for Lostimg image host and API integration.
  * Added encode requirements for CBR tracker.
  * Added `get_name` method to process and format media names with language support.
  * Streamlined localized data loading in multiple tracker classes.
* **Fixes**:
  * Updated qBittorrent response handling for fetching torrent properties via proxy.
  * Removed redundant `announce_url` and `api_key` checks.
"""

__version__ = "v2.0"

"""
Changelog for version v2.0 (2026-07-01):

## What's Changed
* **Features**:
  * Added validation for `api_key` and `announce_url` before upload.
* **Fixes & Improvements**:
  * Improved IMDb usage on ASC tracker.
  * Improved episode overview display by truncating to 60 characters.
  * Fixed BT payload data issues.
  * Updated MediaInfo retrieval condition to check for BDMV disc type.
  * Standardized year handling across multiple modules to ensure consistent data types.
  * Updated default version in `ensure_pesto_binary` method to v0.3.34.
  * Removed redundant metadata injection logic from torrent creation process.
  * Updated Meta class attributes and improved libplacebo handling.
  * Refactored Meta and Disc Handling.
"""

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
