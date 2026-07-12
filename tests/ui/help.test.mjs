/**
 * Help is a mode, because a phone has no hover and therefore no tooltips.
 *
 * The failure this guards against is quiet: add a control, forget its help
 * entry, and it silently renders nothing. So the count is asserted, not just
 * "some help appeared".
 */

import { boot, sleep, state } from "./harness.mjs";

const SETTINGS = ["shape", "rate", "curve", "mode", "hue", "phase", "duty", "bri", "level", "solo"];

export default async function (t) {
  const p = await boot();

  p.feed(state());
  await sleep(10);
  p.run("toggleOpen('t0')");

  t.check("off by default", p.$$(".help").length, 0);
  t.check("no guide either", p.$("#guide").className, "");

  p.run("toggleHelp()");
  await sleep(10);

  t.check("every setting explains itself", p.$$("#tracks .help").length, SETTINGS.length);
  t.check("the transport is explained too", p.$("#guide").className, "show");
  t.check("including what BLACK actually does",
          p.$("#guide").textContent.includes("hides"), true);
  t.check("and that stop hands the lights back",
          p.$("#guide").textContent.includes("hands the lights back"), true);
  t.check("it is remembered", p.window.localStorage.getItem("mmdj.help"), "1");

  p.run("toggleHelp()");
  await sleep(10);
  t.check("and gets out of the way", p.$$(".help").length, 0);

  p.close();
}
