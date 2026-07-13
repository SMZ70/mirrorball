// Capture the playground for the README: a still, and a gif of the stage running.
//
//   uv run python scripts/demo_panel.py &        # fake lights, no bridge
//   cd scripts/shots && npm install && node playground.mjs
//
// Shot against the demo panel on purpose. Nothing here touches a real bridge --
// which is also the point of the feature being photographed.

import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const URL = process.env.PANEL ?? "http://127.0.0.1:8091/";
const CHROME = process.env.CHROME ?? "/usr/bin/chromium";
const DOCS = path.resolve("../../docs");
const FRAMES = path.resolve("pgframes");

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
await page.setViewport({ width: 430, height: 900, deviceScaleFactor: 2 });
await page.goto(URL, { waitUntil: "networkidle0" });
await sleep(800);

const clickText = async (selector, text, wait = 450) => {
  const handle = await page.evaluateHandle(
    (sel, t) => [...document.querySelectorAll(sel)]
      .find((e) => e.textContent.trim().toLowerCase().includes(t)),
    selector, text.toLowerCase(),
  );
  const el = handle.asElement();
  if (!el) throw new Error(`no ${selector} matching ${text}`);
  await el.click();
  await sleep(wait);
};

// ── Into the playground ─────────────────────────────────────────────────────
await page.click("#pg");
await sleep(500);
await clickText("#presets button", "wave", 400);
await page.click("#play");                 // previews; drives nothing
await sleep(900);

await page.screenshot({ path: path.join(DOCS, "playground.png") });

// ── The gif ─────────────────────────────────────────────────────────────────
// Same trick as shoot.mjs: screenshots do NOT happen at a fixed rate, so record
// each frame's true moment and hand ffmpeg the real durations. Otherwise it
// assumes 25fps and replays the whole thing at four times speed.
let n = 0;
const stamps = [];
const shoot = async () => {
  await page.screenshot({
    path: path.join(FRAMES, `${String(n++).padStart(4, "0")}.png`),
    clip: { x: 0, y: 0, width: 430, height: 560 },   // the stage and the transport
  });
  stamps.push(Date.now());
};
const beat = async (ms) => {
  const until = Date.now() + ms;
  while (Date.now() < until) { await shoot(); await sleep(55); }
};

await beat(1600);                                    // the wave, on your own lights
await clickText("#presets button", "rave", 150);     // one lamp, in unison
await beat(1600);
await page.click("#rig-virtual");                    // a rig you do not own
await sleep(500);
await clickText("#presets button", "party", 150);
await beat(1700);

// Grow the virtual rig, live, while it plays.
for (const size of [12, 16, 20, 24]) {
  await page.evaluate((v) => window.setRig("virtual", v), size);
  await sleep(120);
  await beat(420);
}
await beat(1200);

await browser.close();

const lines = [];
for (let i = 0; i < n; i++) {
  const dur = ((stamps[i + 1] ?? stamps[i] + 200) - stamps[i]) / 1000;
  lines.push(`file '${String(i).padStart(4, "0")}.png'`, `duration ${dur.toFixed(3)}`);
}
lines.push(`file '${String(n - 1).padStart(4, "0")}.png'`);
writeFileSync(path.join(FRAMES, "list.txt"), lines.join("\n"));

const gif = path.join(DOCS, "playground.gif");
const filters = "fps=14,scale=380:-1:flags=lanczos";
const input = ["-f", "concat", "-safe", "0", "-i", path.join(FRAMES, "list.txt")];
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...input,
  "-vf", `${filters},palettegen=stats_mode=diff`, path.join(FRAMES, "pal.png")]);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...input,
  "-i", path.join(FRAMES, "pal.png"),
  "-lavfi", `${filters}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3`,
  "-loop", "0", gif]);

const secs = ((stamps.at(-1) - stamps[0]) / 1000).toFixed(1);
console.log(`${n} frames over ${secs}s -> ${gif}`);
