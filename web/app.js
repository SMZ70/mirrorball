// mirrorball panel.
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

const BPM_MIN = 40, BPM_MAX = 220;      // the server rejects anything outside

// What each control is FOR. Shown in place when help is on -- a phone has no
// hover, so there is nowhere to put a tooltip. Written to answer "why would I
// touch this?", not to restate the label.
const HELP = {
  lights: "Which lights this track drives. Tap to add or remove — a light can "
        + "only be in one track at a time, so adding it here takes it from "
        + "wherever it was. <b>Two or more lights in one track is a group</b>: "
        + "they share a pattern.",
  spread: "How the pattern is dealt across the lights in this group. "
        + "<b>unison</b> and they all do the same thing at the same moment — the "
        + "group becomes one big lamp. Turn it up and each light sits a little "
        + "further round the cycle, so the pattern <i>travels</i> through them.",
  follows: "Make this track echo another one instead of having a pattern of its "
        + "own. It copies that track's <b>shape, curve, rate, duty and colour</b>, "
        + "and keeps its own lights, brightness and phase. Change the leader and "
        + "this changes with it.",
  relation: "How the echo differs from what it follows. <b>speed</b> runs it at "
        + "half or double time · <b>invert</b> makes it bright exactly where the "
        + "leader is dark · <b>hue ±</b> rotates its colour (<b>180°</b> is the "
        + "opposite side of the wheel). Add <b>phase</b> below to answer a beat "
        + "later.",
  shape: "What the light does each cycle. <b>pulse</b> swells and falls · "
       + "<b>strobe</b> snaps on and off · <b>chase</b> hits then decays · "
       + "<b>sparkle</b> fires at random moments · <b>breathe</b> drifts slowly · "
       + "<b>sweep</b> travels through the colours · <b>solid</b> just holds.",
  rate:  "How long one cycle lasts, <b>in beats</b>. <b>1</b> = once a beat. "
       + "<b>1/4</b> = four times a beat (fast). <b>4</b> = once every four beats "
       + "(slow). Beats rather than seconds, so it stays locked to the music when "
       + "you change the tempo.",
  curve: "The shape of the swell. <b>sine</b> is smooth · <b>fall</b> snaps up then "
       + "decays, which reads as a <i>hit</i> · <b>ramp</b> rises then drops · "
       + "<b>square</b> is hard on/off · <b>ease</b> is soft at both ends.",
  mode:  "How the colour moves inside the range below. <b>hold</b> = one colour · "
       + "<b>cycle</b> = walk the range each cycle · <b>random</b> = a new colour "
       + "from the range every cycle.",
  hue:   "The colours this light is allowed to use. Set both ends the same for a "
       + "single fixed colour; set 0 → 360 for the whole spectrum.",
  phase: "Where in the cycle this light starts. Offsetting the lights against each "
       + "other is what makes a chase <i>travel</i> around the room instead of every "
       + "light firing at once.",
  duty:  "How much of the cycle is <b>on</b>. Low = short stabs with dark between. "
       + "High = long holds. This is where a strobe stops being a strobe.",
  bri:   "The brightness range. Raise <b>min</b> above 0 to keep the light alive "
       + "between hits; drop <b>max</b> to make it sit back. A wide gap = high "
       + "contrast, which is what makes a room feel like it is moving.",
  level: "This light's fader — scales everything it does, like a channel on a "
       + "mixer. Pull it down to keep a light in the mix but out of the way.",
  solo:  "<b>SOLO</b> plays only the soloed lights and silences the rest — good for "
       + "hearing what one light is actually doing. <b>MUTE</b> silences this one. "
       + "Solo beats mute.",
};

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
  spread:   (v) => (v < 0.02 ? "unison" : v.toFixed(2)),
  hue_shift: (v) => `${Math.round(v)}°`,
  rate_scale: (v) => `×${v}`,
};

// What a follower can do to its leader's pattern.
const SCALES = [
  { label: "×¼", v: 0.25 },
  { label: "×½", v: 0.5 },
  { label: "×1", v: 1 },
  { label: "×2", v: 2 },
  { label: "×4", v: 4 },
];

let state = null;      // last state from the server
let show = null;       // the Show we are editing -- ours, not the server's

// LIVE drives the room. PLAYGROUND drives nothing at all: the server renders the
// same show with the same engine and sends back frames to draw on screen, but it
// never opens a driver. The two keep SEPARATE shows -- switching modes must not
// smuggle a sandbox experiment into the lights, and coming back must not have
// lost what you were doing.
let mode = "live";
const kept = { live: null, pg: null };
let frames = {};       // the playground stage, as last rendered by the server
let open = null;       // which track is expanded
let ws = null;
let dragging = false;  // a slider is under a finger right now
let wantShow = false;  // we asked for a show (a load); take the next one
let drawn = "";        // what the track list currently displays
let loaded = null;     // {name, key} of the show as it arrived, before edits
let tapping = false;   // we asked the server to measure a tap; take its answer
let helpOn = localStorage.getItem("mirrorball.help") === "1";

const $ = (id) => document.getElementById(id);

// ── Socket ────────────────────────────────────────────────────────────────

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    // The playground stage. Rendered by the engine's own code, so what is drawn
    // here is what the room would actually do.
    if (msg.type === "preview") {
      if (mode === "pg") { frames = msg.frames; paintStage(); }
      return;
    }
    if (msg.type !== "state") return;
    state = msg;

    if (!show || wantShow) {
      show = (mode === "pg" ? msg.pg?.show : msg.show);   // ours, or asked for
      wantShow = false;
      loaded = { name: show.name, key: showKey() };   // the unedited original
      drawn = "";                   // force a rebuild
    } else if (tapping && typeof (mode === "pg" ? msg.pg?.bpm : msg.bpm) === "number") {
      // The ONE case where the server knows the tempo better than we do: it
      // measured the taps. Any other time, taking its bpm would undo the number
      // the user is in the middle of typing -- which is exactly how the sliders
      // used to fight back.
      tapping = false;
      show.bpm = mode === "pg" ? msg.pg.bpm : msg.bpm;
      push();
    }

    render();
  };

  ws.onopen = () => {
    err(null);
    // We own the show. If the server restarted while we were away, its idea of
    // the show is stale -- hand it ours.
    if (show) sendW({ type: "show", show });
  };

  ws.onclose = () => {
    err("disconnected — retrying");
    setTimeout(connect, 1000);
  };
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

/** THE choke point. Every message the editor sends goes through here, so the
 *  playground cannot address the live show by accident -- it is one function,
 *  not a rule everybody has to remember. */
const wire = (type) => (mode === "pg" ? `pg.${type}` : type);
const sendW = (msg) => send({ ...msg, type: wire(msg.type) });

/** Whichever transport we are looking at. */
const isPlaying = () => (mode === "pg" ? !!state?.pg?.running : !!state?.playing);

function setMode(next) {
  if (next === mode) return;
  kept[mode] = show;                 // remember where we were
  mode = next;
  show = kept[mode] || null;
  if (!show) wantShow = true;        // first visit: take the server's copy
  frames = {};
  loaded = show ? loaded : null;
  drawn = "";
  document.body.classList.toggle("pg", mode === "pg");
  render();
}

// Push the show, but not on every pixel of a drag: the engine picks the change
// up on its next frame anyway, 20ms later.
let pushTimer = null;
function push() {
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => sendW({ type: "show", show }), 60);
}

function err(msg) {
  const e = $("err");
  if (!msg) { e.classList.remove("show"); return; }
  e.textContent = msg;
  e.classList.add("show");
}

// ── Actions ───────────────────────────────────────────────────────────────

const togglePlay = () => sendW({ type: "play", on: !isPlaying() });

// ── Tempo ─────────────────────────────────────────────────────────────────

function setBpm(value) {
  const bpm = Math.min(BPM_MAX, Math.max(BPM_MIN, Math.round(value || 0)));
  show.bpm = bpm;
  $("bpm").value = bpm;              // snap the field back if it was out of range
  push();
  render();
}

const nudgeBpm = (by) => setBpm(show.bpm + by);

function tap() {
  tapping = true;                    // the next bpm the server sends is the answer
  sendW({ type: "tap" });
}

function toggleHelp() {
  helpOn = !helpOn;
  localStorage.setItem("mirrorball.help", helpOn ? "1" : "0");
  drawn = "";                        // the help lines live inside the track list
  render();
}

const help = (key) => (helpOn ? `<div class="help">${HELP[key]}</div>` : "");

// The transport, explained. These are the buttons you press in the dark, so the
// distinction that actually matters is BLACK vs ■ -- one hides the show, the
// other gives the lights back.
const GUIDE = `
  <div><span class="k">BPM</span> the tempo everything is locked to. Type it, or
       nudge with − / +.</div>
  <div><span class="k">TAP</span> no idea what the tempo is? Tap four times in
       time with the music and it works it out.</div>
  <div><span class="k">↻</span> the show has drifted off the music — snap it back
       onto the downbeat.</div>
  <div><span class="k">BLACK</span> <b>hides</b> the show: every light to zero,
       but it keeps running underneath, still on the beat. Press again and you
       come back <i>in time</i>, not from the top.</div>
  <div><span class="k">▶ ■</span> ■ <b>stops</b> the show and hands the lights back
       to Hue — so the app, the bot and the party routine can drive them again.</div>
  <div><span class="k">tracks</span> tap a light to open it. Everything you change
       applies <b>live</b>, while it plays.</div>`;

function toggleBlackout() {
  show.blackout = !show.blackout;      // ours to change; the server follows
  sendW({ type: "blackout", on: show.blackout });
  render();
}

function saveShow() {
  const name = $("name").value.trim() || show.name;
  show.name = name;
  sendW({ type: "show", show });       // save what is on screen, not what the
  sendW({ type: "save", name });       // server last heard about
  loaded = { name, key: showKey() };   // this is the new "unedited"
  $("name").value = "";
  render();
}

// Loading is the one time we DO want the server's show: it built it (a preset)
// or read it off disk (a save), so it is the authority, not us.
function loadShow(name) {
  wantShow = true;
  sendW({ type: "load", name });
}

function loadPreset(name) {
  wantShow = true;
  sendW({ type: "preset", name });
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

/** Same, for a link's own sliders. Same rule: no rebuild mid-drag. */
function slideLink(el, id, field) {
  const value = +el.value;
  const t = track(id);
  if (!t.link) return;
  t.link[field] = value;

  const label = el.nextElementSibling;
  if (label) label.textContent = FMT[field](value);

  push();
}

/** Drop every solo. The way out of a solo you did not know you had. */
function clearSolo() {
  for (const t of show.tracks) t.solo = false;
  push();
  render();
}

// ── The playground stage ──────────────────────────────────────────────────

/** Draw the lights as they would look. Bulbs are built once and then only their
 *  colour is touched -- rebuilding 24 nodes 25 times a second would fight the
 *  finger on a slider, which is the bug that has bitten this panel three times. */
function paintStage() {
  const lights = state?.pg?.lights || [];
  const box = $("stage");

  if (box.childElementCount !== lights.length) {
    box.innerHTML = lights.map((l) => `
      <div class="bulb" id="b-${l.id}">
        <div class="glow"></div><span>${l.name}</span>
      </div>`).join("");
  }

  for (const l of lights) {
    const node = document.getElementById(`b-${l.id}`);
    if (!node) continue;
    const f = frames[l.id];
    const glow = node.firstElementChild;
    if (!f || f.bri <= 0.5) {
      glow.style.background = "#14161c";
      glow.style.boxShadow = "none";
      continue;
    }
    const light = 12 + (f.bri / 100) * 42;            // 0-100 bri -> HSL lightness
    const col = `hsl(${f.hue} ${Math.round(f.sat * 100)}% ${light}%)`;
    glow.style.background = col;
    glow.style.boxShadow = `0 0 ${8 + f.bri / 3}px ${col}`;
  }
}

function paintRig() {
  const pg = state?.pg;
  if (!pg) return;
  $("rig-real").className = pg.rig === "real" ? "on" : "";
  $("rig-virtual").className = pg.rig === "virtual" ? "on" : "";
  $("rig-count").style.display = pg.rig === "virtual" ? "" : "none";
  const n = $("rig-n");
  if (document.activeElement !== n) n.value = pg.count;
  $("rig-nval").textContent = `${pg.count} lamps`;
}

/** Switching rigs re-deals the show onto the lights that now exist -- otherwise
 *  the tracks would name lights that are gone and the stage would sit dark. */
function setRig(rig, count) {
  wantShow = true;
  send({ type: "pg.rig", rig, count: count ?? state?.pg?.count ?? 8 });
}

// ── Groups ────────────────────────────────────────────────────────────────

/** Move a light in or out of a track. A light belongs to exactly one track --
 *  two tracks driving the same bulb would just fight, and the last one rendered
 *  would win, which is a coin toss dressed up as a feature. */
function toggleLight(trackId, lightId) {
  const t = track(trackId);
  if (t.targets.includes(lightId)) {
    t.targets = t.targets.filter((x) => x !== lightId);
  } else {
    for (const other of show.tracks) {
      other.targets = other.targets.filter((x) => x !== lightId);
    }
    t.targets = [...t.targets, lightId];
  }
  push();
  render();
}

// ── Links ─────────────────────────────────────────────────────────────────

function setLink(id, patch) {
  const t = track(id);
  t.link = t.link
    ? { ...t.link, ...patch }
    : { follow: "", rate_scale: 1, hue_shift: 0, invert: false, ...patch };
  if (!t.link.follow) t.link = null;          // "none" means none
  push();
  render();
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

// The lights this track drives, by name -- that is what the user thinks of it as.
function trackLabel(t) {
  const named = t.targets
    .map((id) => (state.lights.find((l) => l.id === id) || {}).name)
    .filter(Boolean);
  if (!named.length) return "no lights";
  if (named.length <= 2) return named.join(" + ");
  return `${named.length} lights`;
}

function trackHtml(t) {
  const p = t.palette;
  const isOpen = open === t.id;
  const swatch = `linear-gradient(135deg, ${hsl(p.hue_from)}, ${hsl(p.hue_to)})`;
  const leader = t.link && show.tracks.find((x) => x.id === t.link.follow);

  const head = `
    <div class="thead" onclick="toggleOpen('${t.id}')">
      <span class="swatch" style="background:${swatch}"></span>
      <span class="tname">${trackLabel(t)}</span>
      <span class="tinfo">${leader
        ? `follows ${trackLabel(leader)}`
        : `${t.shape} · ${rateLabel(t.rate)}`}</span>
      ${t.targets.length > 1 ? `<span class="chip g">${t.targets.length}</span>` : ""}
      ${leader ? '<span class="chip l">↳</span>' : ""}
      ${t.solo ? '<span class="chip s">S</span>' : ""}
      ${t.mute ? '<span class="chip m">M</span>' : ""}
    </div>`;

  if (!isOpen) return `<div class="track ${t.mute ? "muted" : ""}">${head}</div>`;

  const others = show.tracks.filter((x) => x.id !== t.id);

  return `
  <div class="track ${t.mute ? "muted" : ""} open">
    ${head}
    <div class="body">

      <div class="row"><label>lights</label><div class="segs">
        ${(state.lights || []).map((l) => `<div
           class="seg ${t.targets.includes(l.id) ? "sel" : ""}"
           onclick="toggleLight('${t.id}','${l.id}')">${l.name}</div>`).join("")}
      </div></div>
      ${help("lights")}

      ${t.targets.length > 1 ? `
      <div class="row"><label>spread</label>
        ${slider(t, "spread", 'min="0" max="1" step="0.05"')}
      </div>
      ${help("spread")}` : ""}

      <div class="row"><label>follows</label><div class="segs">
        <div class="seg ${!t.link ? "sel" : ""}"
             onclick="setLink('${t.id}',{follow:''})">nothing</div>
        ${others.map((o) => `<div class="seg ${t.link?.follow === o.id ? "sel" : ""}"
           onclick="setLink('${t.id}',{follow:'${o.id}'})">${trackLabel(o)}</div>`).join("")}
      </div></div>
      ${help("follows")}

      ${t.link ? `
      <div class="row"><label>speed</label><div class="segs">
        ${SCALES.map((s) => `<div class="seg ${t.link.rate_scale === s.v ? "sel" : ""}"
           onclick="setLink('${t.id}',{rate_scale:${s.v}})">${s.label}</div>`).join("")}
        <div class="seg ${t.link.invert ? "sel" : ""}"
             onclick="setLink('${t.id}',{invert:${!t.link.invert}})">invert</div>
      </div></div>
      <div class="row"><label>hue ±</label>
        <input type="range" min="-180" max="180" step="5" value="${t.link.hue_shift}"
               oninput="slideLink(this,'${t.id}','hue_shift')">
        <span class="val">${FMT.hue_shift(t.link.hue_shift)}</span>
      </div>
      ${help("relation")}
      <div class="note">Pattern comes from <b>${trackLabel(leader || t)}</b>. Shape,
        curve, rate, duty and colour are its own — change them there.</div>
      ` : `
      <div class="row"><label>shape</label><div class="segs">
        ${SHAPES.map((s) => `<div class="seg ${t.shape === s ? "sel" : ""}"
           onclick="setTrack('${t.id}',{shape:'${s}'})">${s}</div>`).join("")}
      </div></div>
      ${help("shape")}

      <div class="row"><label>rate</label><div class="segs">
        ${RATES.map((r) => `<div class="seg ${t.rate === r.v ? "sel" : ""}"
           onclick="setTrack('${t.id}',{rate:${r.v}})">${r.label}</div>`).join("")}
      </div></div>
      ${help("rate")}

      <div class="row"><label>curve</label><div class="segs">
        ${CURVES.map((c) => `<div class="seg ${t.curve === c ? "sel" : ""}"
           onclick="setTrack('${t.id}',{curve:'${c}'})">${c}</div>`).join("")}
      </div></div>
      ${help("curve")}

      <div class="row"><label>colour</label><div class="segs">
        ${MODES.map((m) => `<div class="seg ${p.mode === m ? "sel" : ""}"
           onclick="setPal('${t.id}',{mode:'${m}'})">${m}</div>`).join("")}
      </div></div>
      ${help("mode")}

      <div class="row"><label>hue</label>
        ${slider(t, "hue_from", 'class="hue" min="0" max="360"', true)}
      </div>
      <div class="row"><label>…to</label>
        ${slider(t, "hue_to", 'class="hue" min="0" max="360"', true)}
      </div>
      ${help("hue")}
      `}

      <div class="row"><label>phase</label>
        ${slider(t, "phase", 'min="0" max="0.99" step="0.01"')}
      </div>
      ${help("phase")}

      <div class="row"><label>duty</label>
        ${slider(t, "duty", 'min="0.05" max="1" step="0.05"')}
      </div>
      ${help("duty")}

      <div class="row"><label>min</label>
        ${slider(t, "bri_min", 'min="0" max="100"')}
      </div>
      <div class="row"><label>max</label>
        ${slider(t, "bri_max", 'min="0" max="100"')}
      </div>
      ${help("bri")}

      <div class="row"><label>level</label>
        ${slider(t, "level", 'min="0" max="1" step="0.01"')}
      </div>
      ${help("level")}

      <div class="row">
        <button class="${t.solo ? "on" : ""}" onclick="setTrack('${t.id}',{solo:${!t.solo}})">SOLO</button>
        <button class="${t.mute ? "stop" : ""}" onclick="setTrack('${t.id}',{mute:${!t.mute}})">MUTE</button>
      </div>
      ${help("solo")}
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

  // Never type over the user. If the field has focus they are mid-number, and
  // "14" on the way to "140" would get slapped back to 40 by the clamp.
  const bpmField = $("bpm");
  if (document.activeElement !== bpmField) bpmField.value = Math.round(show.bpm);

  $("area").textContent = mode === "pg"
    ? (state.pg?.rig === "virtual" ? `· virtual rig · ${state.pg.count} lamps` : "· your lights, simulated")
    : (state.area ? `· ${state.area}` : "");

  $("live").className = mode === "live" ? "on" : "";
  $("pg").className = mode === "pg" ? "on" : "";
  $("stage").className = mode === "pg" ? "show" : "";
  $("rig").className = mode === "pg" ? "show" : "";
  // Draw the rig the moment you open the playground, dark and waiting -- not
  // only once frames start arriving. An empty box before you press ▶ looks
  // exactly like a feature that did not work.
  if (mode === "pg") { paintRig(); paintStage(); }
  $("play").textContent = isPlaying() ? "■" : "▶";
  $("play").className = isPlaying() ? "stop" : "go";
  $("blackout").className = show.blackout ? "on" : "";

  // A solo silences everything else, which is correct and also invisible: the
  // S badge lives inside one collapsed track row, so a solo left latched on a
  // track you are not looking at reads as "my other groups stopped working".
  const soloed = show.tracks.filter((t) => t.solo);
  const banner = $("soloing");
  banner.className = soloed.length ? "on" : "";
  banner.textContent = soloed.length
    ? `SOLO — only ${soloed.map(trackLabel).join(", ")} ${soloed.length > 1 ? "are" : "is"} `
      + "playing, every other light is silenced. Tap to clear."
    : "";
  $("helpbtn").className = helpOn ? "ghost on" : "ghost";
  $("guide").className = helpOn ? "show" : "";
  $("guide").innerHTML = helpOn ? GUIDE : "";

  // Flash on the downbeat, so you can see the show is locked to the tempo
  const onBeat = isPlaying() && (state.beat % 1) < 0.18;
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
