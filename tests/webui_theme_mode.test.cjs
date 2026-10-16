const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const babel = require("../web_ui/static/js/node_modules/@babel/core");
const scriptPath = (name) => path.join(__dirname, "../web_ui/static/js", name);
const shared = fs.readFileSync(scriptPath("shared_utils.js"), "utf8");

function fixture(blockStorage = false) {
  const stored = new Map();
  const context = vm.createContext({
    window: {},
    document: { documentElement: { dataset: {} } },
    localStorage: {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => {
        if (blockStorage) throw new Error("Storage unavailable");
        stored.set(key, value);
      },
    },
  });
  vm.runInContext(shared, context);
  return { context, stored };
}

test("changing mode updates the page even when storage is unavailable", () => {
  for (const blockStorage of [false, true]) {
    const { context, stored } = fixture(blockStorage);
    for (const dark of [true, false, true]) {
      context.window.setUAThemeMode(dark);
      const mode = dark ? "dark" : "light";
      assert.equal(context.document.documentElement.dataset.uaMode, mode);
      if (!blockStorage) assert.equal(stored.get("ua_config_theme"), mode);
    }
  }
});

for (const name of ["app.js", "config_app.js", "stats_app.js"]) {
  test(`${name}: mode changes propagate to the document and saved preference`, () => {
    const source = fs.readFileSync(scriptPath(name), "utf8");
    const ast = babel.parseSync(source, { parserOpts: { plugins: ["jsx"] } });
    const effects = [];
    function walk(node) {
      if (!node || typeof node !== "object") return;
      if (
        node.type === "CallExpression" &&
        node.callee.name === "useEffect" &&
        node.arguments[1]?.type === "ArrayExpression" &&
        node.arguments[1].elements.length === 1 &&
        node.arguments[1].elements[0]?.name === "isDarkMode"
      )
        effects.push(node.arguments[0]);
      for (const [key, value] of Object.entries(node)) {
        if (["loc", "tokens", "comments"].includes(key)) continue;
        if (Array.isArray(value)) value.forEach(walk);
        else if (value && typeof value === "object") walk(value);
      }
    }
    walk(ast);
    assert.equal(effects.length, 1);
    const { context, stored } = fixture();
    for (const dark of [true, false]) {
      context.isDarkMode = dark;
      vm.runInContext(
        `(${source.slice(effects[0].start, effects[0].end)})()`,
        context,
      );
      assert.equal(
        context.document.documentElement.dataset.uaMode,
        dark ? "dark" : "light",
      );
      assert.equal(stored.get("ua_config_theme"), dark ? "dark" : "light");
    }
  });
}
