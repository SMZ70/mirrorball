/**
 * The playground, in the panel.
 *
 * The property under test is not "the playground works" -- it is "the live panel
 * still does, and nothing the playground does can reach it". The editor is SHARED
 * between the two modes, so the only thing standing between a sandbox experiment
 * and someone's actual living room is which message type goes on the wire. That
 * is one function, and it is worth pinning hard.
 */
import { boot, show, sleep, state, track } from "./harness.mjs";

const pg = (over = {}) => ({
  rig: "real",
  count: 8,
  running: false,
  bpm: 120,
  max: 24,
  savable: true,
  show: show({ name: "playground", bpm: 90 }),
  lights: [
    { id: "l0", name: "Light 0", room: "R" },
    { id: "l1", name: "Light 1", room: "R" },
  ],
  ...over,
});

export default async function (t) {
  const p = await boot();
  p.feed(state({ pg: pg() }));
  await sleep(30);

  // ── The live panel is exactly as it was ──────────────────────────────────
  t.check("no stage in live mode", p.$("#stage").className, "");
  t.check("no rig chooser in live mode", p.$("#rig").className, "");
  t.check("live is the mode you start in", p.run("mode"), "live");

  // ── In the playground, every message is namespaced ───────────────────────
  p.run("setMode('pg')");
  p.feed(state({ pg: pg() }));
  await sleep(30);

  t.check("the stage appears", p.$("#stage").className, "show");
  // Before ▶ there are no frames yet. The lamps must still be THERE, dark and
  // waiting -- an empty box reads as "the playground did not work".
  t.check("the rig is drawn before you press play",
    p.window.document.querySelectorAll("#stage .bulb").length, 2);
  t.check("and the panel says it is sandboxed",
    p.window.document.body.className.includes("pg"), true);

  const before = p.sent.length;
  p.run("togglePlay()");
  p.run("toggleBlackout()");
  p.run("loadPreset('rave')");
  p.run("saveShow()");
  p.run("tap()");
  p.run("setTrack('t0', {shape:'strobe'})");
  await sleep(120);

  const after = p.sent.slice(before);
  t.check("NOTHING addresses the live show from the playground",
    after.filter((m) => !m.type.startsWith("pg.")).map((m) => m.type), []);
  t.check("play is sent, but sandboxed",
    after.some((m) => m.type === "pg.play"), true);
  t.check("and so are edits", after.some((m) => m.type === "pg.show"), true);

  // ── Switching back restores the live show, unpolluted ────────────────────
  p.run("setMode('live')");
  await sleep(30);
  t.check("the live show is as we left it", p.run("show").name, "party");

  const n = p.sent.length;
  p.run("setTrack('t0', {shape:'pulse'})");
  await sleep(120);
  const live = p.sent.slice(n).filter((m) => m.type === "show");
  t.check("live edits address the live show again", live.length, 1);
  t.check("and carry the live show, not the sandbox", live[0].show.name, "party");

  // ── The stage draws exactly what the server rendered ─────────────────────
  p.run("setMode('pg')");
  p.feed(state({ pg: pg() }));
  await sleep(20);
  p.feed({ type: "preview", beat: 1, frames: { l0: { hue: 200, sat: 1, bri: 100 } } });
  await sleep(20);

  // jsdom resolves hsl() to rgb(), so check the colour it actually became:
  // hue 200 is a blue-cyan, and unmistakably not the dark bed.
  const lit = p.window.document.querySelector("#b-l0 .glow");
  const dark = p.window.document.querySelector("#b-l1 .glow");
  const [r, g, b] = lit.style.background.match(/\d+/g).map(Number);
  t.check("a lit bulb takes the frame's colour", b > g && g > r, true);
  t.check("and glows", lit.style.boxShadow !== "none" && !!lit.style.boxShadow, true);
  t.check("a light with no frame stays dark", dark.style.background, "rgb(20, 22, 28)");

  // ── The editor offers the rig you are ON, not the one you are not ────────
  // The chips read the LIVE light list in both modes, so picking a virtual rig
  // still offered your real bulbs -- lights the show is not even dealt onto.
  const virtualRig = () => pg({
    rig: "virtual",
    count: 3,
    show: show({ tracks: [track(0, { targets: ["v0"] })] }),
    lights: [
      { id: "v0", name: "Lamp 1", room: "Virtual rig" },
      { id: "v1", name: "Lamp 2", room: "Virtual rig" },
      { id: "v2", name: "Lamp 3", room: "Virtual rig" },
    ],
  });

  p.run("wantShow = true");                 // as setRig() does: take the new show
  p.feed(state({ pg: virtualRig() }));
  await sleep(30);
  p.run("toggleOpen('t0')");
  await sleep(30);

  const chips = [...p.window.document.querySelectorAll(".track.open .segs.rig .seg")]
    .map((e) => e.textContent.trim());
  t.check("the editor offers the VIRTUAL lamps", chips, ["Lamp 1", "Lamp 2", "Lamp 3"]);
  t.check("and not one real light", chips.some((c) => /Light \d/.test(c)), false);

  // ── The rig you are on is never in doubt ─────────────────────────────────
  p.feed(state({ pg: pg({ rig: "virtual", count: 12, savable: false }) }));
  await sleep(20);
  t.check("the panel says which rig you are on",
    /virtual rig · 12 lamps/.test(p.$("#area").textContent), true);

  p.close();
}
