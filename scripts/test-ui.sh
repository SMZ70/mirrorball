#!/usr/bin/env bash
# The panel's tests. Node, because the panel is JavaScript; jsdom, because the
# bugs worth catching live in the DOM (a slider being destroyed mid-drag).
set -euo pipefail

cd "$(dirname "$0")/../tests/ui"
[ -d node_modules ] || npm install --silent --no-audit --no-fund
exec node run.mjs
