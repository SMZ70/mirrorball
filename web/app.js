// mmdj panel.
//
// It edits the Show and sends it. It never talks to a light, never renders a
// frame, never keeps a second copy of the truth. That is what keeps it small
// enough to throw away and rebuild as a native app over the same socket.
//
// Two rules make the sliders work, and both are easy to break:
//
//   1. The PANEL owns the Show. The server echoes it back ten times a second,
//      and taking those echoes would mean a slider snapping back to the value
//      the server had a moment ago. We take the server's show once, and again
//      only when we ask for one (a load).
//
//   2. Rebuilding the DOM under a finger cancels the drag. So the track list is
//      only rebuilt when its CONTENT changes -- never on a timer, and never
//      while a slider is being dragged. A dragging slider writes its own label.

const SHAPES = ["solid", "pulse", "strobe", "breathe", "sweep", "chase", "sparkle"];
const CURVES = ["sine", "ramp", "fall", "square", "ease"];
const MODES  = ["hold", "cycle", "random"];
const RATES  = [
  { label: "4",   v: 4    },
  { label: "2",   v: 2    },
  { label: "1",   v: 1    },
  { label: "1/2", v: 0.5  },
  { label: "1/4", v: 0.25 },
  { label: "1/8", v: 0.125 },
];

// How each slider's value reads. Used for the markup AND for the live update
// during a drag, so the two cannot drift apart.
const FMT = {
  hue_from: (v) => `${Math.round(v)}°`,
  hue_to:   (v) => `${Math.round(v)}°`,
  phase:    (v) => v.toFixed(2),
  duty:     (v) => v.toFixed(2),
  bri_min:  (v) => `${Math.round(v)}`,
  bri_max:  (v) => `${Math.round(v)}`,
  level:    (v) => `${Math.round(v * 100)}%`,
};

let state = null;      // last state from the server
let show = null;       // the Show we are editing -- ours, not the server's
let open = null;       // which track is expanded
let ws = null;
let dragging = false;  // a slider is under a finger right now
let wantShow = false;  // we asked for a show (a load); take the next one
let drawn = "";        // what the track list currently displays
let loaded = null;     // {name, key} of the show as it arrived, before edits

const $ = (id) => document.getElementById(id);

// ── Socket ────────────────────────────────────────────────────────────────

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type !== "state") return;
    state = msg;

    if (!show || wantShow) {
      show = msg.show;              // first sight of it, or we asked for it
      wantShow = false;
      loaded = { name: show.name, key: showKey() };   // the unedited original
      drawn = "";                   // force a rebuild
    } else if (typeof msg.bpm === "number") {
      show.bpm = msg.bpm;           // tap tempo is measured by the server's clock
    }

    render();
  };

  ws.onopen = () => {
    err(null);
    // We own the show. If the server restarted while we were away, its idea of
    // the show is stale -- hand it ours.
    if (show) send({ type: "show", show });
  };

  ws.onclose = () => {
    err("disconnected — retrying");
    setTimeout(connect, 1000);
  };
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// Push the show, but not on every pixel of a drag: the engine picks the change
// up on its next frame anyway, 20ms later.
let pushTimer = null;
function push() {
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => send({ type: "show", show }), 60);
}

function err(msg) {
  const e = $("err");
  if (!msg) { e.classList.remove("show"); return; }
  e.textContent = msg;
  e.classList.add("show");
}

// ── Actions ───────────────────────────────────────────────────────────────

const togglePlay = () => send({ type: "play", on: !state?.playing });

function toggleBlackout() {
  show.blackout = !show.blackout;      // ours to change; the server follows
  send({ type: "blackout", on: show.blackout });
  render();
}

function saveShow() {
  const name = $("name").value.trim() || show.name;
  show.name = name;
  send({ type: "show", show });        // save what is on screen, not what the
  send({ type: "save", name });        // server last heard about
  loaded = { name, key: showKey() };   // this is the new "unedited"
  $("name").value = "";
  render();
}

// Loading is the one time we DO want the server's show: it built it (a preset)
// or read it off disk (a save), so it is the authority, not us.
function loadShow(name) {
  wantShow = true;
  send({ type: "load", name });
}

function loadPreset(name) {
  wantShow = true;
  send({ type: "preset", name });
}

const track = (id) => show.tracks.find((t) => t.id === id);

/** A discrete edit -- a shape, a rate, SOLO. Rebuilds the list. */
function setTrack(id, patch) {
  Object.assign(track(id), patch);
  push();
  render();
}

function setPal(id, patch) {
  Object.assign(track(id).palette, patch);
  push();
  render();
}

/** A slider edit. Deliberately does NOT rebuild the list: the element being
 *  dragged must survive the drag. It updates its own label instead. */
function slide(el, id, field, palette) {
  const value = +el.value;
  const t = track(id);
  (palette ? t.palette : t)[field] = value;

  const label = el.nextElementSibling;
  if (label) label.textContent = FMT[field](value);

  push();
}

function toggleOpen(id) {
  open = open === id ? null : id;
  render();
}

// A drag begins on the slider and can end anywhere, so the release is watched
// on the window. While it lasts, nothing is allowed to redraw the list.
document.addEventListener("pointerdown", (e) => {
  if (e.target.type === "range") dragging = true;
});
window.addEventListener("pointerup", () => {
  if (!dragging) return;
  dragging = false;
  render();                            // one rebuild, now that it is safe
});

// ── Render ────────────────────────────────────────────────────────────────

const hsl = (h, s = 1, l = 0.5) => `hsl(${h} ${s * 100}% ${l * 100}%)`;

const slider = (t, field, attrs, palette) => {
  const value = palette ? t.palette[field] : t[field];
  return `
    <input type="range" ${attrs} value="${value}"
           oninput="slide(this,'${t.id}','${field}',${palette ? "true" : "false"})">
    <span class="val">${FMT[field](value)}</span>`;
};

function trackHtml(t) {
  const p = t.palette;
  const isOpen = open === t.id;
  const swatch = `linear-gradient(135deg, ${hsl(p.hue_from)}, ${hsl(p.hue_to)})`;

  const head = `
    <div class="thead" onclick="toggleOpen('${t.id}')">
      <span class="swatch" style="background:${swatch}"></span>
      <span class="tname">${t.name || t.target.slice(0, 8)}</span>
      <span class="tinfo">${t.shape} · ${rateLabel(t.rate)}</span>
      ${t.solo ? '<span class="chip s">S</span>' : ""}
      ${t.mute ? '<span class="chip m">M</span>' : ""}
    </div>`;

  if (!isOpen) return `<div class="track ${t.mute ? "muted" : ""}">${head}</div>`;

  return `
  <div class="track ${t.mute ? "muted" : ""} open">
    ${head}
    <div class="body">
      <div class="row"><label>shape</label><div class="segs">
        ${SHAPES.map((s) => `<div class="seg ${t.shape === s ? "sel" : ""}"
           onclick="setTrack('${t.id}',{shape:'${s}'})">${s}</div>`).join("")}
      </div></div>

      <div class="row"><label>rate</label><div class="segs">
        ${RATES.map((r) => `<div class="seg ${t.rate === r.v ? "sel" : ""}"
           onclick="setTrack('${t.id}',{rate:${r.v}})">${r.label}</div>`).join("")}
      </div></div>

      <div class="row"><label>curve</label><div class="segs">
        ${CURVES.map((c) => `<div class="seg ${t.curve === c ? "sel" : ""}"
           onclick="setTrack('${t.id}',{curve:'${c}'})">${c}</div>`).join("")}
      </div></div>

      <div class="row"><label>colour</label><div class="segs">
        ${MODES.map((m) => `<div class="seg ${p.mode === m ? "sel" : ""}"
           onclick="setPal('${t.id}',{mode:'${m}'})">${m}</div>`).join("")}
      </div></div>

      <div class="row"><label>hue</label>
        ${slider(t, "hue_from", 'class="hue" min="0" max="360"', true)}
      </div>
      <div class="row"><label>…to</label>
        ${slider(t, "hue_to", 'class="hue" min="0" max="360"', true)}
      </div>
      <div class="row"><label>phase</label>
        ${slider(t, "phase", 'min="0" max="0.99" step="0.01"')}
      </div>
      <div class="row"><label>duty</label>
        ${slider(t, "duty", 'min="0.05" max="1" step="0.05"')}
      </div>
      <div class="row"><label>min</label>
        ${slider(t, "bri_min", 'min="0" max="100"')}
      </div>
      <div class="row"><label>max</label>
        ${slider(t, "bri_max", 'min="0" max="100"')}
      </div>
      <div class="row"><label>level</label>
        ${slider(t, "level", 'min="0" max="1" step="0.01"')}
      </div>

      <div class="row">
        <button class="${t.solo ? "on" : ""}" onclick="setTrack('${t.id}',{solo:${!t.solo}})">SOLO</button>
        <button class="${t.mute ? "stop" : ""}" onclick="setTrack('${t.id}',{mute:${!t.mute}})">MUTE</button>
      </div>
    </div>
  </div>`;
}

const rateLabel = (v) => (RATES.find((r) => r.v === v) || { label: v }).label;

// What the show currently *is*, as a string. Doubles as the "has the user
// touched this since it loaded?" test and as the redraw check.
const showKey = () => JSON.stringify(show.tracks) + `|${Math.round(show.bpm)}`;

const edited = () => !!loaded && showKey() !== loaded.key;

function presetHtml(p) {
  // A preset's colours, before you load it: one stop per voice.
  const stops = p.hues.flatMap(([a, b]) => [hsl(a), hsl(b)]);
  const strip = stops.length > 1
    ? `linear-gradient(90deg, ${stops.join(",")})`
    : stops[0];

  const on = loaded?.name === p.name;
  const cls = ["preset", on ? "on" : "", on && edited() ? "edited" : ""].join(" ");

  return `
    <button class="${cls}" onclick="loadPreset('${p.name}')">
      <span class="strip" style="background:${strip}"></span>
      <span class="prow">
        <span class="pname">${p.name}</span>
        <span class="pbpm">${Math.round(p.bpm)}</span>
      </span>
      <span class="pnote">${on && edited() ? "edited — tap to reset" : p.note}</span>
    </button>`;
}

function render() {
  if (!state || !show) return;

  $("bpm").textContent = Math.round(show.bpm);
  $("area").textContent = state.area ? `· ${state.area}` : "";
  $("play").textContent = state.playing ? "■" : "▶";
  $("play").className = state.playing ? "stop" : "go";
  $("blackout").className = show.blackout ? "on" : "";

  // Flash on the downbeat, so you can see the show is locked to the tempo
  const onBeat = state.playing && (state.beat % 1) < 0.18;
  $("beat").classList.toggle("on", onBeat);

  // The expensive half. Rebuild only if what we would draw has actually changed
  // -- and never mid-drag, which would tear the slider out from under the
  // finger holding it.
  if (dragging) return;
  const key = [showKey(), open, loaded?.name, edited(), (state.shows || []).join()].join("|");
  if (key === drawn) return;
  drawn = key;

  $("presets").innerHTML = (state.presets || []).map(presetHtml).join("");

  $("shows").innerHTML = (state.shows || [])
    .map((n) => `<button class="${loaded?.name === n ? "on" : ""}"
                         onclick="loadShow('${n}')">${n}</button>`).join("")
    || `<span class="hint">nothing saved yet — load a preset, change it, name it, Save</span>`;

  $("tracks").innerHTML = show.tracks.map(trackHtml).join("")
    || `<div class="track"><div class="thead"><span class="tinfo">no tracks</span></div></div>`;
}

connect();
