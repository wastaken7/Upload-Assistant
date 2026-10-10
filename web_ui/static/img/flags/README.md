# Preview language flags

These 4:3 SVG assets are from [flag-icons v7.3.2](https://github.com/lipis/flag-icons/tree/v7.3.2/flags/4x3), by Panayiotis Lipiridis, distributed under the MIT license. The original copyright notice and license are included in [LICENSE](LICENSE).

The complete collection of 271 flags is bundled, including country, territory, subdivision and organization assets. They are served locally; no third-party requests or runtime dependency are required. Organization and unknown flags are not used as language fallbacks.

The additional circular Quebec flag (`ca-qc.svg`) is from [circle-flags](https://github.com/HatScripts/circle-flags/tree/379588b5da95482d6bbf10bd45644a35b0609ea6), under its included [MIT license](CIRCLE-FLAGS-LICENSE.md). The total is 272 images. Explicit Quebec labels use this flag; generic Canadian French uses Canada's flag.

Flags are representative visual hints for languages, not claims about a track's country of origin. Generic Portuguese uses Portugal and generic English uses the United Kingdom; explicitly recognized regional variants use their corresponding flag. Catalan, Basque, Galician, Welsh and Scottish Gaelic use the corresponding regional flags. Latin American Spanish (`es-419`) uses Mexico as its representative flag, including corresponding named labels. Unknown, undetermined, multilingual and constructed-language labels retain their text without a flag, as do other regions without a single country flag.

The static language table recognizes 620 languages, including ISO 639-1 and ISO 639-2/3 identifiers, bibliographic aliases, names in English, Portuguese and French, and native names where available. Explicit BCP 47 territories override representative flags; script variants use CLDR likely-subtag data. MediaInfo's raw language code is preserved alongside its display name so regional information is retained.

Language and territory data are generated from the project's existing Babel 2.17.0 (Unicode CLDR), langcodes 3.5.1 and pycountry 24.6.1 dependencies. Unicode data retain the [Unicode license](UNICODE-LICENSE); pycountry-derived ISO aliases and names retain their [LGPL 2.1 license](PYCOUNTRY-LICENSE) and [copyright notices](PYCOUNTRY-COPYRIGHT). Upstream sources: [CLDR release 46](https://github.com/unicode-org/cldr/tree/release-46), [pycountry 24.6.1](https://github.com/pycountry/pycountry/tree/24.6.1).

To regenerate the editable-source data table from the bundled flags and installed project dependencies, run `py scripts/generate_webui_language_flags.py` from the repository root, then format `web_ui/static/js/language_flags_data.js` with Prettier. Name matching is exact after case, Unicode and whitespace normalization; it does not guess a language from arbitrary text. No packages are added to the browser or server runtime.
