(() => {
  const DAY = 86400000;
  const WARNING_DAYS = 14;

  function state(expiry) {
    if (!expiry?.expires_at)
      return expiry?.state === "no_expiry" ? "no_expiry" : "unknown";
    const remaining = new Date(expiry.expires_at).getTime() - Date.now();
    if (!Number.isFinite(remaining)) return "unknown";
    return remaining <= 0
      ? "expired"
      : remaining <= WARNING_DAYS * DAY
        ? "expiring"
        : "valid";
  }

  function label(expiry, compact = false) {
    const current = state(expiry);
    if (current === "unknown") return "Expiry not reported";
    if (current === "no_expiry")
      return compact ? "Does not expire" : "No expiry (reported by tracker)";
    const date = new Date(expiry.expires_at);
    const dateText = compact
      ? date.toLocaleDateString()
      : date.toLocaleString();
    if (current === "expired") return `Expired ${dateText}`;
    const days = Math.ceil((date.getTime() - Date.now()) / DAY);
    const remaining = days === 1 ? "less than a day" : `${days} days`;
    return compact
      ? `Expires in ${remaining}`
      : `Expires ${dateText} · ${remaining} remaining`;
  }

  function alerts(trackers) {
    return (trackers || [])
      .filter(
        (tracker) =>
          tracker.configured &&
          tracker.api_key_expiry_supported &&
          ["expired", "expiring"].includes(state(tracker.api_key_expiry)),
      )
      .slice()
      .sort(
        (a, b) =>
          new Date(a.api_key_expiry.expires_at) -
            new Date(b.api_key_expiry.expires_at) ||
          a.name.localeCompare(b.name),
      );
  }

  // Reclassify cached dates as time passes, without making tracker requests.
  function useClock() {
    const [, tick] = React.useState(0);
    React.useEffect(() => {
      const update = () => tick((value) => value + 1);
      const timer = window.setInterval(update, 60000);
      document.addEventListener("visibilitychange", update);
      return () => {
        window.clearInterval(timer);
        document.removeEventListener("visibilitychange", update);
      };
    }, []);
  }

  window.UAApiKeyExpiry = { state, label, alerts, useClock };

  window.UAApiKeyAlerts = function ApiKeyAlerts({
    trackers,
    appBase = "",
    onOpenTracker,
    placement = "rail",
  }) {
    useClock();
    const [open, setOpen] = React.useState(false);
    const buttonRef = React.useRef(null);
    const dialogRef = React.useRef(null);
    const closeRef = React.useRef(null);
    const dialogId = React.useId();
    const affected = alerts(trackers);
    const count = affected.length;
    const severity = count ? state(affected[0].api_key_expiry) : "expiring";

    React.useEffect(() => {
      if (!count) setOpen(false);
    }, [count]);

    React.useEffect(() => {
      if (!open) return undefined;
      closeRef.current?.focus();
      const outside = (event) => {
        if (
          !dialogRef.current?.contains(event.target) &&
          !buttonRef.current?.contains(event.target)
        )
          setOpen(false);
      };
      const escape = (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          setOpen(false);
          buttonRef.current?.focus();
        }
      };
      document.addEventListener("pointerdown", outside);
      document.addEventListener("focusin", outside);
      document.addEventListener("keydown", escape);
      return () => {
        document.removeEventListener("pointerdown", outside);
        document.removeEventListener("focusin", outside);
        document.removeEventListener("keydown", escape);
      };
    }, [open]);

    if (!count) return null;
    const h = React.createElement;
    const description = `${count} API ${count === 1 ? "key needs" : "keys need"} attention`;
    const buttonClass =
      placement === "rail"
        ? "ua-app-rail-button rounded-lg"
        : placement === "sidebar"
          ? "ua-config-sidebar-action rounded-lg px-3 py-2 text-sm font-semibold"
          : "ua-upload-header-action rounded-lg p-2";
    const icon = h(
      "svg",
      {
        width: 20,
        height: 20,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: 2,
        strokeLinecap: "round",
        strokeLinejoin: "round",
        "aria-hidden": true,
      },
      h("path", {
        d: "M10.3 3.9 1.8 18.6A1.6 1.6 0 0 0 3.2 21h17.6a1.6 1.6 0 0 0 1.4-2.4L13.7 3.9a2 2 0 0 0-3.4 0Z",
      }),
      h("path", { d: "M12 9v4m0 4h.01" }),
    );

    return h(
      React.Fragment,
      null,
      h(
        "button",
        {
          ref: buttonRef,
          type: "button",
          className: `${buttonClass} ua-api-key-alert-button`,
          "data-severity": severity,
          "aria-label": description,
          "aria-haspopup": "dialog",
          "aria-expanded": open,
          "aria-controls": open ? dialogId : undefined,
          title: description,
          onClick: () => setOpen((value) => !value),
        },
        h(
          "span",
          { className: "ua-api-key-alert-icon" },
          icon,
          h(
            "span",
            { className: "ua-api-key-alert-count", "aria-hidden": true },
            count,
          ),
        ),
        placement !== "header" && h("span", null, "API keys"),
      ),
      open &&
        ReactDOM.createPortal(
          h(
            "div",
            {
              ref: dialogRef,
              id: dialogId,
              role: "dialog",
              "aria-label": "API key expiry warnings",
              className:
                "ua-app-rail-popover ua-api-key-alert-popover rounded-xl border p-4 shadow-2xl",
              "data-placement": placement,
            },
            h(
              "div",
              { className: "flex items-center justify-between gap-3" },
              h("h2", { className: "text-sm font-semibold" }, "API key expiry"),
              h(
                "button",
                {
                  ref: closeRef,
                  type: "button",
                  "aria-label": "Close API key warnings",
                  className: "rounded p-1 text-xl leading-none",
                  onClick: () => {
                    setOpen(false);
                    buttonRef.current?.focus();
                  },
                },
                "×",
              ),
            ),
            h(
              "p",
              { className: "ua-app-rail-popover-label mt-2 text-xs" },
              `Saved keys that have expired or expire within ${WARNING_DAYS} days. Select a tracker to review its key.`,
            ),
            h(
              "ul",
              { className: "mt-3 space-y-2" },
              affected.map((tracker) =>
                h(
                  "li",
                  { key: tracker.name },
                  h(
                    "a",
                    {
                      href: `${appBase}/config?tracker=${encodeURIComponent(tracker.name)}`,
                      className:
                        "ua-api-key-alert-link block rounded-lg border p-3 text-sm",
                      "data-severity": state(tracker.api_key_expiry),
                      onClick: (event) => {
                        if (
                          onOpenTracker &&
                          !event.ctrlKey &&
                          !event.metaKey &&
                          !event.shiftKey &&
                          !event.altKey
                        ) {
                          event.preventDefault();
                          setOpen(false);
                          onOpenTracker(tracker.name);
                        }
                      },
                    },
                    h(
                      "span",
                      { className: "block font-semibold" },
                      tracker.display_name || tracker.name,
                    ),
                    h(
                      "span",
                      {
                        className: "ua-api-key-expiry-tone mt-1 block text-xs",
                      },
                      label(tracker.api_key_expiry),
                    ),
                    tracker.api_key_expiry.checked_at &&
                      h(
                        "span",
                        {
                          className:
                            "ua-app-rail-popover-label mt-1 block text-xs",
                        },
                        `Last checked ${new Date(tracker.api_key_expiry.checked_at).toLocaleString()}`,
                      ),
                  ),
                ),
              ),
            ),
          ),
          buttonRef.current?.closest(".ua-config-page, .ua-upload-page") ||
            document.body,
        ),
    );
  };
})();
