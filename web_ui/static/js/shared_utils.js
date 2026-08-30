// Shared utility for storage and theme handling used by multiple UI scripts.
(() => {
  const THEME_KEY = "ua_config_theme";
  const COLOR_THEME_KEY = "ua_color_theme";
  const INTERFACE_STYLE_KEY = "ua_interface_style";
  const DEFAULT_COLOR_THEME = "charcoal";
  const DEFAULT_INTERFACE_STYLE = "square";
  const UA_THEMES = Object.freeze([
    {
      id: "amethyst",
      label: "Amethyst",
      description: "Slate purple and lavender",
    },
    {
      id: "charcoal",
      label: "Charcoal",
      description: "Neutral charcoal and blue",
    },
    {
      id: "evergreen",
      label: "Evergreen",
      description: "Deep green and teal",
    },
    { id: "graphite", label: "Graphite", description: "Cool blue graphite" },
    {
      id: "midnight",
      label: "Midnight",
      description: "Near-black and indigo",
    },
    { id: "obsidian", label: "Obsidian", description: "Copper and gold" },
  ]);
  const UA_INTERFACE_STYLES = Object.freeze([
    { id: "rounded", label: "Rounded" },
    { id: "square", label: "Square" },
  ]);
  const UA_HELP_RESOURCE_GROUPS = Object.freeze([
    {
      title: "Start here",
      links: [
        {
          label: "Documentation home",
          description: "Overview and links to the main guides.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/home.md",
        },
        {
          label: "WebUI guide",
          description: "Complete WebUI setup, usage and administration.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/web-ui.md",
        },
      ],
    },
    {
      title: "Configuration",
      links: [
        {
          label: "Configuration reference",
          description: "Detailed settings, defaults and implementation notes.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/example-config.md",
        },
        {
          label: "CLI arguments",
          description: "Command-line options that can override configuration.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/cli-args.md",
        },
        {
          label: "Description builder",
          description: "How description formatting and layout options work.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/description-builder.md",
        },
      ],
    },
    {
      title: "Installation and hosting",
      links: [
        {
          label: "Windows installation",
          description: "Install and run Upload Assistant on Windows.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/windows-install.md",
        },
        {
          label: "Docker",
          description: "Container setup and configuration.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/docker.md",
        },
        {
          label: "Unraid",
          description: "Deployment guidance for Unraid.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/unraid.md",
        },
        {
          label: "Seedbox setup",
          description: "Paths and setup considerations for seedboxes.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/seedbox.md",
        },
      ],
    },
    {
      title: "Upload workflows",
      links: [
        {
          label: "Usenet",
          description: "Configure and use Usenet uploading.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/usenet.md",
        },
        {
          label: "Book uploads",
          description: "Book-specific preparation and uploading.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/book-upload.md",
        },
        {
          label: "Music uploads",
          description: "Music-specific preparation and uploading.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/music-upload.md",
        },
        {
          label: "Game uploads",
          description: "Game-specific preparation and uploading.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/game-upload.md",
        },
      ],
    },
  ]);
  const UA_THEME_IDS = new Set(UA_THEMES.map((theme) => theme.id));
  const UA_INTERFACE_STYLE_IDS = new Set(
    UA_INTERFACE_STYLES.map((style) => style.id),
  );

  const uaStorage = {
    get(key) {
      try {
        return localStorage.getItem(key);
      } catch (error) {
        return null;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch (error) {
        // Ignore storage failures (private mode, blocked storage, etc.).
      }
    },
    remove(key) {
      try {
        localStorage.removeItem(key);
      } catch (error) {
        // Ignore storage failures.
      }
    },
  };

  function getUAStoredTheme() {
    const stored = uaStorage.get(THEME_KEY);
    if (stored === "dark") return true;
    if (stored === "light") return false;
    return typeof window !== "undefined" &&
      typeof window.UA_DEFAULT_THEME === "boolean"
      ? window.UA_DEFAULT_THEME
      : true;
  }

  function getUAStoredColorTheme() {
    const stored = uaStorage.get(COLOR_THEME_KEY);
    if (stored === "dark") {
      uaStorage.set(COLOR_THEME_KEY, "charcoal");
      return "charcoal";
    }
    return UA_THEME_IDS.has(stored) ? stored : DEFAULT_COLOR_THEME;
  }

  function applyUAColorTheme(themeId = getUAStoredColorTheme()) {
    const nextTheme = UA_THEME_IDS.has(themeId) ? themeId : DEFAULT_COLOR_THEME;
    if (typeof document !== "undefined") {
      document.documentElement.dataset.uaTheme = nextTheme;
    }
    return nextTheme;
  }

  function setUAColorTheme(themeId) {
    const nextTheme = applyUAColorTheme(themeId);
    uaStorage.set(COLOR_THEME_KEY, nextTheme);
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("ua-theme-change", { detail: { theme: nextTheme } }),
      );
    }
    return nextTheme;
  }

  function getUAStoredInterfaceStyle() {
    const stored = uaStorage.get(INTERFACE_STYLE_KEY);
    return UA_INTERFACE_STYLE_IDS.has(stored)
      ? stored
      : DEFAULT_INTERFACE_STYLE;
  }

  function applyUAInterfaceStyle(styleId = getUAStoredInterfaceStyle()) {
    const nextStyle = UA_INTERFACE_STYLE_IDS.has(styleId)
      ? styleId
      : DEFAULT_INTERFACE_STYLE;
    if (typeof document !== "undefined") {
      document.documentElement.dataset.uaShape = nextStyle;
    }
    return nextStyle;
  }

  function setUAInterfaceStyle(styleId) {
    const nextStyle = applyUAInterfaceStyle(styleId);
    uaStorage.set(INTERFACE_STYLE_KEY, nextStyle);
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("ua-shape-change", {
          detail: { style: nextStyle },
        }),
      );
    }
    return nextStyle;
  }

  applyUAColorTheme();
  applyUAInterfaceStyle();

  // CSRF + apiFetch helpers with automatic refresh on 401/403 responses.
  let uaCsrfToken = window.UA_CSRF_TOKEN ? String(window.UA_CSRF_TOKEN) : null;
  let uaCsrfRequest = null;

  async function loadCsrfToken(force = false) {
    if (uaCsrfToken && !force) return;
    if (uaCsrfRequest) return uaCsrfRequest;
    uaCsrfRequest = (async () => {
      try {
        const r = await fetch("/api/csrf_token", {
          credentials: "same-origin",
          cache: "no-store",
        });
        if (!r.ok) return;
        const d = await r.json();
        uaCsrfToken = d && d.csrf_token ? String(d.csrf_token) : null;
      } catch (e) {
        // The protected request will surface the authentication error.
      } finally {
        uaCsrfRequest = null;
      }
    })();
    return uaCsrfRequest;
  }

  function clearCsrfToken() {
    uaCsrfToken = null;
  }

  async function uaApiFetch(url, options = {}, retryOnAuthFail = true) {
    await loadCsrfToken();
    const headers = { ...(options.headers || {}) };
    if (uaCsrfToken) headers["X-CSRF-Token"] = uaCsrfToken;
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    if (
      retryOnAuthFail &&
      (response.status === 401 || response.status === 403)
    ) {
      // Attempt a single refresh and retry
      clearCsrfToken();
      await loadCsrfToken(true);
      const headers2 = { ...(options.headers || {}) };
      if (uaCsrfToken) headers2["X-CSRF-Token"] = uaCsrfToken;
      return fetch(url, {
        ...options,
        headers: headers2,
        credentials: "same-origin",
      });
    }
    return response;
  }

  async function loadUAUpdateStatus(force = false) {
    const endpoint = force
      ? "/api/update_status?refresh=1"
      : "/api/update_status";
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await uaApiFetch(endpoint, {
        cache: "no-store",
        signal: controller.signal,
      });
      const status = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(status?.error || "The update check failed.");
      }
      if (!status || typeof status !== "object") {
        throw new Error("The update checker returned an invalid response.");
      }
      return status;
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error(
          "The update check timed out. Check the server’s internet connection and try again.",
        );
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function loadUAChangelog(force = false) {
    const endpoint = force ? "/api/changelog?refresh=1" : "/api/changelog";
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await uaApiFetch(endpoint, {
        cache: "no-store",
        signal: controller.signal,
      });
      const history = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(history?.error || "The changelog request failed.");
      }
      if (!history || typeof history !== "object") {
        throw new Error("The changelog returned an invalid response.");
      }
      return history;
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error(
          "The changelog request timed out. Check the server’s internet connection and try again.",
        );
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function getUADismissedUpdateVersion() {
    return uaStorage.get("ua_dismissed_update_version") || "";
  }

  function dismissUAUpdateVersion(version) {
    if (version) uaStorage.set("ua_dismissed_update_version", String(version));
  }

  const UA_CHANGELOG_AREAS = Object.freeze([
    { id: "all", label: "All" },
    { id: "webui", label: "WebUI" },
    { id: "core", label: "Core" },
    { id: "trackers", label: "Trackers" },
    { id: "configuration", label: "Configuration" },
  ]);
  const UA_CHANGELOG_TYPES = Object.freeze({
    feat: "Feature",
    fix: "Fix",
    perf: "Performance",
    refactor: "Refactor",
    docs: "Documentation",
    chore: "Maintenance",
    build: "Build",
    ci: "CI",
    test: "Tests",
    style: "Style",
    revert: "Revert",
  });
  const UA_TRACKER_SCOPES = new Set([
    "alpharatio",
    "amigosshare",
    "anthelion",
    "beyondhd",
    "bithdtv",
    "bjshare",
    "brasiltracker",
    "broadcasthenet",
    "cathoderaytube",
    "digitalcore",
    "filelist",
    "funfile",
    "greatposterwall",
    "hdbits",
    "hdspace",
    "hdtorrents",
    "immortalseed",
    "iptorrents",
    "makingoff",
    "mteam",
    "nebulance",
    "orpheus",
    "passthepopcorn",
    "pterclub",
    "ptp",
    "ptskit",
    "retroflix",
    "speedapp",
    "swarmazon",
    "torrentleech",
    "totheglory",
    "tvchaosuk",
  ]);
  const UA_CORE_SCOPES = new Set([
    "api",
    "app",
    "auth",
    "book",
    "books",
    "cache",
    "cli",
    "client",
    "clients",
    "core",
    "database",
    "db",
    "dependencies",
    "dependency",
    "description",
    "docker",
    "docs",
    "ffmpeg",
    "filesystem",
    "game",
    "games",
    "get_desc",
    "image",
    "images",
    "logging",
    "meta",
    "metadata",
    "music",
    "packaging",
    "queue",
    "release",
    "screenshots",
    "search",
    "security",
    "setup",
    "takescreens",
    "test",
    "tests",
    "torrent",
    "torrents",
    "update",
    "upload",
    "usenet",
    "video",
    "workflow",
  ]);

  function getUAChangelogArea(scope, summary) {
    const normalizedScope = String(scope || "")
      .trim()
      .toLowerCase();
    const normalizedSummary = String(summary || "").toLowerCase();
    if (
      ["webui", "web-ui", "ui", "frontend"].includes(normalizedScope) ||
      /\bweb\s*ui\b/.test(normalizedSummary)
    ) {
      return "webui";
    }
    if (
      ["config", "configuration", "settings", "example-config"].includes(
        normalizedScope,
      ) ||
      /\b(example config|configuration page)\b/.test(normalizedSummary)
    ) {
      return "configuration";
    }
    if (
      ["tracker", "trackers"].includes(normalizedScope) ||
      UA_TRACKER_SCOPES.has(normalizedScope) ||
      /\b(private )?trackers?\b/.test(normalizedSummary)
    ) {
      return "trackers";
    }
    if (normalizedScope && !UA_CORE_SCOPES.has(normalizedScope)) {
      return "trackers";
    }
    return "core";
  }

  function parseUAReleaseNotes(notes) {
    const raw = String(notes || "").trim();
    const entries = [];
    const supplemental = [];
    let section = "";
    raw.split(/\r?\n/).forEach((sourceLine, index) => {
      const line = sourceLine.trim();
      if (!line) return;
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      if (heading) {
        section = heading[1].replace(/[*_`]/g, "").trim().toLowerCase();
        return;
      }
      const bullet = line.match(/^(?:[-*+]\s+|\d+\.\s+)(.+)$/);
      if (!bullet) {
        if (!/^---+$/.test(line)) supplemental.push(line);
        return;
      }
      const content = bullet[1].trim();
      if (section.includes("contributor")) {
        supplemental.push(content);
        return;
      }
      const conventional = content.match(
        /^(feat|fix|perf|refactor|docs|chore|build|ci|test|style|revert)(?:\(([^)]+)\))?!?:\s*(.+)$/i,
      );
      const type = conventional?.[1]?.toLowerCase() || "change";
      const scope = conventional?.[2]?.trim() || "";
      let summary = conventional?.[3]?.trim() || content;
      const urlMatch = summary.match(
        /https:\/\/github\.com\/wastaken7\/Upload-Assistant\/(?:pull|issues)\/\d+/i,
      );
      const url = urlMatch?.[0] || "";
      if (url) {
        summary = summary
          .replace(url, "")
          .replace(/\s+in\s*$/i, "")
          .trim();
      }
      entries.push({
        id: `${index}-${type}-${scope}-${summary}`,
        type,
        typeLabel: UA_CHANGELOG_TYPES[type] || "Change",
        scope,
        summary,
        url,
        area: getUAChangelogArea(scope, summary),
      });
    });
    return { raw, entries, supplemental };
  }

  function getUAChangelogAreaCounts(parsedReleases) {
    const counts = { all: 0, webui: 0, core: 0, trackers: 0, configuration: 0 };
    parsedReleases.forEach(({ parsed }) => {
      parsed.entries.forEach((entry) => {
        counts.all += 1;
        counts[entry.area] = (counts[entry.area] || 0) + 1;
      });
    });
    return counts;
  }

  function UAChangelogFilters({ activeArea, counts, onChange }) {
    const h = React.createElement;
    return h(
      "div",
      {
        className: "ua-changelog-filters flex flex-wrap gap-2",
        role: "group",
        "aria-label": "Filter changelog by area",
      },
      ...UA_CHANGELOG_AREAS.map((area) =>
        h(
          "button",
          {
            key: area.id,
            type: "button",
            className: `ua-changelog-filter rounded-full border px-3 py-1.5 text-xs font-semibold ${activeArea === area.id ? "is-active" : ""}`,
            "aria-pressed": activeArea === area.id,
            onClick: () => onChange(area.id),
          },
          `${area.label} (${counts[area.id] || 0})`,
        ),
      ),
    );
  }

  function UAReleaseNotes({ parsed, activeArea = "all" }) {
    const h = React.createElement;
    if (!parsed.entries.length) {
      return h(
        "pre",
        {
          className:
            "ua-update-changelog whitespace-pre-wrap rounded-lg border p-3 text-sm leading-6",
        },
        parsed.raw || "No changelog was included with this release.",
      );
    }

    const visibleEntries = parsed.entries.filter(
      (entry) => activeArea === "all" || entry.area === activeArea,
    );
    if (!visibleEntries.length) {
      return h(
        "div",
        { className: "ua-changelog-empty rounded-lg border p-4 text-sm" },
        "This release has no changes in the selected area.",
      );
    }

    const areaGroups = UA_CHANGELOG_AREAS.filter(
      (area) =>
        area.id !== "all" && (activeArea === "all" || activeArea === area.id),
    )
      .map((area) => ({
        ...area,
        entries: visibleEntries.filter((entry) => entry.area === area.id),
      }))
      .filter((group) => group.entries.length);

    return h(
      "div",
      { className: "ua-changelog-notes space-y-4" },
      ...areaGroups.map((group) =>
        h(
          "section",
          { key: group.id, className: "ua-changelog-area" },
          h(
            "h4",
            {
              className:
                "ua-changelog-area-heading mb-2 text-xs font-semibold uppercase tracking-wider",
            },
            group.label,
          ),
          h(
            "ul",
            {
              className:
                "ua-changelog-entry-list overflow-hidden rounded-lg border",
            },
            ...group.entries.map((entry) =>
              h(
                "li",
                {
                  key: entry.id,
                  className:
                    "ua-changelog-entry flex items-start justify-between gap-3 border-b p-3 last:border-b-0",
                },
                h(
                  "div",
                  { className: "min-w-0" },
                  h(
                    "div",
                    { className: "mb-1 flex flex-wrap items-center gap-1.5" },
                    h(
                      "span",
                      {
                        className: `ua-changelog-type ua-changelog-type-${entry.type} rounded-full px-2 py-0.5 text-[0.68rem] font-semibold uppercase tracking-wide`,
                      },
                      entry.typeLabel,
                    ),
                    entry.scope
                      ? h(
                          "span",
                          {
                            className: "ua-changelog-scope text-xs opacity-60",
                          },
                          entry.scope,
                        )
                      : null,
                  ),
                  h("p", { className: "text-sm leading-5" }, entry.summary),
                ),
                entry.url
                  ? h(
                      "a",
                      {
                        href: entry.url,
                        target: "_blank",
                        rel: "noopener noreferrer",
                        className:
                          "ua-changelog-contribution-link shrink-0 text-xs font-semibold",
                        "aria-label": `View contribution for ${entry.summary}`,
                        title: "View contribution on GitHub",
                      },
                      "↗",
                    )
                  : null,
              ),
            ),
          ),
        ),
      ),
      activeArea === "all" && parsed.supplemental.length
        ? h(
            "section",
            { className: "ua-changelog-supplemental rounded-lg border p-3" },
            h(
              "h4",
              {
                className:
                  "mb-2 text-xs font-semibold uppercase tracking-wider",
              },
              "Release information",
            ),
            ...parsed.supplemental.map((line, index) =>
              h(
                "p",
                {
                  key: `${index}-${line}`,
                  className: "text-xs leading-5 opacity-75",
                },
                line,
              ),
            ),
          )
        : null,
    );
  }

  function UAUpdateStatusModal({
    status,
    onClose,
    onDismiss,
    onOpenChangelog,
  }) {
    const [activeArea, setActiveArea] = React.useState("all");
    const parsed = parseUAReleaseNotes(status.changelog);
    const counts = getUAChangelogAreaCounts([{ parsed }]);

    React.useEffect(() => {
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      const closeOnEscape = (event) => {
        if (event.key === "Escape") onClose();
      };
      window.addEventListener("keydown", closeOnEscape);
      return () => {
        document.body.style.overflow = previousOverflow;
        window.removeEventListener("keydown", closeOnEscape);
      };
    }, [onClose]);

    return React.createElement(
      "div",
      {
        className:
          "fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-3 sm:p-4",
        role: "presentation",
        onMouseDown: (event) => {
          if (event.target === event.currentTarget) onClose();
        },
      },
      React.createElement(
        "section",
        {
          className:
            "ua-update-modal flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border shadow-2xl",
          role: "dialog",
          "aria-modal": "true",
          "aria-labelledby": "ua-update-status-title",
        },
        React.createElement(
          "header",
          {
            className:
              "ua-update-modal-header flex items-start justify-between gap-4 border-b px-4 py-3 sm:px-5 sm:py-4",
          },
          React.createElement(
            "div",
            null,
            React.createElement(
              "p",
              {
                className:
                  "ua-update-eyebrow text-xs font-semibold uppercase tracking-wider",
              },
              "Update available",
            ),
            React.createElement(
              "h2",
              {
                id: "ua-update-status-title",
                className: "mt-1 text-lg font-semibold",
              },
              `${status.current_version || "Current"} → ${status.latest_version || "Latest"}`,
            ),
          ),
          React.createElement(
            "button",
            {
              type: "button",
              className: "ua-update-close h-10 w-10 shrink-0 rounded-lg p-0",
              "aria-label": "Close update details",
              onClick: onClose,
              autoFocus: true,
            },
            React.createElement(
              "svg",
              {
                className: "h-4 w-4",
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: "currentColor",
                "aria-hidden": "true",
              },
              React.createElement("path", {
                d: "M6 6l12 12M18 6L6 18",
                strokeWidth: "2",
                strokeLinecap: "round",
              }),
            ),
          ),
        ),
        React.createElement(
          "div",
          { className: "min-h-0 flex-1 overflow-y-auto p-4 sm:p-5" },
          React.createElement(
            "div",
            { className: "ua-update-version-grid mb-4 grid grid-cols-2 gap-3" },
            React.createElement(
              "div",
              { className: "ua-update-version-card rounded-lg border p-3" },
              React.createElement(
                "span",
                { className: "block text-xs opacity-70" },
                "Installed",
              ),
              React.createElement(
                "strong",
                { className: "mt-1 block" },
                status.current_version || "Unknown",
              ),
            ),
            React.createElement(
              "div",
              { className: "ua-update-version-card rounded-lg border p-3" },
              React.createElement(
                "span",
                { className: "block text-xs opacity-70" },
                "Latest",
              ),
              React.createElement(
                "strong",
                { className: "mt-1 block" },
                status.latest_version || "Unknown",
              ),
            ),
          ),
          React.createElement(
            "h3",
            { className: "mb-2 text-sm font-semibold" },
            "What’s changed",
          ),
          React.createElement(
            "div",
            { className: "mb-3" },
            React.createElement(UAChangelogFilters, {
              activeArea,
              counts,
              onChange: setActiveArea,
            }),
          ),
          React.createElement(
            "div",
            { className: "ua-update-changelog-container" },
            React.createElement(UAReleaseNotes, { parsed, activeArea }),
          ),
        ),
        React.createElement(
          "footer",
          {
            className:
              "ua-update-modal-footer flex flex-wrap justify-end gap-2 border-t px-4 py-3 sm:px-5",
          },
          React.createElement(
            "button",
            {
              type: "button",
              className:
                "ua-update-action rounded-lg border px-4 py-2 text-sm font-semibold",
              onClick: onClose,
            },
            "Remind me later",
          ),
          React.createElement(
            "button",
            {
              type: "button",
              className:
                "ua-update-action rounded-lg border px-4 py-2 text-sm font-semibold",
              onClick: onDismiss,
            },
            `Dismiss ${status.latest_version || "release"}`,
          ),
          onOpenChangelog
            ? React.createElement(
                "button",
                {
                  type: "button",
                  className:
                    "ua-update-action rounded-lg border px-4 py-2 text-sm font-semibold",
                  onClick: onOpenChangelog,
                },
                "Full changelog",
              )
            : null,
          React.createElement(
            "a",
            {
              href:
                status.release_url ||
                "https://github.com/wastaken7/Upload-Assistant/releases",
              target: "_blank",
              rel: "noopener noreferrer",
              className:
                "ua-update-primary rounded-lg px-4 py-2 text-sm font-semibold",
            },
            "View release ↗",
          ),
        ),
      ),
    );
  }

  function formatUAReleaseDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(date);
  }

  function normalizeUAVersion(value) {
    return String(value || "")
      .trim()
      .replace(/^v/i, "")
      .toLowerCase();
  }

  function UAChangelogModal({ onClose }) {
    const h = React.createElement;
    const [history, setHistory] = React.useState(null);
    const [error, setError] = React.useState("");
    const [isLoading, setIsLoading] = React.useState(true);
    const [isRefreshing, setIsRefreshing] = React.useState(false);
    const [activeArea, setActiveArea] = React.useState("all");
    const [expandedVersions, setExpandedVersions] = React.useState(new Set());

    const applyHistory = React.useCallback((nextHistory) => {
      setHistory(nextHistory);
      const firstVersion = nextHistory?.releases?.[0]?.version;
      if (firstVersion) {
        setExpandedVersions((current) =>
          current.size ? current : new Set([firstVersion]),
        );
      }
    }, []);

    React.useEffect(() => {
      let cancelled = false;
      setIsLoading(true);
      loadUAChangelog()
        .then((nextHistory) => {
          if (!cancelled) applyHistory(nextHistory);
        })
        .catch((loadError) => {
          if (!cancelled) {
            setError(loadError?.message || "Unable to load the changelog.");
          }
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }, [applyHistory]);

    React.useEffect(() => {
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      const closeOnEscape = (event) => {
        if (event.key === "Escape") onClose();
      };
      window.addEventListener("keydown", closeOnEscape);
      return () => {
        document.body.style.overflow = previousOverflow;
        window.removeEventListener("keydown", closeOnEscape);
      };
    }, [onClose]);

    const refreshHistory = async () => {
      setIsRefreshing(true);
      setError("");
      try {
        applyHistory(await loadUAChangelog(true));
      } catch (refreshError) {
        setError(refreshError?.message || "Unable to refresh the changelog.");
      } finally {
        setIsRefreshing(false);
      }
    };

    const releases = Array.isArray(history?.releases) ? history.releases : [];
    const parsedReleases = React.useMemo(
      () =>
        releases.map((release, index) => ({
          release,
          parsed: parseUAReleaseNotes(release.changelog),
          isLatest: index === 0,
        })),
      [releases],
    );
    const counts = React.useMemo(
      () => getUAChangelogAreaCounts(parsedReleases),
      [parsedReleases],
    );
    const visibleReleases = parsedReleases.filter(
      ({ parsed }) =>
        activeArea === "all" ||
        parsed.entries.some((entry) => entry.area === activeArea),
    );

    const changeArea = (area) => {
      setActiveArea(area);
      if (area === "all") return;
      const firstMatchingRelease = parsedReleases.find(({ parsed }) =>
        parsed.entries.some((entry) => entry.area === area),
      );
      if (firstMatchingRelease?.release?.version) {
        setExpandedVersions((current) => {
          const next = new Set(current);
          next.add(firstMatchingRelease.release.version);
          return next;
        });
      }
    };

    const toggleRelease = (version) => {
      setExpandedVersions((current) => {
        const next = new Set(current);
        if (next.has(version)) next.delete(version);
        else next.add(version);
        return next;
      });
    };

    return h(
      "div",
      {
        className:
          "fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-3 sm:p-4",
        role: "presentation",
        onMouseDown: (event) => {
          if (event.target === event.currentTarget) onClose();
        },
      },
      h(
        "section",
        {
          className:
            "ua-update-modal ua-changelog-modal flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border shadow-2xl",
          role: "dialog",
          "aria-modal": "true",
          "aria-labelledby": "ua-changelog-title",
        },
        h(
          "header",
          {
            className:
              "ua-update-modal-header flex items-start justify-between gap-4 border-b px-4 py-3 sm:px-5 sm:py-4",
          },
          h(
            "div",
            { className: "min-w-0" },
            h(
              "p",
              {
                className:
                  "ua-update-eyebrow text-xs font-semibold uppercase tracking-wider",
              },
              "Release history",
            ),
            h(
              "h2",
              {
                id: "ua-changelog-title",
                className: "mt-1 text-lg font-semibold",
              },
              "Upload Assistant Changelog",
            ),
            h(
              "p",
              { className: "mt-1 text-xs opacity-70" },
              "Browse recent releases by product area and change type.",
            ),
          ),
          h(
            "button",
            {
              type: "button",
              className: "ua-update-close h-10 w-10 shrink-0 rounded-lg p-0",
              "aria-label": "Close changelog",
              onClick: onClose,
              autoFocus: true,
            },
            h(
              "svg",
              {
                className: "h-4 w-4",
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: "currentColor",
                "aria-hidden": "true",
              },
              h("path", {
                d: "M6 6l12 12M18 6L6 18",
                strokeWidth: "2",
                strokeLinecap: "round",
              }),
            ),
          ),
        ),
        h(
          "div",
          { className: "min-h-0 flex-1 overflow-y-auto p-4 sm:p-5" },
          h(
            "div",
            {
              className:
                "ua-changelog-toolbar mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3",
            },
            h(UAChangelogFilters, {
              activeArea,
              counts,
              onChange: changeArea,
            }),
            h(
              "button",
              {
                type: "button",
                className:
                  "ua-update-action shrink-0 rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-wait disabled:opacity-60",
                disabled: isLoading || isRefreshing,
                onClick: refreshHistory,
              },
              isRefreshing ? "Refreshing…" : "Refresh",
            ),
          ),
          history?.warning
            ? h(
                "div",
                {
                  className:
                    "ua-changelog-warning mb-4 rounded-lg border p-3 text-sm",
                  role: "status",
                },
                history.warning,
              )
            : null,
          error
            ? h(
                "div",
                {
                  className:
                    "ua-changelog-error mb-4 rounded-lg border p-3 text-sm",
                  role: "alert",
                },
                error,
              )
            : null,
          isLoading
            ? h(
                "div",
                {
                  className:
                    "ua-changelog-empty rounded-lg border p-6 text-center text-sm",
                  role: "status",
                },
                "Loading release history…",
              )
            : visibleReleases.length
              ? h(
                  "div",
                  { className: "ua-changelog-releases space-y-3" },
                  ...visibleReleases.map(
                    ({ release, parsed, isLatest }, index) => {
                      const version = String(
                        release.version || `release-${index}`,
                      );
                      const expanded = expandedVersions.has(version);
                      const panelId = `ua-changelog-release-${version.replace(/[^a-z0-9_-]/gi, "-")}`;
                      const releaseDate = formatUAReleaseDate(
                        release.published_at,
                      );
                      const title = String(release.title || "");
                      const showTitle = title && title !== version;
                      const isInstalled =
                        normalizeUAVersion(version) ===
                        normalizeUAVersion(window.UA_APP_VERSION);
                      return h(
                        "article",
                        {
                          key: version,
                          className:
                            "ua-changelog-release overflow-hidden rounded-lg border",
                        },
                        h(
                          "div",
                          {
                            className:
                              "ua-changelog-release-header flex items-stretch border-b",
                          },
                          h(
                            "button",
                            {
                              type: "button",
                              className:
                                "flex min-w-0 flex-1 items-center justify-between gap-3 px-3 py-3 text-left sm:px-4",
                              "aria-expanded": expanded,
                              "aria-controls": panelId,
                              onClick: () => toggleRelease(version),
                            },
                            h(
                              "span",
                              { className: "min-w-0" },
                              h(
                                "span",
                                {
                                  className:
                                    "flex flex-wrap items-center gap-2",
                                },
                                h("strong", { className: "text-sm" }, version),
                                isLatest
                                  ? h(
                                      "span",
                                      {
                                        className:
                                          "ua-changelog-release-badge rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide",
                                      },
                                      "Latest",
                                    )
                                  : null,
                                isInstalled
                                  ? h(
                                      "span",
                                      {
                                        className:
                                          "ua-changelog-installed-badge rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide",
                                      },
                                      "Installed",
                                    )
                                  : null,
                                release.prerelease
                                  ? h(
                                      "span",
                                      {
                                        className:
                                          "ua-changelog-prerelease-badge rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide",
                                      },
                                      "Pre-release",
                                    )
                                  : null,
                              ),
                              showTitle
                                ? h(
                                    "span",
                                    {
                                      className:
                                        "mt-1 block truncate text-xs opacity-70",
                                    },
                                    title,
                                  )
                                : null,
                              releaseDate
                                ? h(
                                    "span",
                                    {
                                      className:
                                        "mt-1 block text-xs opacity-55",
                                    },
                                    releaseDate,
                                  )
                                : null,
                            ),
                            h(
                              "svg",
                              {
                                className: `h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`,
                                viewBox: "0 0 24 24",
                                fill: "none",
                                stroke: "currentColor",
                                "aria-hidden": "true",
                              },
                              h("path", {
                                d: "M6 9l6 6 6-6",
                                strokeWidth: "2",
                                strokeLinecap: "round",
                                strokeLinejoin: "round",
                              }),
                            ),
                          ),
                          release.release_url
                            ? h(
                                "a",
                                {
                                  href: release.release_url,
                                  target: "_blank",
                                  rel: "noopener noreferrer",
                                  className:
                                    "ua-changelog-release-link flex shrink-0 items-center border-l px-3 text-xs font-semibold sm:px-4",
                                  title: `View ${version} on GitHub`,
                                  "aria-label": `View ${version} on GitHub`,
                                },
                                "↗",
                              )
                            : null,
                        ),
                        expanded
                          ? h(
                              "div",
                              {
                                id: panelId,
                                className:
                                  "ua-changelog-release-body p-3 sm:p-4",
                              },
                              h(UAReleaseNotes, { parsed, activeArea }),
                            )
                          : null,
                      );
                    },
                  ),
                )
              : h(
                  "div",
                  {
                    className:
                      "ua-changelog-empty rounded-lg border p-6 text-center text-sm",
                  },
                  releases.length
                    ? "No releases contain changes in the selected area."
                    : "No release history is available.",
                ),
        ),
        h(
          "footer",
          {
            className:
              "ua-update-modal-footer flex flex-wrap items-center justify-between gap-2 border-t px-4 py-3 sm:px-5",
          },
          h(
            "span",
            { className: "text-xs opacity-60" },
            history?.stale
              ? "Cached or bundled release notes"
              : "GitHub release history",
          ),
          h(
            "a",
            {
              href: "https://github.com/wastaken7/Upload-Assistant/releases",
              target: "_blank",
              rel: "noopener noreferrer",
              className:
                "ua-update-primary rounded-lg px-4 py-2 text-sm font-semibold",
            },
            "View all releases ↗",
          ),
        ),
      ),
    );
  }

  // Shared HTML sanitizer. Uses DOMPurify when available; falls back to DOMParser-based sanitizer.
  function sanitizeHtml(html) {
    const rawHtml = String(html || "");
    if (typeof window !== "undefined" && window.DOMPurify) {
      const dangerousTags = [
        "script",
        "style",
        "img",
        "svg",
        "iframe",
        "object",
        "embed",
        "form",
        "input",
        "button",
        "meta",
        "link",
      ];
      const forbiddenAttrs = [
        "srcset",
        "onerror",
        "onload",
        "onclick",
        "onmouseover",
        "onmouseenter",
        "onmouseleave",
        "onkeydown",
        "onkeypress",
        "onkeyup",
      ];
      return DOMPurify.sanitize(rawHtml, {
        ALLOWED_ATTR: ["class", "href", "src", "title", "alt", "rel", "style"],
        FORBID_TAGS: dangerousTags,
        FORBID_ATTR: forbiddenAttrs,
      });
    }
    try {
      const doc = new DOMParser().parseFromString(rawHtml, "text/html");
      const dangerousTags = [
        "script",
        "style",
        "img",
        "svg",
        "iframe",
        "object",
        "embed",
        "form",
        "input",
        "button",
        "meta",
        "link",
      ];
      dangerousTags.forEach((tag) => {
        doc.querySelectorAll(tag).forEach((el) => el.remove());
      });
      doc.querySelectorAll("*").forEach((el) => {
        [...el.attributes].forEach((attr) => {
          const attrName = attr.name.toLowerCase();
          const attrValue = String(attr.value).toLowerCase().trim();
          if (attrName.startsWith("on")) {
            el.removeAttribute(attr.name);
          } else if (
            (attrName === "href" || attrName === "src") &&
            (attrValue.startsWith("javascript:") ||
              attrValue.startsWith("data:") ||
              attrValue.startsWith("vbscript:"))
          ) {
            el.removeAttribute(attr.name);
          } else if (
            attrName === "srcset" ||
            (attrName === "style" && attrValue.includes("url("))
          ) {
            el.removeAttribute(attr.name);
          }
        });
      });
      return doc.body.innerHTML;
    } catch (e) {
      return rawHtml.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
  }

  // Expose as globals for non-module usage by existing scripts.
  if (typeof window !== "undefined") {
    window.UAStorage = window.UAStorage || uaStorage;
    window.UAThemes = window.UAThemes || UA_THEMES;
    window.UAInterfaceStyles = window.UAInterfaceStyles || UA_INTERFACE_STYLES;
    window.UAHelpResourceGroups =
      window.UAHelpResourceGroups || UA_HELP_RESOURCE_GROUPS;
    window.getUAStoredTheme = window.getUAStoredTheme || getUAStoredTheme;
    window.getUAStoredColorTheme =
      window.getUAStoredColorTheme || getUAStoredColorTheme;
    window.setUAColorTheme = window.setUAColorTheme || setUAColorTheme;
    window.getUAStoredInterfaceStyle =
      window.getUAStoredInterfaceStyle || getUAStoredInterfaceStyle;
    window.setUAInterfaceStyle =
      window.setUAInterfaceStyle || setUAInterfaceStyle;
    window.loadCsrfToken = window.loadCsrfToken || loadCsrfToken;
    window.clearCsrfToken = window.clearCsrfToken || clearCsrfToken;
    window.uaApiFetch = window.uaApiFetch || uaApiFetch;
    window.loadUAUpdateStatus = window.loadUAUpdateStatus || loadUAUpdateStatus;
    window.loadUAChangelog = window.loadUAChangelog || loadUAChangelog;
    window.getUADismissedUpdateVersion =
      window.getUADismissedUpdateVersion || getUADismissedUpdateVersion;
    window.dismissUAUpdateVersion =
      window.dismissUAUpdateVersion || dismissUAUpdateVersion;
    window.UAUpdateStatusModal =
      window.UAUpdateStatusModal || UAUpdateStatusModal;
    window.UAChangelogModal = window.UAChangelogModal || UAChangelogModal;
    window.sanitizeHtml = window.sanitizeHtml || sanitizeHtml;
  }
})();
