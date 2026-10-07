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

function blur(fieldType, value) {
  const changes = [];
  const values = { thumbnail_size: value, custom_signature: "Saved signature" };
  const context = vm.createContext({
    field: { key: "thumbnail_size", field_type: fieldType },
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
        thumbnail_size: 0,
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
