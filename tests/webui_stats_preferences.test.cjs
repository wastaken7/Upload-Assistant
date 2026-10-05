const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const babel = require("../web_ui/static/js/node_modules/@babel/core");
const source = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/stats_app.js"),
  "utf8",
);
const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });

function fixture(stored = new Map()) {
  let state;
  const context = vm.createContext({
    window: {
      UAStorage: {
        get: (key) => stored.get(key) ?? null,
        set: (key, value) => stored.set(key, value),
      },
    },
    useState: (initialize) => {
      state = initialize();
      return [state, (value) => (state = value)];
    },
  });
  for (const node of ast.program.body) {
    if (
      node.id?.name === "useStatsViewPreference" ||
      node.declarations?.some((d) => d.id.name === "STATS_VIEW_KEY_PREFIX")
    ) {
      vm.runInContext(source.slice(node.start, node.end), context);
    }
  }
  return {
    stored,
    mount: (key, fallback, allowed) =>
      context.useStatsViewPreference(key, fallback, allowed),
    state: () => state,
  };
}

test("chart and table choices survive remounts independently for each block", () => {
  const page = fixture();
  const chart = (key) => page.mount(key + "_chart", "donut", ["donut", "bar"]);
  const table = (key) => page.mount(key + "_table", false, [true, false]);
  assert.equal(chart("cache-by-provider")[0], "donut");
  chart("cache-by-provider")[1]("bar");
  assert.equal(page.state(), "bar");
  table("cache-by-provider")[1](true);
  assert.equal(chart("external-operations")[0], "donut");
  assert.equal(table("external-operations")[0], false);

  const reloaded = fixture(page.stored);
  assert.equal(
    reloaded.mount("cache-by-provider_chart", "donut", ["donut", "bar"])[0],
    "bar",
  );
  const [open, close] = reloaded.mount("cache-by-provider_table", false, [
    true,
    false,
  ]);
  assert.equal(open, true);
  close(false);
  assert.equal(
    fixture(page.stored).mount("cache-by-provider_table", false, [
      true,
      false,
    ])[0],
    false,
  );
});

test("invalid saved preferences fall back to supported defaults", () => {
  for (const stored of ["invalid json", '"pie"', "null", "{}", "true"]) {
    const page = fixture(
      new Map([["ua_stats_view_v1_categories_chart", stored]]),
    );
    assert.equal(
      page.mount("categories_chart", "donut", ["donut", "bar"])[0],
      "donut",
    );
  }
  const page = fixture(
    new Map([["ua_stats_view_v1_categories_table", '"true"']]),
  );
  assert.equal(page.mount("categories_table", false, [true, false])[0], false);
});

test("restoring an expanded table does not overwrite it and native toggles save changes", () => {
  const component = ast.program.body.find(
    (node) => node.id?.name === "PersistentStatsDetails",
  );
  const details = component.body.body.find(
    (node) => node.type === "ReturnStatement",
  ).argument;
  const handler = details.openingElement.attributes.find(
    (attribute) => attribute.name?.name === "onToggle",
  ).value.expression;
  const changes = [];
  const context = vm.createContext({
    open: true,
    setOpen: (value) => changes.push(value),
  });
  const toggle = vm.runInContext(
    source.slice(handler.start, handler.end),
    context,
  );
  toggle({ currentTarget: { open: true } });
  assert.deepEqual(changes, []);
  toggle({ currentTarget: { open: false } });
  assert.deepEqual(changes, [false]);
  context.open = false;
  toggle({ currentTarget: { open: true } });
  assert.deepEqual(changes, [false, true]);
});

test("every distribution chart and expandable stats table has a stable preference key", () => {
  const keys = new Map();
  babel.traverse(ast, {
    JSXOpeningElement({ node }) {
      const name = node.name.name;
      if (
        ![
          "DistributionChart",
          "ChartWithTable",
          "PersistentStatsDetails",
        ].includes(name)
      )
        return;
      const key = node.attributes.find(
        (attribute) => attribute.name?.name === "preferenceKey",
      );
      assert.ok(key, `${name} is missing its preference key`);
      const value = source.slice(key.value.start, key.value.end);
      const group = keys.get(name) || new Set();
      assert.ok(
        !group.has(value),
        `${name} has a duplicate preference key: ${value}`,
      );
      group.add(value);
      keys.set(name, group);
    },
  });
  assert.equal(keys.get("DistributionChart").size, 5);
  assert.equal(keys.get("ChartWithTable").size, 10);
});

test("daily activity restores each series and validates saved values independently", () => {
  let stored = null;
  const context = vm.createContext({
    window: { UAStorage: { get: () => stored } },
  });
  for (const node of ast.program.body) {
    if (
      node.id?.name === "loadTrendSeries" ||
      node.declarations?.some((d) =>
        ["TREND_SERIES_KEY", "DEFAULT_TREND_SERIES"].includes(d.id.name),
      )
    ) {
      vm.runInContext(source.slice(node.start, node.end), context);
    }
  }
  const load = () => JSON.parse(JSON.stringify(context.loadTrendSeries()));
  const defaults = load();
  stored = JSON.stringify({
    ...defaults,
    items: false,
    api: true,
    uploaded_bytes: false,
  });
  assert.deepEqual(load(), {
    ...defaults,
    items: false,
    api: true,
    uploaded_bytes: false,
  });
  stored = JSON.stringify({
    items: false,
    api: "true",
    uploads: null,
    unknown: true,
  });
  assert.deepEqual(load(), { ...defaults, items: false });
  for (const invalid of ["broken json", "null", "[]"]) {
    stored = invalid;
    assert.deepEqual(load(), defaults);
  }
});
