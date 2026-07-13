/**
 * A solo silences every other track. That is correct -- and it was invisible,
 * because the S badge lives inside one collapsed track row. A solo latched on a
 * track you were not looking at read as "my other groups stopped playing", and
 * it was being SAVED into shows, so it came back days later.
 */
import { boot, show, sleep, state, track } from "./harness.mjs";

export default async function (t) {
  const p = await boot();

  // A show recalled with a solo latched on the last track -- the exact shape of
  // the saved shows that caused this.
  p.feed(state({ show: show({ tracks: [track(0), track(1, { solo: true })] }) }));
  await sleep(30);

  const banner = p.$("#soloing");
  t.check("a soloed track raises the banner", banner.className, "on");
  t.check("it says a solo is in force", /SOLO/.test(banner.textContent), true);
  t.check("and that the rest are silenced", /silenced/.test(banner.textContent), true);

  p.run("clearSolo()");
  await sleep(100);

  t.check("one tap clears it", p.$("#soloing").className, "");
  t.check("and the solo is pushed off",
    p.lastSent("show").show.tracks.map((x) => x.solo), [false, false]);

  p.feed(state({ show: show({ tracks: [track(0), track(1)] }) }));
  await sleep(30);
  t.check("no banner when nothing is soloed", p.$("#soloing").className, "");

  p.close();
}
