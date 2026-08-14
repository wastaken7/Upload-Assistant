// ==UserScript==
// @name         UNIT3D ID Report
// @namespace    upload-assistant
// @version      1.0.0
// @description  Export UNIT3D category, type, and resolution IDs as Markdown.
// @match        *://*/torrents*
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  const BUTTON_ID = "unit3d-export-id-report";
  const GROUPS = [
    { key: "categoryIds", title: "Category" },
    { key: "typeIds", title: "Type" },
    { key: "resolutionIds", title: "Resolution" },
  ];

  function normalizeText(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function markdownText(value) {
    return value
      .replace(/\\/g, "\\\\")
      .replace(/\|/g, "\\|")
      .replace(/\r?\n/g, " ");
  }

  function findFieldset(group) {
    return [...document.querySelectorAll("fieldset")].find((fieldset) => {
      const input = [...fieldset.querySelectorAll("input")].find(
        (candidate) => candidate.getAttribute("wire:model.live") === group.key,
      );
      return Boolean(input);
    });
  }

  function extractGroup(group) {
    const fieldset = findFieldset(group);
    if (!fieldset) {
      return [];
    }

    return [...fieldset.querySelectorAll("input")]
      .filter((input) => input.getAttribute("wire:model.live") === group.key)
      .map((input) => {
        const label = input.labels?.[0];
        const name = label ? normalizeText(label.textContent) : "";
        return { id: input.value.trim(), name };
      })
      .filter((item) => item.id && item.name);
  }

  function buildMarkdown() {
    const lines = [
      "# UNIT3D — Supported IDs",
      "",
      `- URL: ${window.location.href}`,
      `- Generated at: ${new Date().toISOString()}`,
      "",
    ];

    for (const group of GROUPS) {
      const entries = extractGroup(group);
      lines.push(`## ${group.title}`, "", "| ID | Name |", "|---:|---|");

      if (entries.length === 0) {
        lines.push("| — | No field found |");
      } else {
        for (const entry of entries) {
          lines.push(
            `| ${markdownText(entry.id)} | ${markdownText(entry.name)} |`,
          );
        }
      }
      lines.push("");
    }

    return lines.join("\n");
  }

  function downloadReport() {
    const markdown = buildMarkdown();
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const link = document.createElement("a");
    const hostname =
      window.location.hostname.replace(/[^a-z0-9.-]/gi, "_") || "unit3d";
    link.href = URL.createObjectURL(blob);
    link.download = `${hostname}-ids.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function installButton() {
    if (
      document.getElementById(BUTTON_ID) ||
      !GROUPS.some((group) => findFieldset(group))
    ) {
      return;
    }

    const button = document.createElement("button");
    button.id = BUTTON_ID;
    button.type = "button";
    button.textContent = "Export IDs (.md)";
    button.title = "Download Category, Type, and Resolution as Markdown";
    Object.assign(button.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      zIndex: "2147483647",
      padding: "10px 14px",
      border: "1px solid #fff",
      borderRadius: "6px",
      background: "#1976d2",
      color: "#fff",
      cursor: "pointer",
      font: "600 14px sans-serif",
      boxShadow: "0 2px 8px #0006",
    });
    button.addEventListener("click", downloadReport);
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
