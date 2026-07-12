// mmdj panel.
//
// It edits the Show and sends it. It never talks to a light, never renders a
// frame, never keeps a second copy of the truth. That is what keeps it small
// enough to throw away and rebuild as a native app over the same socket.

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

let state = null;      // last state from the server
let show = null;       // the Show we are editing
let open = null;       // which track is expanded
let ws = null;
let dirty = false;     // we have local edits the server has not seen yet

const $ = (id) => document.getElementById(id);

// ── Socket ────────────────────────────────────────────────────────────────

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type !== "state") return;
    state = msg;

    // Do not clobber what the user is dragging right now. The server echoes the
    // show back, and without this the slider would fight the thumb.
    if (!dirty) show = msg.show;

    render();
  };

  ws.onclose = () => {
    err("disconnected — retrying");
    setTimeout(connect, 1000);
  };
  ws.onopen = () => err(null);
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// Push the show, but not on every pixel of a drag: at 50fps the engine will
// pick up the change on its next frame anyway.
let pushTimer = null;
function pushShow() {
  dirty = true;
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => {
    send({ type: "show", show });
    dirty = false;
  }, 60);
  render();
}

function err(msg) {
  const e = $("err");
  if (!msg) { e.classList.remove("show"); return; }
  e.textContent = msg;
  e.classList.add("show");
}

// ── Actions ───────────────────────────────────────────────────────────────

const togglePlay = () => send({ type: "play", on: !state?.playing });
const toggleBlackout = () => send({ type: "blackout", on: !show?.blackout });

function saveShow() {
  const name = $("name").value.trim() || show.name;
  send({ type: "save", name });
}

function loadShow(name) { send({ type: "load", name }); }

function setTrack(id, patch) {
  const t = show.tracks.find((x) => x.id === id);
  Object.assign(t, patch);
  pushShow();
}

function toggleOpen(id) {
  open = open === id ? null : id;
  render();
}

// ── Render ────────────────────────────────────────────────────────────────

const hsl = (h, s = 1, l = 0.5) => `hsl(${h} ${s * 100}% ${l * 100}%)`;

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
        ${MODES.map((m) => `<div class="seg ${t.palette.mode === m ? "sel" : ""}"
           onclick="setPal('${t.id}',{mode:'${m}'})">${m}</div>`).join("")}
      </div></div>

      <div class="row"><label>hue</label>
        <input class="hue" type="range" min="0" max="360" value="${p.hue_from}"
               oninput="setPal('${t.id}',{hue_from:+this.value})">
        <span class="val">${Math.round(p.hue_from)}°</span>
      </div>
      <div class="row"><label>…to</label>
        <input class="hue" type="range" min="0" max="360" value="${p.hue_to}"
               oninput="setPal('${t.id}',{hue_to:+this.value})">
        <span class="val">${Math.round(p.hue_to)}°</span>
      </div>

      <div class="row"><label>phase</label>
        <input type="range" min="0" max="0.99" step="0.01" value="${t.phase}"
               oninput="setTrack('${t.id}',{phase:+this.value})">
        <span class="val">${t.phase.toFixed(2)}</span>
      </div>
      <div class="row"><label>duty</label>
        <input type="range" min="0.05" max="1" step="0.05" value="${t.duty}"
               oninput="setTrack('${t.id}',{duty:+this.value})">
        <span class="val">${t.duty.toFixed(2)}</span>
      </div>
      <div class="row"><label>min</label>
        <input type="range" min="0" max="100" value="${t.bri_min}"
               oninput="setTrack('${t.id}',{bri_min:+this.value})">
        <span class="val">${Math.round(t.bri_min)}</span>
      </div>
      <div class="row"><label>max</label>
        <input type="range" min="0" max="100" value="${t.bri_max}"
               oninput="setTrack('${t.id}',{bri_max:+this.value})">
        <span class="val">${Math.round(t.bri_max)}</span>
      </div>
      <div class="row"><label>level</label>
        <input type="range" min="0" max="1" step="0.01" value="${t.level}"
               oninput="setTrack('${t.id}',{level:+this.value})">
        <span class="val">${Math.round(t.level * 100)}%</span>
      </div>

      <div class="row">
        <button class="${t.solo ? "on" : ""}" onclick="setTrack('${t.id}',{solo:${!t.solo}})">SOLO</button>
        <button class="${t.mute ? "stop" : ""}" onclick="setTrack('${t.id}',{mute:${!t.mute}})">MUTE</button>
      </div>
    </div>
  </div>`;
}

function setPal(id, patch) {
  const t = show.tracks.find((x) => x.id === id);
  Object.assign(t.palette, patch);
  pushShow();
}

const rateLabel = (v) => (RATES.find((r) => r.v === v) || { label: v }).label;

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

  $("tracks").innerHTML = show.tracks.map(trackHtml).join("")
    || `<div class="track"><div class="thead"><span class="tinfo">no tracks</span></div></div>`;

  $("shows").innerHTML = (state.shows || [])
    .map((n) => `<button onclick="loadShow('${n}')">${n}</button>`).join("");
}

connect();
