# CORE PACKAGE KNOWLEDGE BASE

## OVERVIEW

`src` is the flat shared package behind CLI and WebUI runs: metadata state, preparation stages, external providers, artifact generation, clients, and tracker dispatch all meet here.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Shared release state | `meta.py` | `Meta` supports attribute and dict-like access; ~183 files import it |
| Pipeline entry | `prep.py` | `Prep.gather_prep()` selects music, book, game, disc, or video work |
| Pipeline stages | `prep.py`, `prep_helpers.py` | Init -> detection -> media -> size/validation -> tracker/torrent -> local artifacts -> metadata -> finalization |
| CLI schema | `args.py`, `apply_overrides.py` | Runtime overrides ultimately land on `Meta` |
| Metadata search | `metadata_searching.py`, provider modules | Provider caching goes through `metadata_cache.py` |
| Artifact paths | `temp_paths.py`, `screenshot_manifest.py`, `tracker_images.py` | Typed image directories and per-tracker collections |
| Progress bridge | `webui_progress.py` | Thread-safe callback and `ProgressEvent` schema |
| Output creation | `torrentcreate.py`, `usenetcreate.py`, `manualpackage.py` | Torrent/Usenet local work can start before metadata finalization; manual packaging occurs during tracker handling |
| Client integration | `clients.py`, `torrent_clients/` | `Clients` composes protocol-specific mixins |
| Tracker lifecycle | `trackersetup.py`, `trackerstatus.py`, `trackerhandle.py` | Enable/filter/check/upload phases are separate |

## CONVENTIONS

- Import package modules as `src.<module>`; `src` itself is the package boundary.
- Treat `Meta` fields as a cross-stage interface. Initialize ownership in preparation code; adapters consume or add tracker-scoped output rather than silently changing global meaning.
- Keep category branching in preparation stages. `MUSIC` uses `src/music/prep.py`; book and game have their own prep modules before shared client/tracker work.
- Build release paths through `temp_paths.py`. Screenshot manifests and tracker image lists rely on stable UUID and typed-directory semantics.
- Publish long-running work through `webui_progress.py` without changing event keys, group IDs, units, or reset/complete lifecycle.
- Preserve async boundaries around network, screenshot, torrent, and Usenet work. Some existing filesystem calls remain synchronous by explicit Ruff exception.
- Provider caches use version/TTL validation and atomic writes; a cache miss or stale entry must remain recoverable.
- `TakeScreensManager` applies its supplied config to module-level screenshot limits at construction through `_apply_config`; tests changing those settings must instantiate a fresh manager with the patched config.

## ANTI-PATTERNS

- Do not use the release temp root as a catch-all image directory; screenshot enumeration would ingest artwork or diagnostics.
- Do not bypass `screenshot_manifest.py` when changing screenshot identity, replacement, or persisted review behavior.
- Do not mix tracker policy into generic metadata providers or preparation helpers; keep site rules in `src/trackers`.
- Do not add client-specific branches to `Clients` when the behavior belongs in a `torrent_clients` mixin or shared `path_utils.py`.
- Do not replace `Meta` with an untyped ad-hoc dict in one stage; downstream code depends on copy, serialization, and dict-like compatibility.
- Do not publish progress from worker threads without the existing lock/callback abstraction.
