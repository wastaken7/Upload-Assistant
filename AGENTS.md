# PROJECT KNOWLEDGE BASE

**Generated:** 2026-08-03
**Analyzed commit:** fee9e80a
**Analyzed branch:** development

## OVERVIEW

Upload-Assistant is a Python 3.14 CLI and Flask/Waitress WebUI for preparing media, checking duplicates, creating torrent or Usenet artifacts, and uploading to tracker/indexer adapters. The runtime is a monolith: root `upload.py` orchestrates a flat `src` package and can launch the WebUI in exclusive server mode.

## STRUCTURE

```text
Upload-Assistant/
├── upload.py              # CLI entrypoint and per-release orchestration
├── config-generator.py    # Interactive data/config.py generator/migrator
├── src/                   # Shared preparation, metadata, client, and upload code
│   └── trackers/          # Tracker adapters and protocol-family bases
├── web_ui/                # Flask API/auth plus template-loaded React frontend
├── tests/                 # Pytest regression suites; no shared conftest.py
├── data/                  # Shipped schema/templates mixed with ignored user state
├── bin/                   # Runtime binary managers and Docker download helpers
├── scripts/               # Linux/Windows installers and Inno Setup packaging
└── docs/                  # Hand-maintained operational and feature guides
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| CLI flow or queue execution | `upload.py`, `src/args.py`, `src/queuemanage.py` | `main()` -> `do_the_thing()` -> `process_meta()` |
| Preparation lifecycle | `src/prep.py`, `src/prep_helpers.py`, `src/meta.py` | `Meta` is the shared cross-domain state contract |
| Metadata providers | `src/metadata_searching.py`, `src/tmdb.py`, `src/imdb.py`, `src/music/` | Provider caches live behind `src/metadata_cache.py` |
| Screenshots and artwork | `src/takescreens.py`, `src/uploadscreens.py`, `src/temp_paths.py` | Release images must use typed temp subdirectories |
| Tracker registration/upload | `src/trackersetup.py`, `src/trackerhandle.py`, `src/trackers/` | Registry and auth-class sets are static |
| Torrent clients | `src/clients.py`, `src/torrent_clients/` | Path mapping/link safety is centralized in `path_utils.py` |
| WebUI/API/security | `web_ui/server.py`, `web_ui/auth.py`, `web_ui/static/js/` | Server owns routes, auth, CSRF, browse roots, execution |
| Config schema and migration | `data/example_config.py`, `config-generator.py`, `src/configvalidator.py` | `data/config.py` is ignored user state, not the schema |
| CI and releases | `.github/workflows/` | PR compile/test/Docker gates; release workflows package Docker/Windows |

## CODE MAP

Python LSP was unavailable at generation time; reference counts below come from repository text/import analysis.

| Symbol | Type | Location | Refs | Role |
| --- | --- | --- | ---: | --- |
| `main` | async function | `upload.py:3000` | WebUI + script | Public CLI/in-process entrypoint |
| `do_the_thing` | async function | `upload.py:2162` | 1 direct | Config, arguments, WebUI mode, queue loop |
| `process_meta` | async function | `upload.py:1106` | 1 direct | Per-release preparation and upload pipeline |
| `Meta` | dataclass-like state | `src/meta.py` | ~183 files | Shared metadata and mutable pipeline contract |
| `Prep` | class | `src/prep.py` | core pipeline | Media/category-specific preparation dispatch |
| `TrackerSetup` | class | `src/trackersetup.py:107` | 5 Python files | Registry lookup, filtering, claims, requests, auth groups |
| `tracker_class_map` | mapping | `src/trackersetup.py:1334` | all adapters | Tracker name to concrete class registry |
| `Common` | class | `src/trackers/common.py:32` | high fan-in | Shared torrent, language, media, and description helpers |
| `release_temp_dir` | function | `src/temp_paths.py` | 1 internal call | Root used by the typed image-directory helpers |
| `app` | Flask app | `web_ui/server.py:332` | `upload.py` | Web pages, APIs, auth middleware, execution control |

## CONVENTIONS

- Python target is 3.14. Ruff uses line length 176 and absolute first-party imports from `cogs`, `data`, `src`, and `web_ui`; see `pyproject.toml` for enabled rule families and exclusions.
- `upload.py` intentionally permits late imports (`E402`). `UNIT3D_TEMPLATE.py` intentionally permits its uppercase module name (`N999`).
- Tests use `test_<subject>.py`, `test_<behavior>`, `tmp_path`, import-qualified monkeypatches, `AsyncMock`, and `pytest.mark.asyncio`; there is no repository pytest configuration.
- Frontend React is loaded through Flask templates with CDN React/Babel/Tailwind, not bundled. `shared_utils.js` must load before `app.js` or `config_app.js`.
- `data/example_config.py` is the checked-in schema/default source. The WebUI and generator write ignored `data/config.py`; Docker restores missing built-ins but only force-syncs `data/version.py`.
- Tracker names are normalized for registry lookup, while individual config keys may retain site-specific casing. Follow the existing adapter and example-config key exactly.

## ANTI-PATTERNS (THIS PROJECT)

- Do not put screenshots, artwork, menu captures, or spectrograms directly in the release temp root; consumers enumerate images by typed subdirectory.
- Do not send `MUSIC` through video/TMDB/screenshot/episode preparation. It has a dedicated pipeline before the shared tracker/client stage.
- Do not treat `data/config.py`, cookies, auth files, cache JSON, or `tmp/` contents as source. They are mutable user/runtime state and may contain secrets.
- Do not weaken WebUI auth, same-origin/CSRF checks, realpath browse-root confinement, or HTML sanitization when changing routes or frontend rendering.
- Do not add a tracker class without its constructor contract, `tracker`, `supported_categories`, `auth_type`, registry entry, example config, and focused behavior tests.
- Do not route qBittorrent bandwidth control through the QUI proxy; `src/qbitwait.py` requires the direct qBittorrent endpoint.
- Do not set Docker `user:` when relying on PUID/PGID ownership repair; the entrypoint must begin as root and then drop privileges.

## UNIQUE STYLES

- The import package is the flat `src/` directory; there is no `src/<project>` package or console-script metadata.
- `Meta` carries hundreds of fields between preparation stages and adapters; extend it deliberately and preserve dict-like compatibility used throughout the tree.
- Tracker support combines standalone adapters with `UNIT3D`, `NEXUSPHP`, `AVISTAZ`, and `USENET` families, all eagerly registered in one map.
- `data/` deliberately mixes immutable shipped defaults with persistent ignored configuration, credentials, cookies, tags, and caches.
- WebUI execution can call `upload.main()` in-process or spawn `upload.py`; progress crosses the boundary through `src/webui_progress.py`.

## COMMANDS

```bash
python -m pip install -r requirements.txt
python upload.py <path> [arguments]
python -m pip install pytest pytest-asyncio
PYTHONPATH=. python -m pytest -q
python -m compileall src web_ui upload.py config-generator.py
ruff check .
pyright
docker build .
cd web_ui/static/js && npm ci && npm run lint:react && npm run format:check
```

Pytest and pytest-asyncio are installed explicitly by CI, not by `requirements.txt`. CI copies `data/example_config.py` to `data/config.py`; do not overwrite a real local config when reproducing that setup.

## NOTES

- `AGENTS.md` and `CLAUDE.md` are ignored by `.gitignore`; use `git add -f` only if intentionally committing generated guidance.
- WebUI-only startup requires explicit browse roots from `UA_BROWSE_ROOTS` or CLI paths. Docker values are container-side paths.
- Normal development auth state defaults under `data/`; Docker commonly persists it under the mounted XDG config directory.
- `README.md` currently links to missing `docs/web-ui.md`; the live WebUI guides are `docs/web-ui-basic.md` and `docs/web-ui-api.md`.
