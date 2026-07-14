/**
 * Tracks, the lights in them, and linking -- from the panel's side.
 *
 * The rules that keep this coherent, and which are easy to break:
 *
 *   1. A light belongs to exactly ONE track. Two tracks driving the same bulb
 *      just fight, and whichever renders last wins -- a coin toss dressed up as
 *      a feature.
 *
 *   2. An EMPTY track cannot exist. It renders nothing and is not a thing in the
 *      room. Take the last light out and the track goes with it. Husks are what
 *      made this list unreadable.
 *
 *   3. A light in no track is UNASSIGNED and says so, out in the open -- not
 *      hidden as an unselected chip inside the editor of an unrelated track.
 *
 *   4. A follower has no pattern of its own. Showing it a shape picker would be
 *      a lie: the shape comes from its leader.
 */

import { boot, show, sleep, state, track } from "./harness.mjs";

const THREE = {
  lights: [
    { id: "l0", name: "Light 0", room: "R" },
    { id: "l1", name: "Light 1", room: "R" },
    { id: "l2", name: "Light 2", room: "R" },   // in no track: free
  ],
  show: show({ tracks: [track(0), track(1)] }),
};

export default async function (t) {
  const p = await boot();
  const labels = (sel) => p.$$(sel).map((e) => e.textContent.trim());

  p.feed(state(THREE));
  await sleep(10);
  p.run("toggleOpen('t0')");
  await sleep(10);

  // ── The editor shows THIS track, and what is actually free ──────────────
  t.check("the editor lists only this track's lights",
    labels("#tracks .segs.rig .seg"), ["Light 0 ×"]);
  t.check("and offers only the lights nobody is using",
    labels("#tracks .segs.free .seg"), ["+ Light 2"]);
  t.check("a free light is visible outside the editor too",
    labels("#spare .seg"), ["+ Light 2"]);

  // ── Grouping ────────────────────────────────────────────────────────────
  p.run("addLight('t0','l2')");
  await sleep(10);
  t.check("adding a light makes a group", p.run("show.tracks[0].targets"), ["l0", "l2"]);
  t.check("the head says so", !!p.$("#tracks .chip.g"), true);
  t.check("and nothing is left free", labels("#spare .seg"), []);

  const spread = () => p.$$("#tracks input[type=range]")
    .find((i) => i.getAttribute("oninput").includes("spread"));
  t.check("a group gets a spread control", !!spread(), true);

  spread().value = "1";
  spread().dispatchEvent(new p.window.Event("input", { bubbles: true }));
  await sleep(80);
  t.check("spread reaches the server", p.lastSent("show").show.tracks[0].spread, 1);

  // ── One light, one track ────────────────────────────────────────────────
  p.run("addLight('t1','l2')");                    // steal it back
  await sleep(10);
  t.check("a stolen light leaves its old track", p.run("show.tracks[0].targets"), ["l0"]);
  t.check("no light is driven twice", p.run(
    "new Set(show.tracks.flatMap(x => x.targets)).size === show.tracks.flatMap(x => x.targets).length"),
    true);
  t.check("a single light has no spread control", !!spread(), false);

  // ── Rule 2: no husks ────────────────────────────────────────────────────
  p.run("dropLight('t1','l1')");                   // t1 still holds l2
  await sleep(10);
  t.check("dropping one of several lights keeps the track",
    p.run("show.tracks.map(x => x.id)"), ["t0", "t1"]);

  p.run("dropLight('t1','l2')");                   // now it is the last one
  await sleep(10);
  t.check("taking the LAST light out deletes the track",
    p.run("show.tracks.map(x => x.id)"), ["t0"]);
  t.check("and its lights are free again",
    labels("#spare .seg"), ["+ Light 1", "+ Light 2"]);

  // ── Rule 3: build one from nothing, on a light YOU name ─────────────────
  // "+ Track" used to grab the first free light and hope. Which light a track is
  // for is not a decision the panel gets to make.
  p.run("addTrack()");
  await sleep(20);
  t.check("+ Track with no light named creates nothing",
    p.run("show.tracks.length"), 1);

  p.run("togglePicker()");
  await sleep(20);
  t.check("it asks which light instead", p.$("#picker").className, "show");
  t.check("offering exactly the free ones",
    labels("#picker .seg"), ["Light 1", "Light 2"]);

  p.run("addTrack('l1')");
  await sleep(80);
  t.check("a track can be built from a free light, no preset needed",
    p.run("show.tracks.length"), 2);
  t.check("it holds that light", p.run("show.tracks[1].targets"), ["l1"]);
  t.check("it opens ready to shape", p.run("open"), p.run("show.tracks[1].id"));
  t.check("and the panel pushed it", p.lastSent("show").show.tracks.length, 2);

  // ── Linking, and deleting a leader ──────────────────────────────────────
  const second = p.run("show.tracks[1].id");
  p.run(`setLink('${second}',{follow:'t0'})`);
  await sleep(10);
  t.check("the link is made", p.run("show.tracks[1].link.follow"), "t0");
  t.check("with sane defaults",
    p.run("[show.tracks[1].link.rate_scale, show.tracks[1].link.hue_shift, show.tracks[1].link.invert]"),
    [1, 0, false]);

  // addTrack already left it open -- toggling would close it.
  const rows = labels("#tracks .row label");
  t.check("a follower is not offered a shape it does not own", rows.includes("shape"), false);
  t.check("it is offered the relation instead", rows.includes("hue ±"), true);
  t.check("and is told where its pattern comes from", !!p.$("#tracks .note"), true);

  p.run(`setLink('${second}',{invert:true, rate_scale:2})`);
  await sleep(80);
  const link = p.lastSent("show").show.tracks[1].link;
  t.check("invert reaches the server", link.invert, true);
  t.check("so does the speed", link.rate_scale, 2);

  // Delete the LEADER. The follower must not be left pointing at a ghost.
  p.run("deleteTrack('t0')");
  await sleep(10);
  t.check("deleting a track removes it", p.run("show.tracks.map(x => x.id)"), [second]);
  t.check("a link to it is cleared, not left dangling",
    p.run("show.tracks[0].link"), null);
  t.check("and its lights go back to the free pile",
    labels("#spare .seg").includes("+ Light 0"), true);

  // ── A blank show, from nothing ──────────────────────────────────────────
  p.run("newShow()");
  await sleep(80);
  t.check("New show clears the tracks", p.run("show.tracks.length"), 0);
  t.check("and every light is free", labels("#spare .seg").length, 3);

  p.close();
}
