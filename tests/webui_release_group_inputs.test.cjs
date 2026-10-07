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
let blurHandler;
babel.traverse(ast, {
  FunctionDeclaration(functionPath) {
    if (functionPath.node.id.name !== "ReleaseGroupOverrides") return;
    functionPath.traverse({
      JSXAttribute(attributePath) {
        if (attributePath.node.name.name === "onBlur") {
          blurHandler = attributePath.node.value.expression;
        }
      },
    });
  },
});
assert.ok(blurHandler, "Release group inputs need a blur handler");

function blur(
  fieldType,
  value,
  key = "screens_per_row",
  minimum = 0,
  inheritedValue = 400,
) {
  const changes = [];
  const values = { [key]: value, custom_signature: "Saved signature" };
  const context = vm.createContext({
    field: { key, field_type: fieldType, field_min: minimum },
    inherited: { value: inheritedValue },
    name: "FictionalGroup",
    groups: { FictionalGroup: values, OtherGroup: { screens_per_row: 3 } },
    values,
    updateGroups: (groups) => changes.push(JSON.parse(JSON.stringify(groups))),
  });
  const handler = vm.runInContext(
    `(${source.slice(blurHandler.start, blurHandler.end)})`,
    context,
  );
  handler({ target: { value } });
  return changes;
}

test("clearing a numeric group override resets it to zero on blur and preserves other fields", () => {
  assert.deepEqual(blur("number", ""), [
    {
      FictionalGroup: {
        screens_per_row: 0,
        custom_signature: "Saved signature",
      },
      OtherGroup: { screens_per_row: 3 },
    },
  ]);
});

test("blur preserves numeric edits including zero and intentional blank text", () => {
  for (const value of ["400", "0", "3"]) {
    assert.deepEqual(blur("number", value), []);
  }
  assert.deepEqual(blur("text", ""), []);
});

test("empty image sizes restore a positive inherited size instead of zero", () => {
  for (const key of [
    "thumbnail_size",
    "pack_thumb_size",
    "logo_size",
    "bluray_image_size",
  ]) {
    for (const [inherited, expected] of [
      [400, 400],
      ["300", 300],
      [0, 1],
      ["", 1],
      ["invalid", 1],
    ]) {
      assert.equal(
        blur("number", "", key, 1, inherited)[0].FictionalGroup[key],
        expected,
      );
    }
    assert.deepEqual(blur("number", "400", key, 1), []);
  }
});
