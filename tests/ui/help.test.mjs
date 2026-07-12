/**
 * Help is a mode, because a phone has no hover and therefore no tooltips.
 *
 * The failure this guards against is quiet: add a control, forget its help
 * entry, and it silently renders nothing. So the count is asserted, not just
 * "some help appeared".
 */

import { boot, sleep, state } from "./harness.mjs";

// Always shown for a plain, unlinked track.
const ALWAYS = ["lights", "shape", "rate", "curve", "mode", "hue", "phase", "duty",
                "bri", "level", "follows", "solo"];

export default async function (t) {
  const p = await boot();

  p.feed(state());
  await sleep(10);
  p.run("toggleOpen('t0')");

  t.check("off by default", p.$$(".help").length, 0);
  t.check("no guide either", p.$("#guide").className, "");

  p.run("toggleHelp()");
  await sleep(10);

  t.check("every setting explains itself", p.$$("#tracks .help").length, ALWAYS.length);
  t.check("the transport is explained too", p.$("#guide").className, "show");
  t.check("including what BLACK actually does",
          p.$("#guide").textContent.includes("hides"), true);
  t.check("and that stop hands the lights back",
          p.$("#guide").textContent.includes("hands the lights back"), true);
  t.check("it is remembered", p.window.localStorage.getItem("mirrorball.help"), "1");

  // The two controls that only exist in context must explain themselves there,
  // and nowhere else -- help for a control you cannot see is noise.
  p.run("toggleLight('t0','l1')");                 // now a group: spread appears
  await sleep(10);
  t.check("a group's spread is explained", p.$$("#tracks .help").length, ALWAYS.length + 1);

  // A follower inherits its leader's whole pattern -- shape, rate, curve, colour
  // mode AND palette -- so none of those are its to edit. What it gets instead is
  // the relation. The editor must show exactly that, or it is offering a lie.
  p.run("setLink('t0',{follow:'t1'})");
  await sleep(10);
  const rows = p.$$("#tracks .row label").map((e) => e.textContent.trim());
  t.check("a follower is offered its relation, not a pattern", rows,
          ["lights", "spread", "follows", "speed", "hue ±",
           "phase", "duty", "min", "max", "level"]);

  p.run("toggleHelp()");
  await sleep(10);
  t.check("and gets out of the way", p.$$(".help").length, 0);

  p.close();
}
