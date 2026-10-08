# UNIT3D Catalog Exporter

Userscript for Tampermonkey or Violentmonkey that downloads one JSON file with
the tracker catalogs available on a standard UNIT3D torrent filter page.

## Usage

1. Install [UNIT3D-catalog-exporter.user.js](./UNIT3D-catalog-exporter.user.js) in your userscript manager.
2. Open the tracker's `/torrents` page and expand its filters if necessary.
3. Click **Export catalog (.json)** near the bottom-right corner.
4. Known tracker domains automatically use the name registered in Upload Assistant.
   For other domains, enter the tracker name, such as `CAPYBARABR`, when prompted.
5. Copy the downloaded `capybarabr.json` to `data/unit3d_catalogs/`.

For example, `upload.cx` saves as `ulcx.json`, `theldu.to` as
`lastdigitalunderground.json`, and `tlzdigital.com` as `theleachzone.json`.
The domain map comes from the UNIT3D trackers registered in `src/trackersetup.py`
and their `base_url` / `tracker_urls`. Domain matching ignores a leading `www.`
and uses exact hostnames. Update the userscript's map when registered domains change.

Each section maps numeric site IDs to codes or display names:

```json
{
  "regions": { "33": "BRA" },
  "distributors": { "10001": "Example Studio" },
  "regions_complete": true,
  "distributors_complete": true,
  "categories": { "1": "Example Movies" },
  "types": { "2": "Example Encode" },
  "resolutions": { "3": "1080p" }
}
```

The IDs above are illustrative. Exported IDs always come from the site. Localized
region names are reduced to their three-letter codes. Other names retain their
original language, with whitespace normalized in checkbox labels.

All five sections are always included. When the page has no field for a section,
that section is an empty object. Regions and distributors are marked complete,
including when absent, so Upload Assistant will not inherit default options that
the site does not offer. All available choices are exported, regardless of which
are selected. The `0` / "No region" / "No distributor" placeholders are omitted.
Malformed or executable initializers, conflicting IDs and conflicting lists
prevent the download instead of producing a partial export. Repeated display
labels with different IDs are preserved.

The exporter supports UNIT3D's `myRegions` and `myDistributors` initializers
containing JSON.parse strings, literal arrays or empty array spreads, with or
without a semicolon before VirtualSelect.init. It also reads complete Alpine
triSelect configurations, native selects and Livewire checkbox labels, including
the older `categories`, `types` and `resolutions` model names. It does not scrape
VirtualSelect's visible options, which contain only part of the list. The export
button appears even when region/distributor filters are absent. Custom page
layouts may still require adaptation.

PolishTorrent country spellings are normalized to Upload Assistant region codes
while retaining the site's IDs. If the region field includes names without a
known country code, `region_labels` preserves all its original labels, including
choices such as "Other" and language/dubbing filters. `regions` contains only
recognized country codes; no code is guessed for non-country choices. Its
complete flag still prevents fallback to another site's region IDs.

Upload Assistant uses the exported regions and distributors for tracker-specific
upload IDs and metadata lookups. Categories, types and resolutions are stored for
future features and do not change existing upload classification.

When refreshing an existing tracker JSON, preserve any manually maintained
`aliases` and `excluded_aliases` from that file. The exporter cannot infer these
name equivalences from the site. See the [catalog format](../../data/unit3d_catalogs/README.md).

Export is local and triggered by a click. The file contains only catalog IDs and
names, without URLs, account details or tokens. The exporter does not evaluate
page script contents or make network requests.
