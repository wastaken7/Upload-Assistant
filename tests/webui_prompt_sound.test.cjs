const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "../web_ui/static/js/prompt_sound.js"),
  "utf8",
);

function setup({
  state = "running",
  unavailable = false,
  rejectResume = false,
} = {}) {
  const contexts = [];
  class AudioContext {
    constructor() {
      this.state = state;
      this.currentTime = 10;
      this.destination = {};
      this.oscillators = [];
      this.gains = [];
      this.resumeCalls = 0;
      contexts.push(this);
    }
    async resume() {
      this.resumeCalls++;
      if (rejectResume) throw new Error("Audio blocked");
      this.state = "running";
    }
    createOscillator() {
      const node = {
        frequency: { setValueAtTime() {} },
        connect(target) {
          this.target = target;
        },
        disconnect() {
          this.disconnected = true;
        },
        start(time) {
          this.startTime = time;
        },
        stop(time) {
          this.stopTime = time;
        },
      };
      this.oscillators.push(node);
      return node;
    }
    createGain() {
      const node = {
        gain: {
          setValueAtTime() {},
          linearRampToValueAtTime() {},
          exponentialRampToValueAtTime() {},
        },
        connect(target) {
          this.target = target;
        },
        disconnect() {
          this.disconnected = true;
        },
      };
      this.gains.push(node);
      return node;
    }
  }
  const window = unavailable ? {} : { AudioContext };
  vm.runInNewContext(script, { window });
  return { sound: window.uaPromptSound, contexts };
}

test("loading the page and receiving sound before Execute create no audio", () => {
  const { sound, contexts } = setup();
  sound.play();
  assert.equal(contexts.length, 0);
});

test("Execute silently unlocks audio and reuses the context", () => {
  const { sound, contexts } = setup({ state: "suspended" });
  sound.unlock();
  sound.unlock();
  assert.equal(contexts.length, 1);
  assert.equal(contexts[0].resumeCalls, 1);
  assert.equal(contexts[0].oscillators.length, 0);
});

test("each sound event plays a short tone and disconnects finished nodes", () => {
  const { sound, contexts } = setup();
  sound.unlock();
  sound.play();
  const context = contexts[0];
  const oscillator = context.oscillators[0];
  const gain = context.gains[0];
  assert.equal(context.oscillators.length, 1);
  assert.equal(oscillator.startTime, 10);
  assert.equal(oscillator.stopTime, 10.6);
  assert.equal(oscillator.target, gain);
  assert.equal(gain.target, context.destination);
  oscillator.onended();
  assert.equal(oscillator.disconnected, true);
  assert.equal(gain.disconnected, true);
  sound.play();
  assert.equal(context.oscillators.length, 2);
});

test("unsupported audio does not interrupt execution", () => {
  const { sound } = setup({ unavailable: true });
  assert.doesNotThrow(() => {
    sound.unlock();
    sound.play();
  });
});

test("blocked audio is caught and never queues stale prompt sounds", async () => {
  const { sound, contexts } = setup({ state: "suspended", rejectResume: true });
  sound.unlock();
  sound.play();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(contexts[0].oscillators.length, 0);
  contexts[0].state = "running";
  assert.equal(contexts[0].oscillators.length, 0);
});

test("a closed context can be recreated on the next Execute click", () => {
  const { sound, contexts } = setup();
  sound.unlock();
  contexts[0].state = "closed";
  sound.play();
  sound.unlock();
  sound.play();
  assert.equal(contexts.length, 2);
  assert.equal(contexts[0].oscillators.length, 0);
  assert.equal(contexts[1].oscillators.length, 1);
});

test("audio device errors cannot interrupt the output stream", () => {
  const { sound, contexts } = setup();
  sound.unlock();
  contexts[0].createOscillator = () => {
    throw new Error("Device unavailable");
  };
  assert.doesNotThrow(() => sound.play());
});
