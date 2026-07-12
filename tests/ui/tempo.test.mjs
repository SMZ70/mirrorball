/**
 * The tempo is the panel's, except when it is not.
 *
 * The panel owns the bpm -- if it took the server's, a typed tempo would be
 * overwritten by the server's clock before the push could land (the same echo
 * bug as the sliders, one control over). The single exception is TAP: the
 * server measured the taps, so there it genuinely knows better.
 *
 * That "single exception" is the whole risk. It must fire exactly once, or the
 * tempo drifts back to whatever the server last thought.
 */

import { boot, sleep, state } from "./harness.mjs";

export default async function (t) {
  const p = await boot();
  const bpm = () => p.$("#bpm");
  const stale = () => p.feed(state());          // the server still says 120

  stale();
  await sleep(10);
  t.check("shows the tempo", bpm().value, "120");

  // Typed, and then hammered with a second of the server's old number.
  p.run("setBpm(138)");
  for (let i = 0; i < 12; i++) { stale(); await sleep(15); }
  t.check("a typed tempo survives the echo", p.run("show.bpm"), 138);
  t.check("the field agrees", bpm().value, "138");
  t.check("the server was told", p.lastSent("show").show.bpm, 138);

  p.run("nudgeBpm(-3)");
  await sleep(10);
  t.check("nudge moves it", p.run("show.bpm"), 135);

  p.run("setBpm(9000)");
  t.check("clamped to what the server accepts (high)", p.run("show.bpm"), 220);
  p.run("setBpm(1)");
  t.check("clamped (low)", p.run("show.bpm"), 40);

  // TAP: the server did the measuring, so its answer wins -- once.
  p.run("setBpm(100)");
  p.run("tap()");
  t.check("asks the server to measure", p.lastSent("tap"), { type: "tap" });

  p.feed(state({ bpm: 143.2 }));
  await sleep(10);
  t.check("takes the tapped tempo", p.run("show.bpm"), 143.2);
  t.check("and shows it", bpm().value, "143");

  for (let i = 0; i < 8; i++) { stale(); await sleep(15); }
  t.check("and does not then drift back", p.run("show.bpm"), 143.2);

  p.close();
}
