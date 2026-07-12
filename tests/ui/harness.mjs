/**
 * The panel, in a fake browser.
 *
 * These tests load the REAL web/index.html and web/app.js -- not a copy, not a
 * mock -- and drive them through a fake WebSocket. That is the point: every bug
 * they have caught so far lived in the seam between the panel and the socket,
 * and a test that stubbed either side would have missed all of them.
 *
 * The one that keeps coming back: the server broadcasts the whole show ten
 * times a second, and if the panel takes those echoes it undoes whatever the
 * user is doing right now. It has eaten the sliders and then the tempo. So the
 * fixtures below deliberately echo a STALE show, and the tests assert the
 * panel's own value survives.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM, VirtualConsole } from "jsdom";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const HTML = readFileSync(join(ROOT, "web/index.html"), "utf8");
const APP = readFileSync(join(ROOT, "web/app.js"), "utf8");

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Fixtures ────────────────────────────────────────────────────────────────

export const track = (i = 0, over = {}) => ({
  id: `t${i}`, target: `l${i}`, name: `Light ${i}`, target_kind: "light",
  shape: "pulse", curve: "sine", rate: 1.0, phase: 0.1 * i, duty: 0.5,
  palette: { hue_from: 30, hue_to: 55, saturation: 1.0, mode: "cycle" },
  bri_min: 8, bri_max: 100, level: 1.0, mute: false, solo: false, seed: i,
  ...over,
});

export const show = (over = {}) => ({
  version: 1, name: "party", bpm: 120, blackout: false,
  master: { brightness: 1.0, energy: 1.0 },
  tracks: [track(0), track(1)],
  ...over,
});

export const state = (over = {}) => ({
  type: "state",
  show: show(),
  playing: false,
  beat: 0,
  bpm: 120,
  shows: [],
  presets: [
    { name: "party", note: "one of each", bpm: 120, hues: [[30, 55], [320, 350]] },
    { name: "rave", note: "hard strobe", bpm: 140, hues: [[180, 200]] },
    { name: "sunset", note: "a long drift", bpm: 60, hues: [[10, 300]] },
  ],
  lights: [
    { id: "l0", name: "Light 0", room: "R" },
    { id: "l1", name: "Light 1", room: "R" },
  ],
  area: "Music area",
  ...over,
});

// ── The fake browser ────────────────────────────────────────────────────────

export async function boot() {
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously",
    url: "http://mmdj.test/",
    pretendToBeVisual: true,
    virtualConsole: new VirtualConsole(),   // jsdom's "not implemented" noise
  });
  const { window } = dom;

  const sent = [];
  class FakeWS {
    static OPEN = 1;
    constructor() {
      this.readyState = 1;
      FakeWS.last = this;
      setTimeout(() => this.onopen?.(), 0);
    }
    send(data) { sent.push(JSON.parse(data)); }
    close() {}
  }
  window.WebSocket = FakeWS;

  const script = window.document.createElement("script");
  script.textContent = APP;
  window.document.body.appendChild(script);
  await sleep(20);

  return {
    window,
    sent,                                            // every message the panel sent
    feed: (msg) => FakeWS.last.onmessage({ data: JSON.stringify(msg) }),
    run: (js) => window.eval(js),                    // call the panel's own functions
    $: (sel) => window.document.querySelector(sel),
    $$: (sel) => [...window.document.querySelectorAll(sel)],
    lastSent: (type) => sent.filter((m) => m.type === type).at(-1),
    close: () => window.close(),
  };
}
