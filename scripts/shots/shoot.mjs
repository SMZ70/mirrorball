// Drive the panel in a real browser and capture the README's stills and GIF.
//
//   uv run python scripts/demo_panel.py &     # fake lights, no bridge
//   cd scripts/shots && npm install && node shoot.mjs
//
// Frames go to frames/, stills and the gif to ../../docs/. ffmpeg makes the gif.
// It shoots the demo panel on purpose: no real light names end up in the repo.

import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const URL = process.env.PANEL ?? "http://127.0.0.1:8091/";
const CHROME = process.env.CHROME ?? "/usr/bin/chromium";
const DOCS = path.resolve("../../docs");
const FRAMES = path.resolve("frames");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

rmSync(FRAMES, { recursive: true, force: true });
mkdirSync(FRAMES, { recursive: true });
mkdirSync(DOCS, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--force-color-profile=srgb", "--hide-scrollbars"],
});

const page = await browser.newPage();
// A phone, because that is what it is used on. deviceScaleFactor 2 so the stills
// are not soft on a retina screen; the gif is scaled back down by ffmpeg.
await page.setViewport({ width: 430, height: 900, deviceScaleFactor: 2 });
await page.goto(URL, { waitUntil: "networkidle0" });
await sleep(800);

const click = async (sel, wait = 450) => {
  await page.click(sel);
  await sleep(wait);
};
const clickText = async (selector, text, wait = 450) => {
  const handle = await page.evaluateHandle(
    (sel, t) => [...document.querySelectorAll(sel)].find((e) => e.textContent.trim().toLowerCase().includes(t)),
    selector, text.toLowerCase(),
  );
  const el = handle.asElement();
  if (!el) throw new Error(`no ${selector} matching ${text}`);
  await el.click();
  await sleep(wait);
};

const nudgeUp = async () => {
  const buttons = await page.$$(".tempo .nudge");
  await buttons[buttons.length - 1].click();
};

// The editor sits below the presets, so it has to be scrolled to or the still is
// mostly preset cards.
const showEditor = async () => {
  await page.evaluate(() => document.querySelector("#tracks .track.open")
    ?.scrollIntoView({ block: "center" }));
  await sleep(350);
};

// ── Stills ──────────────────────────────────────────────────────────────────
await clickText("#presets button", "fire");
await page.screenshot({ path: path.join(DOCS, "presets.png") });

await click("#tracks .track .thead");                    // open the first track
await showEditor();
await page.screenshot({ path: path.join(DOCS, "editor.png") });

await click("#helpbtn");                                 // inline help on
await showEditor();
await page.screenshot({ path: path.join(DOCS, "help.png") });
await click("#helpbtn");                                 // back off
await click("#tracks .track .thead");                    // close it again
await page.evaluate(() => window.scrollTo(0, 0));
await sleep(300);

// ── The GIF ─────────────────────────────────────────────────────────────────
// A little story: play, swap preset, open a light, change its shape and colour.
// Frames are captured as fast as the browser allows, which is NOT a fixed rate:
// a screenshot takes as long as it takes. So each frame's real wall-clock moment
// is recorded, and ffmpeg is told the true duration of each one. Handing an
// image sequence to ffmpeg without this makes it assume 25fps, which replays ten
// seconds of interaction in under two and looks like a seizure.
let n = 0;
const stamps = [];
const shoot = async () => {
  await page.screenshot({ path: path.join(FRAMES, `${String(n++).padStart(4, "0")}.png`) });
  stamps.push(Date.now());
};
const beat = async (ms) => {
  const until = Date.now() + ms;
  while (Date.now() < until) { await shoot(); await sleep(60); }
};

await clickText("#presets button", "party", 200);
await beat(700);
await click("#play", 200);            // ▶
await beat(1400);
await clickText("#presets button", "rave", 200);
await beat(1500);
await clickText("#presets button", "call", 200);
await beat(1500);
await click("#tracks .track .thead", 250);   // open a light
await beat(700);

// Nudge the tempo, so the panel is visibly live rather than a slideshow.
for (let i = 0; i < 6; i++) { await nudgeUp(); await shoot(); await sleep(120); }
await beat(900);
await click("#play", 200);            // ■ — hand the lights back
await beat(600);

await browser.close();

// A concat list carrying each frame's true duration, so the gif plays back at the
// speed the interaction actually happened.
const lines = [];
for (let i = 0; i < n; i++) {
  const dur = ((stamps[i + 1] ?? stamps[i] + 200) - stamps[i]) / 1000;
  lines.push(`file '${String(i).padStart(4, "0")}.png'`, `duration ${dur.toFixed(3)}`);
}
lines.push(`file '${String(n - 1).padStart(4, "0")}.png'`);   // ffmpeg drops the last
writeFileSync(path.join(FRAMES, "list.txt"), lines.join("\n"));

// A palette first, or the gif dithers into mud on a dark UI.
const gif = path.join(DOCS, "panel.gif");
const filters = "fps=12,scale=380:-1:flags=lanczos";
const input = ["-f", "concat", "-safe", "0", "-i", path.join(FRAMES, "list.txt")];
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...input,
  "-vf", `${filters},palettegen=stats_mode=diff`, path.join(FRAMES, "pal.png")]);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...input,
  "-i", path.join(FRAMES, "pal.png"),
  "-lavfi", `${filters}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3`,
  "-loop", "0", gif]);

const secs = ((stamps.at(-1) - stamps[0]) / 1000).toFixed(1);
console.log(`${n} frames over ${secs}s -> ${gif}`);
