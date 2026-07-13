/**
 * The UI suite:  ./scripts/test-ui.sh   (or: node tests/ui/run.mjs)
 *
 * Deliberately not a test framework. A few files, one assertion helper, no
 * config -- the panel is 300 lines of plain JS and does not need a build step
 * to test a build step it does not have.
 */

import groups from "./groups.test.mjs";
import help from "./help.test.mjs";
import playground from "./playground.test.mjs";
import presets from "./presets.test.mjs";
import sliders from "./sliders.test.mjs";
import solo from "./solo.test.mjs";
import tempo from "./tempo.test.mjs";

const SUITES = [
  ["sliders — a drag must survive the redraw and the echo", sliders],
  ["tempo   — the panel owns the bpm, except after TAP", tempo],
  ["presets — the cards must not lie about what is loaded", presets],
  ["groups  — one light, one track; a follower has no pattern", groups],
  ["help    — every setting explains itself", help],
  ["solo    — a control that silences the room cannot be invisible", solo],
  ["playgnd — the sandbox must never reach the lights", playground],
];

const GREEN = "\x1b[32m", RED = "\x1b[31m", DIM = "\x1b[2m", OFF = "\x1b[0m";

let failed = 0;
const started = Date.now();

for (const [title, suite] of SUITES) {
  console.log(`\n${DIM}${title}${OFF}`);

  const t = {
    check(label, got, want) {
      const ok = JSON.stringify(got) === JSON.stringify(want);
      if (ok) {
        console.log(`  ${GREEN}✓${OFF} ${label}`);
      } else {
        failed++;
        console.log(`  ${RED}✗ ${label}${OFF}`);
        console.log(`      got  ${JSON.stringify(got)}`);
        console.log(`      want ${JSON.stringify(want)}`);
      }
    },
  };

  try {
    await suite(t);
  } catch (err) {
    failed++;
    console.log(`  ${RED}✗ threw: ${err.message}${OFF}`);
  }
}

const secs = ((Date.now() - started) / 1000).toFixed(1);
console.log(failed
  ? `\n${RED}${failed} failed${OFF} in ${secs}s\n`
  : `\n${GREEN}all green${OFF} in ${secs}s\n`);

process.exit(failed ? 1 : 0);
