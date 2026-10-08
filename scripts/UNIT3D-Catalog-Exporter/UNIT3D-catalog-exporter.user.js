// ==UserScript==
// @name         UNIT3D Catalog Exporter
// @namespace    upload-assistant
// @version      1.2.2
// @description  Export UNIT3D regions, distributors, categories, types and resolutions as JSON.
// @match        *://*/torrents*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const BUTTON_ID = "unit3d-export-catalog";
  // Known UNIT3D domains from src/trackersetup.py and tracker base_url/tracker_urls.
  const TRACKER_HOSTNAMES = {
    "aither.cc": "aither",
    "bitporn.eu": "bitporn",
    "blutopia.cc": "blutopia",
    "capybarabr.com": "capybarabr",
    "cinematik.net": "cinematik",
    "darkpeers.org": "darkpeers",
    "dreadvault.org": "dreadvault",
    "eiga.moi": "asiancinema",
    "emuwarez.com": "emuwarez",
    "hawke.uno": "hawkeuno",
    "homiehelpdesk.net": "homiehelpdesk",
    "infinityhd.net": "infinityhd",
    "itatorrents.xyz": "itatorrents",
    "lat-team.com": "latteam",
    "locadora.cc": "locadora",
    "lst.gg": "lst",
    "luminarr.me": "luminarr",
    "midnightscene.cc": "midnightscene",
    "nordicq.org": "nordicquality",
    "oldtoons.world": "oldtoonsworld",
    "onlyencodes.cc": "onlyencodes",
    "peergarden.org": "peergarden",
    "polishtorrent.top": "polishtorrent",
    "portugas.org": "portugas",
    "racing4everyone.eu": "racing4everyone",
    "rastastugan.org": "rastastugan",
    "reelflix.cc": "reelflix",
    "reelflix.xyz": "reelflix",
    "retro-movies.club": "retromoviesclub",
    "rocket-hd.cc": "rockethd",
    "samaritano.cc": "samaritano",
    "seedpool.org": "seedpool",
    "shareisland.org": "shareisland",
    "skipthecommercials.xyz": "skipthecommercials",
    "theldu.to": "lastdigitalunderground",
    "theoldschool.cc": "theoldschool",
    "tlzdigital.com": "theleachzone",
    "torrent.desi": "desitorrents",
    "torrenteros.org": "torrenteros",
    "torrenthr.org": "torrenthr",
    "upload.cx": "ulcx",
    "utp.to": "utopia",
    "yu-scene.net": "yuscene",
    "znth.cx": "zenith",
  };

  // Decode a quoted JavaScript string as data, without evaluating page code.
  function decodeString(literal) {
    const escapes = { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", v: "\v" };
    let result = "";
    for (let index = 1; index < literal.length - 1; index++) {
      let character = literal[index];
      if (character === "\\") {
        character = literal[++index];
        if (character === "u" || character === "x") {
          const length = character === "u" ? 4 : 2;
          const hex = literal.slice(index + 1, index + 1 + length);
          if (!new RegExp(`^[0-9a-f]{${length}}$`, "i").test(hex)) {
            throw new Error("Invalid escape in catalog data.");
          }
          result += String.fromCharCode(parseInt(hex, 16));
          index += length;
          continue;
        }
        if (
          !["\\", "'", '"', "/", ...Object.keys(escapes)].includes(character)
        ) {
          throw new Error("Unsupported escape in catalog data.");
        }
        character = escapes[character] ?? character;
      }
      result += character;
    }
    return result;
  }

  const GROUPS = [
    {
      key: "regions",
      models: ["regionIds", "regions"],
      variable: "myRegions",
      selector: "select#region_id, select[name='region_id'], select#regions",
    },
    {
      key: "distributors",
      models: ["distributorIds", "distributors"],
      variable: "myDistributors",
      selector:
        "select#distributor_id, select[name='distributor_id'], select#distributors",
    },
    {
      key: "categories",
      models: ["categoryIds", "categories"],
      selector: "select#category_id, select[name='category_id']",
    },
    {
      key: "types",
      models: ["typeIds", "types"],
      selector: "select#type_id, select[name='type_id']",
    },
    {
      key: "resolutions",
      models: ["resolutionIds", "resolutions"],
      selector: "select#resolution_id, select[name='resolution_id']",
    },
  ];

  // These localized country spellings occur in PolishTorrent's region catalog.
  // Non-country choices stay in region_labels and are never assigned guessed IDs.
  const REGION_ALIASES = {
    ARGENTYNA: "ARG",
    AUSTRALIA: "AUS",
    AUTRALIA: "AUS",
    BRAZYLIA: "BRA",
    BULGARIA: "BGR",
    CZECHY: "CZE",
    CHINY: "CHN",
    DANIA: "DNK",
    FILIPINY: "PHI",
    FRANCJA: "FRA",
    HISZPANIA: "ESP",
    HOLANDIA: "NLD",
    HONGKONG: "HKG",
    HONKONG: "HKG",
    INDIE: "IND",
    IRLANDIA: "IRL",
    INDONEZJA: "IDN",
    IZRAEL: "ISR",
    JAPONIA: "JPN",
    KANADA: "CAN",
    KOLUMBIA: "COL",
    "KOREA POLUDNIOWA": "KOR",
    LITWA: "LTU",
    LOTWA: "LVA",
    MEKSYK: "MEX",
    NIEMCY: "GER",
    NORWEGIA: "NOR",
    POLSKA: "POL",
    PORTUGALIA: "POR",
    RPA: "RSA",
    ROSJA: "RUS",
    SZWECJA: "SWE",
    TURCJA: "TUR",
    UKRAINA: "UKR",
    UK: "GBR",
    WEGRY: "HUN",
    WLOCHY: "ITA",
  };

  function regionCode(label) {
    const explicit = /^([A-Z]{3})(?:\s*\([^\r\n]*\))?$/.exec(label)?.[1];
    if (explicit) return explicit;
    const name = label
      .replace(/\s*\([^\r\n]*\)$/, "")
      .trim()
      .toUpperCase()
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .replace(/Ł/g, "L");
    return REGION_ALIASES[name] ?? null;
  }

  // Parse the data-only subset used by UNIT3D initializers. No eval/Function:
  // strings, numbers, objects, arrays, array spreads and JSON.parse(string).
  function readData(source) {
    let position = 0;
    function skip() {
      while (/\s/.test(source[position] ?? "") && position < source.length)
        position++;
    }
    function consume(expected) {
      skip();
      if (!source.startsWith(expected, position))
        throw new Error(
          "Unsupported catalog initializer; no file was generated.",
        );
      position += expected.length;
    }
    function string() {
      skip();
      const start = position;
      const quote = source[position++];
      while (position < source.length) {
        if (source[position] === "\\") {
          position += 2;
          continue;
        }
        if (source[position++] === quote)
          return decodeString(source.slice(start, position));
      }
      throw new Error("Unterminated catalog string.");
    }
    function value() {
      skip();
      if (source[position] === "'" || source[position] === '"') return string();
      if (source.startsWith("JSON.parse", position)) {
        consume("JSON.parse");
        consume("(");
        skip();
        if (!["'", '"'].includes(source[position]))
          throw new Error("Catalog JSON.parse must contain a literal string.");
        const result = JSON.parse(string());
        consume(")");
        return result;
      }
      if (source[position] === "[") {
        position++;
        const items = [];
        skip();
        while (source[position] !== "]") {
          if (source.startsWith("...", position)) {
            position += 3;
            const spread = value();
            if (!Array.isArray(spread))
              throw new Error("Catalog spread is not a list.");
            for (const item of spread) items.push(item);
          } else {
            items.push(value());
          }
          skip();
          if (source[position] === "]") break;
          consume(",");
          skip();
        }
        consume("]");
        return items;
      }
      if (source[position] === "{") {
        position++;
        const object = Object.create(null);
        skip();
        while (source[position] !== "}") {
          let key;
          if (["'", '"'].includes(source[position])) {
            key = string();
          } else {
            const match = /^(?:[A-Za-z_$][\w$]*|\d+)/.exec(source.slice(position));
            if (!match) throw new Error("Invalid catalog object key.");
            key = match[0];
            position += key.length;
          }
          if (Object.hasOwn(object, key))
            throw new Error("Duplicate catalog object key.");
          consume(":");
          object[key] = value();
          skip();
          if (source[position] === "}") break;
          consume(",");
          skip();
        }
        consume("}");
        return object;
      }
      const scalar = /^(?:-?\d+(?:\.\d+)?|true|false|null)\b/.exec(
        source.slice(position),
      );
      if (!scalar)
        throw new Error("Unsupported executable expression in catalog data.");
      position += scalar[0].length;
      return JSON.parse(scalar[0]);
    }
    const result = value();
    const end = position;
    skip();
    return {
      value: result,
      rest: source.slice(position),
      newline: /[\r\n]/.test(source.slice(end, position)),
    };
  }

  function buildCatalog(options, key) {
    if (!Array.isArray(options)) throw new Error("Catalog data is not a list.");
    const entries = {};
    const regionLabels = {};
    const rawEntries = {};
    const codes = new Set();
    for (const option of options) {
      const id = String(option?.value ?? "").trim();
      if (id === "0") continue;
      const label = String(option?.label ?? "")
        .replace(/\s+/g, " ")
        .trim();
      if (!/^[1-9]\d*$/.test(id) || !label)
        throw new Error(`Cannot export entry '${label}': invalid ID or label.`);
      if (Object.hasOwn(rawEntries, id)) {
        if (rawEntries[id] !== label)
          throw new Error(`Conflicting catalog ID: ${id}.`);
        continue; // The same control can appear more than once on a page.
      }
      rawEntries[id] = label;
      if (key === "regions") {
        const code = regionCode(label);
        regionLabels[id] = label;
        if (!code) continue;
        if (codes.has(code)) throw new Error(`Duplicate region code: ${code}.`);
        codes.add(code);
        entries[id] = code;
      } else {
        entries[id] = label;
      }
    }
    return { entries, regionLabels };
  }

  function matchesModel(element, group) {
    return ["wire:model.live", "wire:model", "wire:model.defer"].some(
      (attribute) => group.models.includes(element.getAttribute(attribute)),
    );
  }

  function extractGroup(group) {
    // Read full data sources, never the visible window of VirtualSelect options.
    const sources = [];
    if (group.variable) {
      for (const script of document.querySelectorAll("script")) {
        const pattern = new RegExp(
          `\\b(?:let|const|var)\\s+${group.variable}\\s*=\\s*`,
          "g",
        );
        for (const match of script.textContent.matchAll(pattern)) {
          const parsed = readData(
            script.textContent.slice(match.index + match[0].length),
          );
          if (
            parsed.rest &&
            !parsed.rest.startsWith(";") &&
            !(parsed.newline && /^VirtualSelect\.init\b/.test(parsed.rest))
          )
            throw new Error("Unsupported catalog assignment suffix.");
          sources.push(buildCatalog(parsed.value, group.key));
        }
      }
    }
    for (const element of document.querySelectorAll("[x-data]")) {
      const expression = element.getAttribute("x-data").trim();
      if (!expression.startsWith("triSelect(")) continue;
      const parsed = readData(expression.slice("triSelect(".length));
      if (parsed.rest !== ")")
        throw new Error("Unsupported triSelect catalog initializer.");
      if (group.models.includes(parsed.value?.includeModel))
        sources.push(buildCatalog(parsed.value.options, group.key));
    }
    for (const select of document.querySelectorAll("select")) {
      if (select.matches(group.selector) || matchesModel(select, group)) {
        sources.push(
          buildCatalog(
            [...select.options]
              .filter((option) => option.value !== "")
              .map((option) => ({
                value: option.value,
                label: option.textContent,
              })),
            group.key,
          ),
        );
      }
    }
    const inputs = [...document.querySelectorAll("input")].filter((input) =>
      matchesModel(input, group),
    );
    if (inputs.length) {
      sources.push(
        buildCatalog(
          inputs.map((input) => ({
            value: input.value,
            label: input.labels?.[0]?.textContent ?? "",
          })),
          group.key,
        ),
      );
    }
    if (
      sources.some((source) =>
        ["entries", "regionLabels"].some((section) => {
          const expected = sources[0][section];
          const actual = source[section];
          return (
            Object.keys(actual).length !== Object.keys(expected).length ||
            Object.entries(actual).some(
              ([id, label]) =>
                !Object.hasOwn(expected, id) || expected[id] !== label,
            )
          );
        }),
      )
    )
      throw new Error(
        `Conflicting ${group.key} lists found. Reload the page before exporting.`,
      );
    return sources[0] ?? { entries: {}, regionLabels: {} };
  }

  function extractCatalog() {
    const catalog = {};
    for (const group of GROUPS) {
      const result = extractGroup(group);
      catalog[group.key] = result.entries;
      if (
        group.key === "regions" &&
        Object.keys(result.regionLabels).some(
          (id) => !Object.hasOwn(result.entries, id),
        )
      ) {
        catalog.region_labels = result.regionLabels;
      }
    }
    catalog.regions_complete = true;
    catalog.distributors_complete = true;
    return catalog;
  }

  function downloadCatalog() {
    try {
      const catalog = extractCatalog();
      const hostname = window.location.hostname
        .toLowerCase()
        .replace(/\.$/, "")
        .replace(/^www\./, "");
      const tracker = Object.hasOwn(TRACKER_HOSTNAMES, hostname)
        ? TRACKER_HOSTNAMES[hostname]
        : window.prompt(
            "Tracker name used in Upload Assistant (for example: CAPYBARABR):",
            hostname.split(".")[0],
          );
      if (tracker === null) return;
      const name = tracker.trim().toLowerCase();
      if (!/^[a-z0-9][a-z0-9_-]*$/.test(name)) {
        throw new Error(
          "Use only letters, digits, underscores or hyphens for the tracker name.",
        );
      }
      const blob = new Blob([JSON.stringify(catalog, null, 2) + "\n"], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${name}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      window.alert(`Catalog export failed: ${error.message}`);
    }
  }

  function installButton() {
    if (document.getElementById(BUTTON_ID) || !document.body) return;
    const button = document.createElement("button");
    button.id = BUTTON_ID;
    button.type = "button";
    button.textContent = "Export catalog (.json)";
    Object.assign(button.style, {
      position: "fixed",
      right: "16px",
      bottom: "64px",
      zIndex: "2147483647",
      padding: "10px 14px",
      border: "1px solid #fff",
      borderRadius: "6px",
      background: "#1976d2",
      color: "#fff",
      cursor: "pointer",
      font: "600 14px sans-serif",
    });
    button.addEventListener("click", downloadCatalog);
    document.body.appendChild(button);
  }

  function start() {
    installButton();
    new MutationObserver(installButton).observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
