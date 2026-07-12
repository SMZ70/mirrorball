/**
 * A preset card has to be honest.
 *
 * It must say what it is before you tap it -- tapping replaces your show, so
 * "find out by trying" costs you your work. And once loaded, it must stop
 * claiming to be the preset the moment you change anything, or the way back to
 * the original becomes invisible.
 *
 * Also pinned here: Save must carry the edit. It used to just say "save" and
 * let the server write whatever it last heard, which raced the 60ms push.
 */

import { boot, sleep, state } from "./harness.mjs";

export default async function (t) {
  const p = await boot();
  const cards = () => p.$$("#presets .preset");
  const card = (name) =>
    cards().find((c) => c.querySelector(".pname").textContent.trim() === name);

  p.feed(state({ shows: ["saturday"] }));
  await sleep(10);

  t.check("every preset is offered", cards().length, 3);
  t.check("it says what it is", card("rave").querySelector(".pnote").textContent.trim(),
          "hard strobe");
  t.check("and at what tempo", card("sunset").querySelector(".pbpm").textContent.trim(), "60");
  t.check("and what colours it will make",
          card("party").querySelector(".strip").style.background.startsWith("linear-gradient"),
          true);
  t.check("the one we are on is marked", card("party").className.includes("on"), true);
  t.check("the others are not", card("rave").className.includes("on"), false);
  t.check("saved shows are listed", !!p.$("#shows button"), true);

  // Load one: the panel asks, and adopts what comes back.
  p.run("loadPreset('rave')");
  t.check("asks the server for it", p.lastSent("preset"), { type: "preset", name: "rave" });

  p.feed(state({ show: { ...state().show, name: "rave" }, shows: ["saturday"] }));
  await sleep(10);
  t.check("selection follows the load", card("rave").className.includes("on"), true);
  t.check("the old one lets go", card("party").className.includes("on"), false);
  t.check("and it is not yet edited", card("rave").className.includes("edited"), false);

  // Change it: the card must stop pretending to be the pristine preset.
  p.run("setTrack('t0',{shape:'chase'})");
  await sleep(10);
  t.check("an edit is admitted", card("rave").className.includes("edited"), true);
  t.check("and says how to get back",
          card("rave").querySelector(".pnote").textContent.includes("tap to reset"), true);

  // Save: the edit must reach the server BEFORE the save is asked for.
  p.$("#name").value = "my night";
  p.run("saveShow()");
  t.check("the edit is pushed first", p.lastSent("show").show.tracks[0].shape, "chase");
  t.check("then saved under the name", p.lastSent("save"), { type: "save", name: "my night" });
  t.check("and the preset is no longer claimed", card("rave").className.includes("on"), false);

  p.close();
}
