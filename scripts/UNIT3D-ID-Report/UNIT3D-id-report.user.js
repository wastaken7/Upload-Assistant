// ==UserScript==
// @name         UNIT3D ID Report & Diff Exporter
// @namespace    upload-assistant
// @version      2.0.0
// @description  Extracts UNIT3D category, type, resolution, region, genre, and distributor IDs in sorted JSON format, compares them against Upload-Assistant standard defaults from GitHub, and exports only tracker-specific differences.
// @match        *://*/torrents*
// @match        *://*/upload*
// @match        *://*/torrents/upload*
// @match        file:///*
// @grant        GM_xmlhttpRequest
// @grant        GM.xmlHttpRequest
// @connect      raw.githubusercontent.com
// @connect      githubusercontent.com
// ==/UserScript==

(function () {
  "use strict";

  const GITHUB_DEFAULTS_URL =
    "https://raw.githubusercontent.com/wastaken7/Upload-Assistant/development/data/unit3d_default_ids.json";

  const EMBEDDED_DEFAULTS = {
    categories: {
      Movie: "1",
      TV: "2",
    },
    types: {
      Encode: "3",
      "Full Disc": "1",
      HDTV: "6",
      Remux: "2",
      "WEB-DL": "4",
      WEBRip: "5",
    },
    resolutions: {
      "1080i": "4",
      "1080p": "3",
      "2160p": "2",
      "4320p": "1",
      "480i": "9",
      "480p": "8",
      "576i": "7",
      "576p": "6",
      "720p": "5",
      Other: "10",
    },
    genres: {
      Action: "28",
      "Action & Adventure": "10759",
      Adventure: "12",
      Animation: "16",
      Comedy: "35",
      Crime: "80",
      Documentary: "99",
      Drama: "18",
      Family: "10751",
      Fantasy: "14",
      History: "36",
      Horror: "27",
      Kids: "10762",
      Music: "10402",
      Musical: "22",
      Mystery: "9648",
      News: "10763",
      Reality: "10764",
      Romance: "10749",
      "Sci-Fi & Fantasy": "10765",
      "Science Fiction": "878",
      Soap: "10766",
      Talk: "10767",
      "TV Movie": "10770",
      Thriller: "53",
      War: "10752",
      "War & Politics": "10768",
      Western: "37",
    },
  };

  const FIELD_SPECS = [
    {
      group: "categories",
      title: "Categories",
      wireKeys: ["categoryIds", "categories", "category_id"],
      selectNames: ["category_id", "categories[]", "categoryIds[]"],
    },
    {
      group: "types",
      title: "Types",
      wireKeys: ["typeIds", "types", "type_id"],
      selectNames: ["type_id", "types[]", "typeIds[]"],
    },
    {
      group: "resolutions",
      title: "Resolutions",
      wireKeys: ["resolutionIds", "resolutions", "resolution_id"],
      selectNames: ["resolution_id", "resolutions[]", "resolutionIds[]"],
    },
    {
      group: "regions",
      title: "Regions",
      wireKeys: ["regionIds", "regions", "region_id"],
      selectNames: ["region_id", "regions[]", "regionIds[]"],
    },
    {
      group: "genres",
      title: "Genres",
      wireKeys: ["genreIds", "genres", "genre_id"],
      selectNames: ["genre_id", "genres[]", "genreIds[]"],
    },
    {
      group: "distributors",
      title: "Distributors",
      wireKeys: ["distributorIds", "distributor_id"],
      selectNames: ["distributor_id", "distributors[]", "distributorIds[]"],
    },
    {
      group: "mediums",
      title: "Mediums / Formats",
      wireKeys: ["medium_id", "format_id"],
      selectNames: ["medium_id", "format_id"],
    },
    {
      group: "editions",
      title: "Editions",
      wireKeys: ["edition_id", "editionIds"],
      selectNames: ["edition_id", "editions[]"],
    },
  ];

  function normalizeText(value) {
    if (!value) return "";
    return value.replace(/\s+/g, " ").trim();
  }

  function sortObjectAlphabetically(obj) {
    const sorted = {};
    const keys = Object.keys(obj).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base", numeric: true })
    );
    for (const key of keys) {
      sorted[key] = obj[key];
    }
    return sorted;
  }

  function extractGroupData(spec) {
    const results = {};

    // 1. Check livewire / alpine inputs
    for (const wireKey of spec.wireKeys) {
      const inputs = [
        ...document.querySelectorAll(
          `input[wire\\:model\\.live="${wireKey}"], input[wire\\:model="${wireKey}"], input[wire\\:model\\.defer="${wireKey}"]`
        ),
      ];

      for (const input of inputs) {
        const val = input.value?.trim();
        if (!val) continue;

        let label = input.labels?.[0];
        if (!label && input.id) {
          label = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
        }
        if (!label) {
          label = input.closest("label");
        }

        const name = label ? normalizeText(label.textContent) : "";
        if (name && val) {
          results[name] = String(val);
        }
      }
    }

    // 2. Check standard select elements
    for (const selectName of spec.selectNames) {
      const selects = [
        ...document.querySelectorAll(
          `select[name="${selectName}"], select#${CSS.escape(selectName)}`
        ),
      ];

      for (const select of selects) {
        for (const option of select.options) {
          const val = option.value?.trim();
          const name = normalizeText(option.textContent);
          if (val && name && val !== "0" && val !== "" && !/select|choose/i.test(name)) {
            results[name] = String(val);
          }
        }
      }
    }

    // 3. Check inputs by name or id attribute
    for (const nameAttr of spec.selectNames) {
      const inputs = [
        ...document.querySelectorAll(
          `input[name="${nameAttr}"], input[name="${nameAttr}[]"]`
        ),
      ];

      for (const input of inputs) {
        const val = input.value?.trim();
        if (!val) continue;

        let label = input.labels?.[0];
        if (!label && input.id) {
          label = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
        }
        if (!label) {
          label = input.closest("label");
        }

        const name = label ? normalizeText(label.textContent) : "";
        if (name && val) {
          results[name] = String(val);
        }
      }
    }

    return sortObjectAlphabetically(results);
  }

  function extractAllIds() {
    const all = {};
    for (const spec of FIELD_SPECS) {
      const data = extractGroupData(spec);
      if (Object.keys(data).length > 0) {
        all[spec.group] = data;
      }
    }
    return sortObjectAlphabetically(all);
  }

  async function fetchCodebaseDefaults() {
    return new Promise((resolve) => {
      const handleSuccess = (responseText) => {
        try {
          const parsed = JSON.parse(responseText);
          resolve(parsed);
        } catch {
          resolve(EMBEDDED_DEFAULTS);
        }
      };

      const requester =
        typeof GM_xmlhttpRequest !== "undefined"
          ? GM_xmlhttpRequest
          : typeof GM !== "undefined" && GM.xmlHttpRequest
          ? GM.xmlHttpRequest
          : null;

      if (requester) {
        requester({
          method: "GET",
          url: GITHUB_DEFAULTS_URL,
          headers: { "Cache-Control": "no-cache" },
          onload: (response) => {
            if (response.status >= 200 && response.status < 300) {
              handleSuccess(response.responseText);
            } else {
              resolve(EMBEDDED_DEFAULTS);
            }
          },
          onerror: () => resolve(EMBEDDED_DEFAULTS),
          ontimeout: () => resolve(EMBEDDED_DEFAULTS),
        });
      } else {
        fetch(GITHUB_DEFAULTS_URL, { cache: "no-store" })
          .then((res) => (res.ok ? res.json() : EMBEDDED_DEFAULTS))
          .then((data) => resolve(data))
          .catch(() => resolve(EMBEDDED_DEFAULTS));
      }
    });
  }

  function computeDiff(extracted, defaults) {
    const diff = {};

    for (const [groupKey, items] of Object.entries(extracted)) {
      const defaultGroup = defaults[groupKey] || {};
      const defaultMapLower = {};
      for (const [defName, defId] of Object.entries(defaultGroup)) {
        defaultMapLower[defName.trim().toLowerCase()] = String(defId).trim();
      }

      const groupDiff = {};
      for (const [name, id] of Object.entries(items)) {
        const cleanName = name.trim();
        const cleanId = String(id).trim();
        const lowerName = cleanName.toLowerCase();

        if (!(lowerName in defaultMapLower)) {
          // Custom / tracker-specific ID not in UNIT3D defaults
          groupDiff[cleanName] = cleanId;
        } else if (defaultMapLower[lowerName] !== cleanId) {
          // ID value differs from standard default
          groupDiff[cleanName] = cleanId;
        }
      }

      if (Object.keys(groupDiff).length > 0) {
        diff[groupKey] = sortObjectAlphabetically(groupDiff);
      }
    }

    return sortObjectAlphabetically(diff);
  }

  function downloadJson(filename, obj) {
    const jsonStr = JSON.stringify(obj, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function getSiteHostname() {
    if (window.location.protocol === "file:") {
      const pathParts = window.location.pathname.split(/[/\\\\]/);
      const fileName = pathParts[pathParts.length - 1] || "unit3d";
      return fileName.replace(/\.html?$/i, "").replace(/[^a-z0-9_-]/gi, "_");
    }
    return window.location.hostname.replace(/[^a-z0-9.-]/gi, "_") || "unit3d";
  }

  async function exportDiffJson() {
    const button = document.getElementById("unit3d-export-diff-btn");
    if (button) button.textContent = "⏳ Comparing...";

    const extracted = extractAllIds();
    const defaults = await fetchCodebaseDefaults();
    const diff = computeDiff(extracted, defaults);

    const hostname = getSiteHostname();
    const diffCount = Object.values(diff).reduce(
      (acc, g) => acc + Object.keys(g).length,
      0
    );

    downloadJson(`${hostname}-custom-ids.json`, diff);

    if (button) {
      button.textContent = `✓ Diff Exported (${diffCount} custom)`;
      setTimeout(() => {
        button.textContent = "⚡ Export Diff JSON";
      }, 3000);
    }
  }

  function exportFullJson() {
    const extracted = extractAllIds();
    const hostname = getSiteHostname();
    downloadJson(`${hostname}-all-ids.json`, extracted);
  }

  function buildMarkdownReport(extracted, diff) {
    const lines = [
      `# UNIT3D ID Report — ${getSiteHostname()}`,
      "",
      `- URL: ${window.location.href}`,
      `- Date: ${new Date().toISOString()}`,
      "",
      "## Tracker-Specific Differences (vs UNIT3D Standard)",
      "",
    ];

    if (Object.keys(diff).length === 0) {
      lines.push("*(No custom differences found — matches standard UNIT3D defaults)*", "");
    } else {
      for (const [group, items] of Object.entries(diff)) {
        lines.push(`### ${group.toUpperCase()} (Custom / Overrides)`, "", "| Name | Tracker ID |", "|---|---:|");
        for (const [k, v] of Object.entries(items)) {
          lines.push(`| ${k} | ${v} |`);
        }
        lines.push("");
      }
    }

    lines.push("## Full Extracted IDs", "");
    for (const [group, items] of Object.entries(extracted)) {
      lines.push(`### ${group.toUpperCase()}`, "", "| Name | ID |", "|---|---:|");
      for (const [k, v] of Object.entries(items)) {
        lines.push(`| ${k} | ${v} |`);
      }
      lines.push("");
    }

    return lines.join("\n");
  }

  async function exportMarkdown() {
    const extracted = extractAllIds();
    const defaults = await fetchCodebaseDefaults();
    const diff = computeDiff(extracted, defaults);
    const md = buildMarkdownReport(extracted, diff);

    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${getSiteHostname()}-ids.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function installUI() {
    if (document.getElementById("unit3d-id-tools-panel")) {
      return;
    }

    const extracted = extractAllIds();
    if (Object.keys(extracted).length === 0) {
      return;
    }

    const container = document.createElement("div");
    container.id = "unit3d-id-tools-panel";
    Object.assign(container.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      zIndex: "2147483647",
      display: "flex",
      flexDirection: "column",
      gap: "6px",
      padding: "10px",
      background: "rgba(20, 24, 33, 0.95)",
      border: "1px solid rgba(255, 255, 255, 0.2)",
      borderRadius: "8px",
      boxShadow: "0 4px 16px rgba(0, 0, 0, 0.6)",
      fontFamily: "system-ui, -apple-system, sans-serif",
      backdropFilter: "blur(6px)",
    });

    const title = document.createElement("div");
    title.textContent = "UNIT3D ID Tools";
    Object.assign(title.style, {
      color: "#e2e8f0",
      fontSize: "12px",
      fontWeight: "700",
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      marginBottom: "2px",
    });
    container.appendChild(title);

    const createBtn = (id, text, titleText, bg, onClick) => {
      const btn = document.createElement("button");
      btn.id = id;
      btn.type = "button";
      btn.textContent = text;
      btn.title = titleText;
      Object.assign(btn.style, {
        padding: "7px 12px",
        border: "none",
        borderRadius: "5px",
        background: bg,
        color: "#ffffff",
        cursor: "pointer",
        fontSize: "13px",
        fontWeight: "600",
        textAlign: "left",
        transition: "all 0.15s ease",
      });
      btn.addEventListener("mouseenter", () => (btn.style.filter = "brightness(1.15)"));
      btn.addEventListener("mouseleave", () => (btn.style.filter = "none"));
      btn.addEventListener("click", onClick);
      return btn;
    };

    const diffBtn = createBtn(
      "unit3d-export-diff-btn",
      "⚡ Export Diff JSON",
      "Export only IDs that differ from standard Upload-Assistant defaults",
      "#2563eb",
      exportDiffJson
    );
    container.appendChild(diffBtn);

    const fullBtn = createBtn(
      "unit3d-export-full-btn",
      "📦 Export All JSON",
      "Export all extracted IDs in sorted JSON format",
      "#475569",
      exportFullJson
    );
    container.appendChild(fullBtn);

    const mdBtn = createBtn(
      "unit3d-export-md-btn",
      "📝 Export Markdown",
      "Export full and diff report as Markdown",
      "#334155",
      exportMarkdown
    );
    container.appendChild(mdBtn);

    document.body.appendChild(container);
  }

  function start() {
    installUI();
    new MutationObserver(installUI).observe(document.documentElement, {
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
