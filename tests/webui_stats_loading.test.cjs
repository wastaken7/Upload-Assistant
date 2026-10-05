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
const app = ast.program.body.find((node) => node.id?.name === "StatsApp");
const load = app.body.body.find((node) =>
  node.declarations?.some((declaration) => declaration.id.name === "load"),
);

function fixture(fetch, signal = { aborted: false }) {
  const state = { data: { previous: true }, error: "", loading: false };
  const context = vm.createContext({
    period: "30d",
    mode: "real",
    settings: { timezone: "utc" },
    activeTracker: "",
    APP_BASE: "http://localhost",
    window: { UA_CSRF_TOKEN: "fictional-csrf" },
    URLSearchParams,
    fetch,
    signal,
    setData: (value) => (state.data = value),
    setError: (value) => (state.error = value),
    setLoading: (value) => (state.loading = value),
  });
  vm.runInContext(source.slice(load.start, load.end), context);
  return { state, run: () => vm.runInContext("load(signal)", context) };
}

test("failed stats requests discard previous filter data", async () => {
  const { state, run } = fixture(async () => ({
    ok: false,
    json: async () => ({ error: "Unable to read statistics" }),
  }));
  await run();
  assert.equal(state.data, null);
  assert.equal(state.error, "Unable to read statistics");
  assert.equal(state.loading, false);
});

test("an unsuccessful payload is shown as an error even with HTTP 200", async () => {
  const { state, run } = fixture(async () => ({
    ok: true,
    json: async () => ({ success: false, error: "Database unavailable" }),
  }));
  await run();
  assert.equal(state.data, null);
  assert.equal(state.error, "Database unavailable");
});

test("aborted older requests cannot replace data or end the new loading state", async () => {
  const signal = { aborted: false };
  const { state, run } = fixture(
    async () => ({
      ok: true,
      json: async () => {
        signal.aborted = true;
        return { success: true, old: true };
      },
    }),
    signal,
  );
  await run();
  assert.deepEqual(state.data, { previous: true });
  assert.equal(state.error, "");
  assert.equal(state.loading, true);
});

test("network failure clears data and a subsequent retry restores it", async () => {
  let fails = true;
  const response = { success: true, timeline: [] };
  const { state, run } = fixture(async () => {
    if (fails) throw new Error("Network unavailable");
    return { ok: true, json: async () => response };
  });
  await run();
  assert.equal(state.data, null);
  assert.equal(state.error, "Network unavailable");
  fails = false;
  await run();
  assert.equal(state.data, response);
  assert.equal(state.error, "");
  assert.equal(state.loading, false);
});
