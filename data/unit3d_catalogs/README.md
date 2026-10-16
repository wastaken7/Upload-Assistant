# UNIT3D tracker catalogs

One `<tracker>.json` file contains the site's `regions` and `distributors`, and
optionally its `categories`, `types` and `resolutions`. Filenames use lowercase
Upload Assistant tracker names. All five sections map numeric IDs, stored as
JSON object keys, to names. Regions use three-letter region codes.

The [Catalog Exporter](../../scripts/UNIT3D-Catalog-Exporter/README.md) produces
complete site snapshots with `regions_complete: true` and
`distributors_complete: true`. These flags make each respective section
authoritative: absent entries are unsupported, rather than inherited from
`default.json`. Empty complete sections are also exported when their fields are
absent from the page; they must not inherit default options.

When a region selector contains non-country or unrecognized labels,
`region_labels` preserves its entire ID-to-display-name catalog. The `regions`
section contains only recognized country codes and is still authoritative.
Language/dubbing filters and "Other" choices are not assigned guessed country
codes. `region_labels` is retained for future uses and is not used for upload IDs.

Existing migrated files without a complete flag retain their previous behavior:
their entries override or extend the default catalog. This preserves existing
verified tracker differences without claiming an unverified full snapshot.

Distributor-specific compatibility fields retain their original meaning:

- `aliases`: alternate names mapped to the site's numeric distributor IDs.
- `excluded_ids`: distributor IDs removed after expanding defaults and applying overrides.
- `excluded_aliases`: inherited distributor aliases that must not resolve.

Default distributor aliases follow company identity when site IDs differ, and
site canonical names take precedence. Preserve manually maintained aliases when
refreshing a file using the exporter.

## Compacting extracted catalogs

Run the standalone comparison script after exporting:

```powershell
py scripts/compact_unit3d_catalogs.py data/unit3d_catalogs --output-dir tmp/unit3d-compacted
```

You can also pass individual JSON files, or a directory of new exports. The
script skips `default.json`, writes separate copies and refuses to overwrite
existing files. Use a new output directory for each run. Copy the reviewed
compacted tracker files into this directory to use them in Upload Assistant.

Only `regions` and `distributors` are compacted. All other sections and metadata,
including categories, types, resolutions, region labels and aliases, retain their
contents. The script verifies that expanding each compacted section reproduces
its input exactly. Legacy overrides without complete flags retain their format.

Matching IDs are recorded under `default_ids`, using individual IDs or inclusive
ranges; only added or different entries remain in the respective section:

```json
{
  "regions": { "250": "CZE" },
  "distributors": {},
  "regions_complete": true,
  "distributors_complete": true,
  "default_ids": {
    "regions": ["1-243"],
    "distributors": ["1-965"]
  }
}
```

The example references exactly regions 1–243 and distributors 1–965 from the
local default. IDs not referenced are unsupported; future additions to the
default are not inherited automatically. Changes to the values of referenced
default IDs are shared, so regenerate compacted files against the new default
when those values change. Empty complete sections without references remain
empty. Keep the full browser exports as the source for future comparisons.

`categories`, `types` and `resolutions` are currently stored for future use. No
upload classification behavior reads those sections yet. The current exporter
always writes these sections, using empty objects when their fields are absent.
Older files with a missing section have not collected it yet.

Catalogs are cached during a process. Restart Upload Assistant after changing a
catalog file. All JSONs are included in the Python package through
`pyproject.toml`. The original distributor catalogs and region maps were moved
here; rolling back the corresponding Git change restores the original layout.
