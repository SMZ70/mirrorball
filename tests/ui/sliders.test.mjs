/**
 * A slider must survive being dragged.
 *
 * It did not, for two compounding reasons, and both are easy to reintroduce:
 *
 *   1. render() rebuilt the track list with innerHTML on every redraw -- and
 *      redrew on every broadcast AND every oninput. The element under the
 *      finger was destroyed and replaced, which drops the pointer capture and
 *      ends the drag after one step.
 *
 *   2. The panel took the server's echo of the show. During the 60ms push
 *      debounce that echo is stale, so the value snapped back.
 *
 * Both are asserted here. If either regresses, this fails.
 */

import { boot, sleep, state } from "./harness.mjs";

export default async function (t) {
  const p = await boot();

  p.feed(state());
  await sleep(10);
  p.run("toggleOpen('t0')");

  const slider = p.$$('#tracks input[type=range]')
    .find((i) => i.getAttribute("oninput").includes("phase"));
  t.check("the phase slider is there", !!slider, true);

  slider.dispatchEvent(new p.window.PointerEvent("pointerdown", { bubbles: true }));

  // The finger moves -- while the server keeps insisting phase is still 0.
  for (const v of ["0.20", "0.40", "0.60", "0.80"]) {
    slider.value = v;
    slider.dispatchEvent(new p.window.Event("input", { bubbles: true }));
    await sleep(10);
    p.feed(state());                    // the stale echo, mid-drag
  }

  t.check("the element survives the drag", p.window.document.body.contains(slider), true);
  t.check("its label follows the thumb", slider.nextElementSibling.textContent, "0.80");

  await sleep(120);                     // let the debounced push fire
  for (let i = 0; i < 10; i++) {        // ...and a second of stale echoes after it
    p.feed(state());
    await sleep(20);
  }

  slider.dispatchEvent(new p.window.PointerEvent("pointerup", { bubbles: true }));
  p.window.dispatchEvent(new p.window.PointerEvent("pointerup", { bubbles: true }));
  await sleep(30);

  t.check("the value holds", p.run("show.tracks[0].phase"), 0.8);
  t.check("the server was told", p.lastSent("show").show.tracks[0].phase, 0.8);

  const redrawn = p.$$('#tracks input[type=range]')
    .find((i) => i.getAttribute("oninput").includes("phase"));
  t.check("and the redraw agrees", redrawn.value, "0.8");

  p.close();
}
