# TRACKER ADAPTER KNOWLEDGE BASE

## OVERVIEW

`src/trackers` contains site policy and protocol-family adapters. `src/trackersetup.py` eagerly imports and registers every concrete tracker; `src/trackerhandle.py` dispatches uploads using derived auth groups.

## STRUCTURE

```text
trackers/
├── common.py       # Shared torrent, language, media, description, and API helpers
├── UNIT3D/         # API-family base, template, and many concrete adapters
├── NEXUSPHP/       # Cookie-auth mapping-oriented family
├── AVISTAZ/        # Shared base plus cross-site network routing
├── USENET/         # Indexer upload/search adapters and Newznab helpers
└── *.py            # Standalone tracker implementations and policy
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Shared helpers | `common.py` | `Common` is a service object, not the universal adapter base |
| Registration/filtering | `../trackersetup.py` | `tracker_class_map`, auth sets, categories, claims, requests |
| Upload dispatch | `../trackerhandle.py` | Includes special MANUAL, TORRENTHR, and PASSTHEPOPCORN paths |
| API-family behavior | `UNIT3D/__init__.py` | Async search, mapping, description, upload, response hooks |
| Cookie-family behavior | `NEXUSPHP/__init__.py`, `AVISTAZ/__init__.py` | Subclasses supply tracker name and local mappings/rules |
| AvistaZ routing | `AVISTAZ/routing.py` | Country, age, SD, and cross-tracker routing decisions |
| Registry regressions | `../../tests/test_tracker_setup.py` | Category filtering and class-map expectations |

## CONVENTIONS

- A concrete adapter must be callable as `TrackerClass(config)`, even when its family base internally requires `tracker_name`.
- Declare stable `tracker`, `supported_categories`, and `auth_type`; registry-derived `api_trackers`, `other_api_trackers`, and `http_trackers` control downstream branches.
- Keep `search_existing()` and `upload()` async. Preserve method shapes consumed by `TrackerSetup`, `trackerhandle`, and WebUI tracker discovery.
- Reuse `Common` for torrent creation, language validation, MediaInfo, cookie parsing, and description helpers instead of cloning cross-site behavior.
- Add every concrete class import and `tracker_class_map` entry in `src/trackersetup.py`; add its canonical schema block in `data/example_config.py`.
- Match the existing config-key spelling/casing for the site. Registry names normalize to uppercase, but configuration lookups are not uniformly normalized.
- Put cross-site family behavior in the family base; keep tracker-specific validation, ID mappings, payload fields, and naming in the concrete module.
- Add focused tests for every non-default rule; tracker rule suites commonly use patched HTTP clients and `Meta` fixtures.

## ANTI-PATTERNS

- Do not infer auth grouping from module location or URL shape; `auth_type` is the source consumed by derived registry sets.
- Do not change constructor shape, class attributes, or async method names without tracing the static registry and dispatcher.
- Do not move site-specific forbidden-category, codec, container, language, or naming policy into `Common` unless multiple independent adapters share it.
- Do not edit one family adapter by copying an entire base method when a narrow hook or mapping override exists.
- Preserve `trackerhandle`'s explicit `MANUAL`, `TORRENTHR`, and `PASSTHEPOPCORN` branches; keep `USENET` separate from ordinary torrent adapter classes.
