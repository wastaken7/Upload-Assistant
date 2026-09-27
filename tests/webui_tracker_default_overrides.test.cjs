const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = { window: {} };
vm.runInNewContext(
  fs.readFileSync(
    path.join(__dirname, "../web_ui/static/js/config_tracker_default_overrides.js"),
    "utf8",
  ),
  context,
);
const { createEditor } = context.window.UATrackerDefaultOverrides;
const defaults = { add_logo: true, multiScreens: 4, custom_signature: "Global" };
const pathKey = (item) => `TRACKERS/AITHER/${item.key}`;
const item = (key, value, source = "config") => ({
  key,
  value,
  source,
  example_value: defaults[key],
});

function setup() {
  const pendingChanges = new Map();
  const drafts = new Map();
  const editor = createEditor({
    pathParts: ["TRACKERS", "AITHER"],
    defaults: { ...defaults },
    pendingChanges,
    drafts,
    onValueChange(path, value, meta) {
      if (value === meta.originalValue && !meta.removeKey) {
        pendingChanges.delete(path.join("/"));
      } else {
        pendingChanges.set(path.join("/"), { path, value, ...meta });
      }
    },
  });
  return { ...editor, pendingChanges, drafts };
}

test("saved null and absent settings inherit while falsy overrides stay enabled", () => {
  const editor = setup();
  for (const [key, value] of [
    ["add_logo", false],
    ["multiScreens", 0],
    ["custom_signature", ""],
  ]) {
    assert.equal(editor.fieldState(item(key, value)).enabled, true);
    for (const inherited of [item(key, null), item(key, value, "example")]) {
      const state = editor.fieldState(inherited);
      assert.equal(state.enabled, false);
      assert.equal(state.inherited, defaults[key]);
    }
  }
});

test("Disable all stages null values, keeps the keys on save and reloads unchecked", () => {
  const editor = setup();
  const items = [
    item("add_logo", false),
    item("multiScreens", 0),
    item("custom_signature", ""),
  ];
  items.forEach((entry) => editor.setFieldEnabled(entry, false));
  assert.equal(items.filter((entry) => editor.fieldState(entry).enabled).length, 0);
  assert.equal(editor.pendingChanges.size, 3);
  for (const entry of items) {
    const update = editor.pendingChanges.get(pathKey(entry));
    assert.equal(update.value, null);
    assert.ok(!update.removeKey);
    const saved = JSON.parse(JSON.stringify(update));
    const reloaded = setup().fieldState(item(entry.key, saved.value));
    assert.equal(reloaded.stored, true);
    assert.equal(reloaded.enabled, false);
    assert.equal(reloaded.inherited, defaults[entry.key]);
  }
});

test("disable then re-enable restores unsaved drafts including false, zero and blank", () => {
  for (const [key, value] of [
    ["add_logo", false],
    ["multiScreens", 0],
    ["custom_signature", ""],
  ]) {
    const editor = setup();
    const entry = item(key, null);
    editor.setFieldEnabled(entry, true);
    editor.updateField(entry, value);
    editor.setFieldEnabled(entry, false);
    assert.equal(editor.pendingChanges.size, 0);
    editor.setFieldEnabled(entry, true);
    assert.equal(editor.fieldState(entry).value, value);
    assert.equal(editor.fieldState(entry).enabled, true);
    assert.equal(editor.pendingChanges.get(pathKey(entry)).value, value);
  }
});

test("toggling a saved override off and back on cancels the pending change", () => {
  const editor = setup();
  const entry = item("add_logo", false);
  editor.setFieldEnabled(entry, false);
  editor.setFieldEnabled(entry, true);
  assert.equal(editor.pendingChanges.size, 0);
  assert.equal(editor.fieldState(entry).value, false);
});

test("Enable all starts saved inherited fields from current DEFAULT values", () => {
  const editor = setup();
  for (const key of Object.keys(defaults)) {
    const entry = item(key, null);
    editor.setFieldEnabled(entry, true);
    assert.equal(editor.fieldState(entry).enabled, true);
    assert.equal(editor.pendingChanges.get(pathKey(entry)).value, defaults[key]);
  }
});

test("discard restores the saved override and clears unsaved inheritance", () => {
  const editor = setup();
  const entry = item("multiScreens", 2);
  editor.setFieldEnabled(entry, false);
  editor.pendingChanges.clear();
  editor.drafts.clear();
  assert.equal(editor.fieldState(entry).enabled, true);
  assert.equal(editor.fieldState(entry).value, 2);
});

test("legacy fields missing from the template recover their type from DEFAULT", () => {
  const editor = setup();
  const entry = { key: "add_logo", value: null, source: "config" };
  editor.setFieldEnabled(entry, true);
  assert.equal(editor.fieldState(entry).value, true);
  assert.equal(editor.coerceFieldValue(entry, "false"), false);
});
