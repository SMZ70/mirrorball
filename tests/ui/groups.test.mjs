/**
 * Grouping and linking, from the panel's side.
 *
 * The two rules that keep this coherent, and which are easy to break:
 *
 *   1. A light belongs to exactly ONE track. Two tracks driving the same bulb
 *      just fight, and whichever renders last wins -- a coin toss dressed up as
 *      a feature. So adding a light to a track must remove it from its old one.
 *
 *   2. A follower has no pattern of its own. Showing it a shape picker would be
 *      a lie: the shape comes from its leader. So those controls are replaced by
 *      the relation controls.
 */

import { boot, sleep, state } from "./harness.mjs";

export default async function (t) {
  const p = await boot();
  const labels = (sel) => p.$$(sel).map((e) => e.textContent.trim());

  p.feed(state());
  await sleep(10);
  p.run("toggleOpen('t0')");

  // ── Grouping ────────────────────────────────────────────────────────────
  t.check("every light in the area is offerable", labels("#tracks .row .seg").slice(0, 2),
          ["Light 0", "Light 1"]);
  t.check("this track holds its own light", p.run("show.tracks[0].targets"), ["l0"]);

  // Take light 1 from the other track: it must LEAVE that track, not be shared.
  p.run("toggleLight('t0','l1')");
  await sleep(10);
  t.check("the light joins this track", p.run("show.tracks[0].targets"), ["l0", "l1"]);
  t.check("and leaves the one it was in", p.run("show.tracks[1].targets"), []);
  t.check("no light is driven twice", p.run(
    "new Set(show.tracks.flatMap(t => t.targets)).size === show.tracks.flatMap(t => t.targets).length"),
          true);

  t.check("the head says it is a group", !!p.$("#tracks .chip.g"), true);

  // A group -- and only a group -- gets a spread control.
  const spread = () => p.$$("#tracks input[type=range]")
    .find((i) => i.getAttribute("oninput").includes("spread"));
  t.check("a group gets a spread control", !!spread(), true);

  spread().value = "1";
  spread().dispatchEvent(new p.window.Event("input", { bubbles: true }));
  await sleep(80);
  t.check("spread is sent to the server", p.lastSent("show").show.tracks[0].spread, 1);

  p.run("toggleLight('t0','l1')");                 // give it back
  await sleep(10);
  t.check("a single light has no spread control", !!spread(), false);

  // ── Linking ─────────────────────────────────────────────────────────────
  p.run("setLink('t1',{follow:'t0'})");
  await sleep(10);
  t.check("the link is made", p.run("show.tracks[1].link.follow"), "t0");
  t.check("with sane defaults",
          p.run("[show.tracks[1].link.rate_scale, show.tracks[1].link.hue_shift, show.tracks[1].link.invert]"),
          [1, 0, false]);

  p.run("toggleOpen('t1')");
  await sleep(10);
  const rows = labels("#tracks .row label");
  t.check("a follower is not offered a shape it does not own", rows.includes("shape"), false);
  t.check("it is offered the relation instead", rows.includes("hue ±"), true);
  t.check("and is told where its pattern comes from", !!p.$("#tracks .note"), true);

  p.run("setLink('t1',{invert:true, rate_scale:2})");
  await sleep(80);
  const link = p.lastSent("show").show.tracks[1].link;
  t.check("invert reaches the server", link.invert, true);
  t.check("so does the speed", link.rate_scale, 2);

  p.run("setLink('t1',{follow:''})");
  await sleep(10);
  t.check("and it can be broken", p.run("show.tracks[1].link"), null);

  p.close();
}
