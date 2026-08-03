# UNIT3D FAMILY KNOWLEDGE BASE

## OVERVIEW

This directory is one adapter family: `UNIT3D` owns common API search/upload behavior, while 38 concrete subclasses provide tracker identity, mappings, validations, and payload exceptions.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Base contract | `__init__.py` | Constructor, URLs, auth, search, mapping hooks, upload/retry flow |
| New-adapter scaffold | `UNIT3D_TEMPLATE.py` | Naming and override inventory; examples are placeholders |
| Registration | `../../trackersetup.py` | Every concrete adapter is imported and entered in `tracker_class_map` |
| Standard adapters | `aither.py`, `blutopia.py`, `hawkeuno.py` | Typical constructor plus targeted mapping/check overrides |
| Heavy exceptions | `shareisland.py`, `emuwarez.py`, `cinematik.py`, `darkpeers.py`, `znth.py` | Broader per-site policies; inspect before generalizing |
| Focused coverage | `../../../tests/test_unit3d_search_existing.py` | Base search behavior and tracker-specific rule suites |

## CONVENTIONS

- Subclass `UNIT3D` directly and call `super().__init__(config, tracker_name="CANONICAL")`; external callers still instantiate the subclass with only `config`.
- Set site identity and URL/config data through the established base/config path. Keep the canonical name aligned with the registry and example config.
- Prefer inherited search, description, upload, retry, and response behavior. Override only the narrow hook that differs.
- Preserve mapping signatures, including `reverse` and `mapping_only` where present. Callers use both forward payload mapping and reverse display/search mapping.
- Keep category/type/resolution methods deterministic for the same `Meta`; additional checks return the established warning/error shape.
- Use `get_additional_data()` for extra payload fields and `get_name()`/`get_description()` only when the site truly diverges from base output.
- Register the class in `src/trackersetup.py`, add schema/defaults in `data/example_config.py`, then add a focused test for each override.
- The template module's uppercase filename is an explicit Ruff `N999` exception; concrete adapter filenames remain lowercase.

## ANTI-PATTERNS

- Do not copy the full base upload or search implementation to change one field; drift across dozens of adapters is already a family risk.
- Do not remove `reverse`/`mapping_only` parameters from mapping overrides, even if one local call path does not use them.
- Do not assume all adapters support only MOVIE/TV; specialized adapters also encode BOOK, GAME, or MUSIC rules.
- Do not normalize the heavy exception modules into a minimal template without preserving their tracker-specific validation and payload contracts.
- Do not forget the central registry import: an unregistered adapter is invisible to CLI, WebUI, auth grouping, and validation.
