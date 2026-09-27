// Keep a large configuration save to one field-update request.
(() => {
  const readResponse = async (response) => {
    if (response.status === 429) {
      throw new Error(
        "Too many requests. Pending changes kept; try saving later.",
      );
    }
    try {
      return await response.json();
    } catch {
      throw new Error(
        `Unable to read the save response (HTTP ${response.status}). Your pending changes are still here.`,
      );
    }
  };

  const saveUpdates = async (apiFetch, apiBase, updates) => {
    if (!updates.length) return;
    const response = await apiFetch(`${apiBase}/config_update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    });
    const data = await readResponse(response);
    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to save configuration");
    }
  };

  window.UAConfigSave = { readResponse, saveUpdates };
})();
