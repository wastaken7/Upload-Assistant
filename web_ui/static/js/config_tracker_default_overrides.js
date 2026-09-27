/** Keep explicit tracker values distinct from inherited (null) settings. */
(() => {
  const createEditor = ({
    pathParts,
    defaults = {},
    pendingChanges = new Map(),
    drafts,
    onValueChange,
  }) => {
    const fieldState = (item) => {
      const path = [...pathParts, item.key];
      const pathKey = path.join("/");
      const pending = pendingChanges.get(pathKey);
      const stored = item.source === "config";
      const value = pending
        ? pending.removeKey
          ? null
          : pending.value
        : item.value;
      return {
        path,
        pathKey,
        stored,
        enabled: (pending ? !pending.removeKey : stored) && value != null,
        value,
        inherited: defaults[item.key] ?? item.example_value ?? "",
      };
    };
    const updateField = (item, value) => {
      const state = fieldState(item);
      onValueChange(state.path, value, {
        originalValue: state.stored ? item.value : undefined,
        isSensitive: false,
        isRedacted: false,
        readOnly: false,
      });
    };
    const coerceFieldValue = (item, value) => {
      const valueType = typeof (
        item.example_value ?? item.value ?? defaults[item.key]
      );
      return valueType === "boolean"
        ? value === true || value === "true" || value === "True"
        : valueType === "number"
          ? Number(value)
          : value;
    };
    const setFieldEnabled = (item, enabled) => {
      const state = fieldState(item);
      if (state.enabled === enabled) return;
      if (enabled) {
        updateField(
          item,
          coerceFieldValue(item, drafts.get(state.pathKey) ?? state.inherited),
        );
      } else {
        drafts.set(state.pathKey, state.value);
        updateField(item, null);
      }
    };
    return { fieldState, updateField, coerceFieldValue, setFieldEnabled };
  };

  window.UATrackerDefaultOverrides = { createEditor };
})();
