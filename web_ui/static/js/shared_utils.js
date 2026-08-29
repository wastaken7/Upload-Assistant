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
          description: "Basic WebUI setup and usage.",
          href: "https://github.com/wastaken7/Upload-Assistant/blob/development/docs/web-ui-basic.md",
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

  function getUADismissedUpdateVersion() {
    return uaStorage.get("ua_dismissed_update_version") || "";
  }

  function dismissUAUpdateVersion(version) {
    if (version) uaStorage.set("ua_dismissed_update_version", String(version));
  }

  function UAUpdateStatusModal({ status, onClose, onDismiss }) {
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
              className:
                "ua-update-close h-10 w-10 shrink-0 rounded-lg text-xl",
              "aria-label": "Close update details",
              onClick: onClose,
              autoFocus: true,
            },
            "×",
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
            "pre",
            {
              className:
                "ua-update-changelog whitespace-pre-wrap rounded-lg border p-3 text-sm leading-6",
            },
            status.changelog || "No changelog was included with this release.",
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
    window.getUADismissedUpdateVersion =
      window.getUADismissedUpdateVersion || getUADismissedUpdateVersion;
    window.dismissUAUpdateVersion =
      window.dismissUAUpdateVersion || dismissUAUpdateVersion;
    window.UAUpdateStatusModal =
      window.UAUpdateStatusModal || UAUpdateStatusModal;
    window.sanitizeHtml = window.sanitizeHtml || sanitizeHtml;
  }
})();
