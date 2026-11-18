const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");
const babel = require("../web_ui/static/js/node_modules/@babel/core");

const shared = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/shared_utils.js"),
  "utf8",
);
const ast = babel.parseSync(shared, { parserOpts: { plugins: ["jsx"] } });
const helper = ast.program.body[0].expression.callee.body.body.find(
  (node) => node.id?.name === "uaApiFetch",
);

const reauthChallenge = () =>
  new Response(JSON.stringify({ reauth_required: true, totp_required: true }), {
    status: 403,
    headers: { "X-UA-Reauth-Required": "1" },
  });
const csrfFailure = () => new Response("{}", { status: 403 });
const ok = () => new Response("{}", { status: 200 });

function fixture(responses, promptResult = true) {
  const prompts = [];
  const calls = [];
  const context = vm.createContext({
    Response,
    uaCsrfToken: "fictional-token",
    loadCsrfToken: async () => {},
    clearCsrfToken: () => {},
    window: {
      UAReauthPrompt: async (info) => {
        prompts.push(info);
        return promptResult;
      },
    },
    fetch: async (url) => {
      calls.push(url);
      return responses.shift()();
    },
  });
  vm.runInContext(shared.slice(helper.start, helper.end), context);
  return { context, prompts, calls };
}

test("a stale CSRF token still reaches the password prompt", async () => {
  const { context, prompts, calls } = fixture([
    csrfFailure,
    reauthChallenge,
    ok,
  ]);
  const response = await context.uaApiFetch("/api/config_update", {
    method: "POST",
  });
  assert.equal(response.status, 200);
  assert.equal(prompts.length, 1);
  assert.equal(prompts[0].totpRequired, true);
  assert.equal(calls.length, 3);
});

test("a confirmed request can still refresh its CSRF token", async () => {
  const { context, calls } = fixture([reauthChallenge, csrfFailure, ok]);
  const response = await context.uaApiFetch("/api/config_update", {
    method: "POST",
  });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 3);
});

test("the prompt is shown once and a cancel returns the challenge", async () => {
  const { context, prompts, calls } = fixture([reauthChallenge], false);
  const response = await context.uaApiFetch("/api/config_update", {
    method: "POST",
  });
  assert.equal(response.status, 403);
  assert.equal(prompts.length, 1);
  assert.equal(calls.length, 1);
});

test("a second challenge after confirming does not loop", async () => {
  const { context, prompts, calls } = fixture([
    reauthChallenge,
    reauthChallenge,
  ]);
  const response = await context.uaApiFetch("/api/config_update", {
    method: "POST",
  });
  assert.equal(response.status, 403);
  assert.equal(prompts.length, 1);
  assert.equal(calls.length, 2);
});
