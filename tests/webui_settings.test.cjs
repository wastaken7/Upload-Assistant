const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const babel = require("../web_ui/static/js/node_modules/@babel/core");

const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/config_app.js"),
  "utf8",
);
const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
const declarations = new Map();
function visit(node) {
  if (!node || typeof node !== "object") return;
  if (node.type === "VariableDeclarator")
    declarations.set(node.id.name, node.init);
  for (const [key, value] of Object.entries(node)) {
    if (["loc", "tokens", "comments"].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(visit);
    else if (value && typeof value === "object") visit(value);
  }
}
visit(ast);
function load(context, names) {
  for (const name of names) {
    const node = declarations.get(name);
    assert.ok(node, `Missing declaration ${name}`);
    vm.runInContext(
      `const ${name} = ${source.slice(node.start, node.end)};`,
      context,
    );
  }
}

test("WebUI settings belong to General without adding a sidebar page", () => {
  const context = vm.createContext({});
  load(context, [
    "DEFAULT_WORKFLOW_GROUPS",
    "normalizeConfigHeading",
    "getDefaultItemGroupId",
    "getDefaultNavigationGroups",
  ]);
  context.section = {
    section: "DEFAULT",
    items: [
      { key: "MAIN SETTINGS", subsection: true },
      { key: "WEBUI SETTINGS", subsection: true },
      { key: "IMAGE HOSTING", subsection: true },
    ],
  };
  assert.equal(
    vm.runInContext("getDefaultItemGroupId(section.items[1])", context),
    "general",
  );
  const groups = vm.runInContext(
    "getDefaultNavigationGroups(section)",
    context,
  );
  assert.deepEqual(
    Array.from(groups, (group) => group.label),
    ["General", "Image Hosting"],
  );
});

test("THRImg and Catbox credentials both map to image host API keys", () => {
  const context = vm.createContext({});
  load(context, ["imageHostApiKeys", "getImageHostForApiKey"]);
  assert.equal(
    vm.runInContext('getImageHostForApiKey("thrimg_api")', context),
    "thrimg",
  );
  assert.equal(
    vm.runInContext('getImageHostForApiKey("catbox_userhash")', context),
    "catbox",
  );
  assert.equal(
    vm.runInContext('getImageHostForApiKey("image_upload_limit")', context),
    null,
  );
});

test("prompt timeout is numeric with a 60-minute default and accepts zero, fractions, and longer waits", () => {
  const context = vm.createContext({});
  load(context, ["isNumericField", "getDefaultValue", "getFieldLimits"]);
  const key = "webui_unattended_prompt_timeout";
  context.key = key;
  assert.equal(vm.runInContext("isNumericField(key)", context), true);
  assert.equal(vm.runInContext("getDefaultValue(key)", context), 60);
  const limits = vm.runInContext("getFieldLimits(key)", context);
  assert.equal(limits.min, 0);
  assert.equal(limits.step, "any");
  Object.assign(context, limits, {
    isEditing: { current: true },
    cancelCommit: { current: false },
    setDraftValue: () => {},
  });
  const commit = declarations.get("commitDraftValue");
  const commitValue = vm.runInContext(
    `(${source.slice(commit.start, commit.end)})`,
    context,
  );
  for (const minutes of [0, 0.5, 60, 150, 1440]) {
    context.draftValue = String(minutes);
    context.onChange = (value) => assert.equal(value, minutes);
    commitValue();
  }
});

test("negative timeout drafts restore the previous value without staging an indefinite wait", () => {
  const context = vm.createContext({});
  load(context, ["getFieldLimits"]);
  const limits = vm.runInContext(
    'getFieldLimits("webui_unattended_prompt_timeout")',
    context,
  );
  const staged = [];
  let displayed;
  Object.assign(context, limits, {
    isEditing: { current: true },
    cancelCommit: { current: false },
    normalizedValue: 60,
    setDraftValue: (value) => {
      displayed = value;
    },
    onChange: (value) => staged.push(value),
  });
  const commit = declarations.get("commitDraftValue");
  const commitValue = vm.runInContext(
    `(${source.slice(commit.start, commit.end)})`,
    context,
  );
  for (const draft of ["-1", "-0.5"]) {
    context.draftValue = draft;
    commitValue();
    assert.deepEqual(staged, []);
    assert.equal(displayed, "60");
  }
});

test("other numeric settings retain their existing clamping behaviour", () => {
  const context = vm.createContext({});
  load(context, ["getFieldLimits"]);
  const limits = vm.runInContext('getFieldLimits("screens")', context);
  let staged;
  Object.assign(context, limits, {
    rejectOutOfRange: false,
    isEditing: { current: true },
    cancelCommit: { current: false },
    normalizedValue: 6,
    draftValue: "-1",
    setDraftValue: () => {},
    onChange: (value) => {
      staged = value;
    },
  });
  const commit = declarations.get("commitDraftValue");
  vm.runInContext(`(${source.slice(commit.start, commit.end)})()`, context);
  assert.equal(staged, 1);
});
