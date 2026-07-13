/**
 * A solo silences every other track. That is correct -- and it was invisible,
 * because the S badge lives inside one collapsed track row. A solo latched on a
 * track you are not looking at reads as "my other groups stopped playing".
 */
import assert from "node:assert/strict";
import { boot, state, show, track, sleep } from "./harness.mjs";

const p = await boot();

// A show recalled with a solo latched on the LAST track -- exactly the shape of
// the saved shows that caused this.
p.feed(state({ show: show({ tracks: [track(0), track(1, { solo: true })] }) }));
await sleep(30);

const banner = p.$("#soloing");
assert.ok(banner.className.includes("on"), "the banner must show when a track is soloed");
assert.match(banner.textContent, /SOLO/, "it must say what is happening");
assert.match(banner.textContent, /silenced/, "and that the other lights are silenced");

// One tap gets you out.
p.run("clearSolo()");
await sleep(100);

assert.equal(p.$("#soloing").className, "", "the banner clears");
const sent = p.lastSent("show").show;
assert.deepEqual(sent.tracks.map((t) => t.solo), [false, false], "and the solo is pushed off");

// No solo, no banner.
p.feed(state({ show: show({ tracks: [track(0), track(1)] }) }));
await sleep(30);
assert.equal(p.$("#soloing").className, "", "no banner when nothing is soloed");

console.log("solo banner: 6 checks passed");
p.close();
