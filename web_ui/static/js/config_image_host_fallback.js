// Keep Image Host dropdowns usable when config metadata omits the host list.
(() => {
  const IMAGE_HOSTS = Object.freeze([
    "dalexni",
    "imgbb",
    "imgbox",
    "lensdump",
    "lostimg",
    "midnightscene",
    "onlyimage",
    "passtheimage",
    "pixhost",
    "ptscreens",
    "seedpool_cdn",
    "sharex",
    "utppm",
    "zipline",
  ]);

  const originalApiFetch = window.uaApiFetch;
  if (typeof originalApiFetch !== "function") {
    return;
  }

  const ensureImageHostHelp = (data) => {
    if (!data || !Array.isArray(data.sections)) {
      return data;
    }

    const helpLine = `Available image hosts: ${IMAGE_HOSTS.join(", ")}`;

    const visitItems = (items) => {
      for (const item of items || []) {
        if (Array.isArray(item.children)) {
          visitItems(item.children);
        }
        if (!String(item.key || "").startsWith("img_host_")) {
          continue;
        }

        if (!Array.isArray(item.help)) {
          item.help = [];
        }
        if (
          !item.help.some((line) =>
            String(line).toLowerCase().includes("available image hosts"),
          )
        ) {
          item.help.push(helpLine);
        }
      }
    };

    for (const section of data.sections) {
      visitItems(section.items || []);
    }
    return data;
  };

  window.uaApiFetch = async (...args) => {
    const response = await originalApiFetch(...args);
    const url = String(args[0] || "");
    if (!url.includes("/api/config_options") || !response || !response.ok) {
      return response;
    }

    try {
      const data = ensureImageHostHelp(await response.clone().json());
      const headers = new Headers(response.headers);
      headers.delete("content-length");
      return new Response(JSON.stringify(data), {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    } catch (_error) {
      return response;
    }
  };

  window.UA_IMAGE_HOSTS = IMAGE_HOSTS;
})();
