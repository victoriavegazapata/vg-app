// Virtual Gages page. Reads data/latest.json (written every hour by run_update.py).
// Nowcast and Forecast are drawn in separate sections and separate charts, never in one line.

const C = {
  grape: "#6D1F42", blueberry: "#52A5CE", olive: "#AFAB23", lilacs: "#D3B6D3",
  bubblegum: "#FF7BAC", orange: "#EF6F3C", ink: "#2b2230", muted: "#6b6068", nws: "#8a7f86",
};
let DATA = null, MAP = null, MARKERS = {};

// ---------- small helpers
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (x, d = 0) => (x === null || x === undefined ? "—" : Number(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const when = (t) => (t ? t.replace("T", " ") + " " + DATA.local_time : "—");
// A range "lo–hi"; one value when both round to the same number (e.g. "9", not "9–9")
const rng = (lo, hi, d = 0) => { const a = fmt(lo, d), b = fmt(hi, d); return a === b ? a : `${a}–${b}`; };
// Find a point from the link: exact id (#rio-nigua-confluence) or one word of it (#nigua, #arecibo)
const findPoint = (h) => DATA.points.find((p) => p.id === h) || DATA.points.find((p) => p.id.split("-").includes(h));
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };

// ---------- load: draw the map first, then add the points when the data file arrives
buildMap();
fetch("data/latest.json", { cache: "no-store" })
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((d) => { DATA = d; start(); })
  .catch(() => { $("#panel").innerHTML = '<p class="empty">The data file could not be loaded yet. Try again in a few minutes.</p>'; });

function start() {
  $("#status-text").textContent = DATA.status_label.replace(/^Research prototype,?\s*/i, "");
  $("#method-version").textContent = DATA.method_version;
  $("#updated").textContent = ` Last update: ${when(DATA.generated)}.`;
  // Warn if the hourly update has not run for more than 3 hours (times in the file are AST = UTC−4)
  const ageH = (Date.now() - new Date(DATA.generated + ":00-04:00").getTime()) / 3600e3;
  if (ageH > 3) {
    $("#updated").insertAdjacentHTML("afterend", `<span class="stale"> The data is ${Math.floor(ageH)} hours old: the hourly update has not run since then.</span>`);
  }
  addPoints();
  buildSearch();
  buildFooter();
  const route = () => { const p = findPoint(decodeURIComponent(location.hash.slice(1)).toLowerCase()); if (p) show(p.id); else overview(); };
  route();
  window.addEventListener("hashchange", route);
}

// ---------- overview of all points (shown until a point is picked)
function overview() {
  for (const m of Object.values(MARKERS)) m.setStyle({ radius: 9 });
  MAP.flyTo([18.22, -66.4], 9, { duration: 0.6 });  // back to the whole island
  const rows = DATA.points.map((p) => {
    const n = p.nowcast.now, k = p.forecast.peak, test = p.kind === "test";
    const flow = test ? `${fmt(n.vg_q)} cfs` : `${rng(n.vg_low, n.vg_high)} cfs`;
    const level = test
      ? (n.vg_h_hand === null && n.vg_q !== null ? "below HAND table" : `${fmt(n.vg_h_hand, 2)} ft`)
      : (n.below_table ? `&lt; ${fmt(p.hand_min_depth_m, 2)} m` : `${rng(n.depth_low, n.depth_high, 2)} m`);
    const obs = test ? `${fmt(n.usgs_q)} cfs` : "no gage";
    const peak = test ? `${fmt(k.vg_q)} cfs` : `${rng(k.vg_low, k.vg_high)} cfs`;
    const flag = k.dry_day ? ` <span class="flagmark" title="${esc(DATA.forecast_info.dry_day_note)}">⚑ dry-day rule</span>` : "";
    return `<tr data-id="${p.id}" tabindex="0">
      <td><strong>${esc(p.name)}</strong><br><small>${test ? "Test point" : "No gage (range)"}</small></td>
      <td class="num">${flow}<br><small>${when(n.vg_time).replace(/^\d{4}-/, "")}</small></td>
      <td class="num">${level}</td>
      <td class="num">${obs}</td>
      <td class="num fc">${peak}${flag}<br><small>${when(k.time).replace(/^\d{4}-/, "")}</small></td>
    </tr>`;
  }).join("");
  $("#panel").innerHTML = `
    <section class="section overview">
      <h3>All points</h3>
      <p class="note">Click a row or a point on the map for its charts. ${esc(DATA.low_flow_note)}</p>
      <table class="ov">
        <thead>
          <tr><th rowspan="2">Point</th><th colspan="3" class="grp nc">Nowcast (virtual gage, now)</th><th class="grp fc">Forecast <span class="tag exp">EXPERIMENTAL</span></th></tr>
          <tr><th>Flow</th><th>Water level / depth</th><th>USGS observed</th><th class="fc">Expected peak</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="note"><strong>⚑ dry-day rule:</strong> ${esc(DATA.forecast_info.dry_day_note)} Forecast: NWM cycle ${esc(DATA.forecast_info.nwm_cycle_utc)}.
        Water level at test points is in ft on the USGS gage datum; at points without a gage, depth above the DEM channel in m.</p>
    </section>`;
  document.querySelectorAll(".ov tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => { location.hash = tr.dataset.id; });
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") location.hash = tr.dataset.id; });
  });
}

// ---------- map
function buildMap() {
  MAP = L.map("map", { scrollWheelZoom: false }).setView([18.22, -66.4], 9);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 14, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(MAP);
}

function addPoints() {
  for (const p of DATA.points) {
    const test = p.kind === "test";
    const m = L.circleMarker(p.lat_lon, {
      radius: 9, weight: test ? 2 : 4, color: test ? C.blueberry : C.bubblegum,
      fillColor: test ? C.blueberry : "#fff", fillOpacity: 1,
    }).addTo(MAP);
    m.bindTooltip(p.name, { direction: "top", offset: [0, -8] });
    m.on("click", () => { location.hash = p.id; });
    MARKERS[p.id] = m;
  }
}

// ---------- search
function buildSearch() {
  const box = $("#search"), list = $("#results");
  const render = () => {
    const q = box.value.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const hits = DATA.points.filter((p) => {
      const text = (p.name + " " + p.description).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
      return !q || text.includes(q);
    });
    list.innerHTML = hits.length
      ? hits.map((p) => `<li data-id="${p.id}">${esc(p.name)}<small>${esc(p.kind === "test" ? "Test point" : "Point without a gage")} · ${esc(p.description)}</small></li>`).join("")
      : "<li>No point matches. Try a river name or a USGS gage number.</li>";
    list.querySelectorAll("li[data-id]").forEach((li) => li.addEventListener("click", () => { location.hash = li.dataset.id; }));
  };
  // The list shows only while typing, so the map stays right under the search box
  const toggle = () => { list.hidden = box.value.trim() === ""; };
  box.addEventListener("input", () => { render(); toggle(); });
  box.addEventListener("keydown", (e) => { if (e.key === "Enter") { const li = list.querySelector("li[data-id]"); if (li) { location.hash = li.dataset.id; box.value = ""; toggle(); } } });
  list.addEventListener("click", () => { box.value = ""; toggle(); });
  render();
  toggle();
}

// ---------- point panel
function show(id) {
  const p = findPoint(id);
  if (!p) return;
  id = p.id;
  document.querySelectorAll("#results li").forEach((li) => li.classList.toggle("active", li.dataset.id === id));
  MAP.flyTo(p.lat_lon, 11, { duration: 0.6 });
  for (const [k, m] of Object.entries(MARKERS)) m.setStyle({ radius: k === id ? 12 : 9 });
  const test = p.kind === "test";
  $("#panel").innerHTML = `
    <div class="point-head">
      <p><a href="#" class="back">← All points</a></p>
      <h2>${esc(p.name)}</h2>
      <p>${esc(p.description)}</p>
      <p>Method: ${esc(p.method)}</p>
    </div>
    <section class="section nowcast">
      <h3>Nowcast <span class="tag tested">tested on past floods</span></h3>
      <p class="note">Last 48 h up to now. ${test ? "" : "No gage here: the virtual gage is shown as a range."} ${esc(DATA.low_flow_note)}</p>
      ${lowNote(lowMask(test ? p.nowcast.vg_q : p.nowcast.vg_high))}
      <div id="nc-flow" class="chart"></div>
      <div id="nc-stage" class="chart"></div>
      <div class="tables">${nowTable(p)}${updateTable(p)}</div>
      ${test && DATA.nws_stages.show ? `<p class="note">Water level in ft on the USGS gage datum. NWS stages for ${esc(p.nws.lid)}: ${nwsText(p)}. Source: ${esc(DATA.nws_stages.source)}.</p>` : ""}
    </section>
    <section class="section forecast">
      <h3>Forecast <span class="tag exp">EXPERIMENTAL</span></h3>
      <div class="warn"><strong>Experimental, not tested.</strong> Kept apart from the nowcast. Upstream flow is held at its last measured value;
        rain after the last MRMS hour is the NWM short-range forecast rain. ${esc(DATA.forecast_info.known_weakness)}</div>
      ${p.forecast.peak.dry_day ? `<div class="flag"><strong>Peak flag:</strong> ${esc(DATA.forecast_info.dry_day_note)}</div>` : ""}
      ${p.forecast.dry_day.some(Boolean) ? `<p class="note marker-note"><span class="ring"></span> Open circles = hours using the dry-day rule: ${esc(DATA.forecast_info.dry_day_marker_note)}</p>` : ""}
      ${lowNote(lowMask(test ? p.forecast.vg_q : p.forecast.vg_high))}
      <div id="fc-flow" class="chart"></div>
      <div id="fc-stage" class="chart"></div>
      <div class="tables">${peakTable(p)}${cycleTable(p)}</div>
    </section>`;
  drawNowcast(p);
  drawForecast(p);
}

function nwsText(p) {
  return Object.entries(p.nws.stages_ft).map(([k, v]) => `${k} ${v} ft`).join(", ");
}

// ---------- tables
function nowTable(p) {
  const n = p.nowcast.now;
  if (p.kind === "test") {
    return `<table><caption>Value now</caption>
      <tr><th>Source</th><th>Flow</th><th>Water level</th><th>Hour</th></tr>
      <tr><td>Virtual gage</td><td class="num">${fmt(n.vg_q)} cfs</td><td class="num">${n.vg_h_hand === null && n.vg_q !== null ? "below HAND table" : fmt(n.vg_h_hand, 2) + " ft"} (HAND)<br>${fmt(n.vg_h_usgs, 2)} ft (USGS rating)</td><td>${when(n.vg_time)}</td></tr>
      <tr><td>USGS observed</td><td class="num">${fmt(n.usgs_q)} cfs</td><td class="num">${fmt(n.usgs_h, 2)} ft</td><td>${when(n.usgs_time)}</td></tr>
      <tr><td>NWM Open Loop</td><td class="num">${fmt(n.nwm_ol_q)} cfs</td><td>—</td><td>${when(n.nwm_ol_time)}</td></tr>
    </table>`;
  }
  const d0 = fmt(p.hand_min_depth_m, 2);
  const depth = n.below_table ? (n.depth_high === null ? `&lt; ${d0} m` : `&lt; ${d0} to ${fmt(n.depth_high, 2)} m`) : `${rng(n.depth_low, n.depth_high, 2)} m`;
  return `<table><caption>Value now</caption>
    <tr><th>Source</th><th>Flow</th><th>Depth above DEM channel</th><th>Hour</th></tr>
    <tr><td>Virtual gage range</td><td class="num">${rng(n.vg_low, n.vg_high)} cfs<br><small>typical error ${rng(n.band_low, n.band_high)}</small></td><td class="num">${depth}</td><td>${when(n.vg_time)}</td></tr>
    <tr><td>NWM Open Loop</td><td class="num">${fmt(n.nwm_ol_q)} cfs</td><td>—</td><td>${when(n.nwm_ol_time)}</td></tr>
  </table>`;
}

function updateTable(p) {
  const rows = Object.entries(p.last_update).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${when(v)}</td></tr>`).join("");
  return `<table><caption>Last data received</caption><tr><th>Source</th><th>Time</th></tr>${rows}</table>`;
}

function peakTable(p) {
  const k = p.forecast.peak, s = p.forecast.nwm_sr_peak;
  const flag = k.dry_day ? " <strong>(dry-day rule, see flag)</strong>" : "";
  const vg = p.kind === "test"
    ? `<tr><td>Virtual gage forecast</td><td class="num">${fmt(k.vg_q)} cfs${flag}<br>${k.vg_h_hand === null ? "below HAND table" : fmt(k.vg_h_hand, 2) + " ft (HAND)"}, ${fmt(k.vg_h_usgs, 2)} ft (USGS rating)</td><td>${when(k.time)}<br><small>${esc(k.hour_type)}</small></td></tr>`
    : `<tr><td>Virtual gage forecast range</td><td class="num">${rng(k.vg_low, k.vg_high)} cfs${flag}<br><small>typical error ${rng(k.band_low, k.band_high)}</small></td><td>${when(k.time)}<br><small>${esc(k.hour_type)}</small></td></tr>`;
  return `<table><caption>Expected peak</caption><tr><th>Source</th><th>Peak</th><th>Time</th></tr>${vg}
    <tr><td>NWM short-range</td><td class="num">${fmt(s.q)} cfs</td><td>${when(s.time)}</td></tr></table>`;
}

function cycleTable(p) {
  const f = DATA.forecast_info, n = p.forecast.hour_type.filter((h) => h === "upstream measured").length;
  return `<table><caption>Forecast made with</caption>
    <tr><td>NWM short-range cycle</td><td>${esc(f.nwm_cycle_utc)} (${when(f.nwm_cycle)}), NWM ${esc(f.nwm_version)}, rain = NBM</td></tr>
    <tr><td>Hours with upstream flow already measured</td><td>${n}</td></tr>
    <tr><td>Forecast ends</td><td>${when(p.forecast.t[p.forecast.t.length - 1])}</td></tr></table>`;
}

// ---------- charts
const LAYOUT = (ytitle) => ({
  margin: { l: 58, r: 12, t: 36, b: 52 }, height: 330, hovermode: "x unified",
  font: { family: "system-ui, sans-serif", size: 12, color: C.ink },
  xaxis: { type: "date", title: { text: `Time (${DATA.local_time}, UTC−4)` }, gridcolor: "#eee", nticks: 6, tickangle: 0 },
  yaxis: { title: { text: ytitle }, gridcolor: "#eee", rangemode: "tozero", separatethousands: true },
  legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { size: 11 } },  // legend above the chart
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
});
const CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
function line(x, y, name, color, extra = {}) {
  const { line: style = {}, ...rest } = extra;
  return { x, y, name, type: "scatter", mode: "lines", connectgaps: false, ...rest, line: { color, width: 2, ...style } };
}
// ---------- low-flow display rule (config: low_flow_display). Drawing only; the numbers are unchanged.
// Hours whose virtual-gage flow is below the tested flood threshold
const lowMask = (q) => q.map((v) => v !== null && v < DATA.low_flow_display.threshold_cfs);
// Split one series into the part at/above the threshold and the part below; the two parts touch at each crossing
function splitLow(y, low) {
  const hi = y.map((v, i) => (low[i] ? null : v)), lo = y.map((v, i) => (low[i] ? v : null));
  for (let i = 0; i < y.length; i++) {
    if (low[i] && i > 0 && !low[i - 1]) lo[i - 1] = y[i - 1];
    if (low[i] && i + 1 < y.length && !low[i + 1]) lo[i + 1] = y[i + 1];
  }
  return { hi, lo };
}
// A virtual-gage line: solid where flow ≥ threshold, faded and dashed where below
function vgLine(x, y, low, name, color, extra = {}) {
  const { hi, lo } = splitLow(y, low), { line: style = {} } = extra;
  const out = [line(x, hi, name, color, extra)];
  if (low.some(Boolean)) {
    // left out of the legend: the low-flow note above the chart explains the faded dashed lines
    out.push(line(x, lo, `${name} (low flow, outside tested range)`, color, { opacity: 0.45, showlegend: false, line: { ...style, dash: style.dash === "dot" ? "dot" : "dash" } }));
  }
  return out;
}
// A virtual-gage band: normal fill where flow ≥ threshold, faded fill with a dashed edge where below.
// Each stretch is drawn as its own piece (a band with gaps would fill across them).
function vgBand(x, lo, hi, low, name, color, alpha) {
  const out = [];
  let i = 0, shown = { hi: false, lo: false };
  while (i < x.length) {
    let j = i;
    while (j + 1 < x.length && low[j + 1] === low[i]) j++;
    const k = Math.min(j + 1, x.length - 1);  // include the next hour so neighbouring pieces touch
    const sl = (a) => a.slice(i, k + 1), isLow = low[i];
    const piece = band(sl(x), sl(lo), sl(hi), isLow ? `${name} (low flow, outside tested range)` : name, color, isLow ? alpha * 0.4 : alpha);
    const top = piece[1];
    top.legendgroup = name;
    top.showlegend = !isLow && !shown.hi;  // one legend entry; the low-flow note explains the faded parts
    if (isLow) top.line = { width: 1, dash: "dash", color: rgba(color, 0.8) };
    shown[isLow ? "lo" : "hi"] = true;
    out.push(...piece);
    i = j + 1;
  }
  if (!shown.hi && out.length) out[1].showlegend = true, out[1].name = name;  // all low: still one legend entry
  return out;
}
// Depth band low edge: where the low end is below the HAND table (no value), shade down to 0 m (true depth is < table minimum)
const depthLow = (lo, hi) => lo.map((v, i) => (v === null && hi[i] !== null ? 0 : v));

function lowNote(low) {
  return low.some(Boolean) ? `<p class="note lowflow"><span class="dashline"></span> Faded dashed parts: ${esc(DATA.low_flow_display.note)}</p>` : "";
}

function band(x, lo, hi, name, color, alpha) {
  return [
    { x, y: lo, type: "scatter", mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip", connectgaps: false },
    { x, y: hi, type: "scatter", mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: rgba(color, alpha), name, connectgaps: false,
      hovertemplate: "%{y:,.0f}" },
  ];
}
function nwsLines(p, layout, values) {
  if (p.kind !== "test" || !DATA.nws_stages.show) return;
  const top = Math.max(...values.filter((v) => v !== null), 0);
  const st = p.nws.stages_ft;
  layout.shapes = []; layout.annotations = [];
  for (const [k, v] of Object.entries(st)) {
    layout.shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: v, y1: v, line: { color: C.nws, width: 1, dash: "dot" } });
    layout.annotations.push({ xref: "paper", x: 0.005, y: v, xanchor: "left", yanchor: "bottom", showarrow: false, text: `${DATA.nws_stages.labels[k]} ${v} ft`, font: { size: 10, color: C.muted } });
  }
  // show the data plus the action stage; higher stages stay listed in the note below the chart
  layout.yaxis.range = [0, Math.max(top, st.action) * 1.15];
  layout.yaxis.rangemode = undefined;
}

function drawNowcast(p) {
  const n = p.nowcast, t = n.t;
  let flow, stage, ly = LAYOUT("Flow (cfs)"), ls;
  if (p.kind === "test") {
    const low = lowMask(n.vg_q);
    flow = [line(t, n.usgs_q, "USGS observed", C.ink, { line: { width: 1.5 } }), ...vgLine(t, n.vg_q, low, "Virtual gage", C.bubblegum, { line: { width: 2.5 } }), line(t, n.nwm_ol_q, "NWM Open Loop", C.blueberry)];
    ls = LAYOUT("Water level (ft)");
    stage = [line(t, n.usgs_h, "USGS observed", C.ink, { line: { width: 1.5 } }), ...vgLine(t, n.vg_h_hand, low, "Virtual gage, HAND rating", C.grape, { line: { width: 3.5 } }),
             ...vgLine(t, n.vg_h_usgs, low, "Virtual gage, current USGS rating", C.grape, { line: { dash: "dot" } })];
    nwsLines(p, ls, [...n.usgs_h, ...n.vg_h_hand, ...n.vg_h_usgs]);
  } else {
    const low = lowMask(n.vg_high);
    flow = [...band(t, n.band_low, n.band_high, "Typical error (±30.1 %)", C.bubblegum, 0.18), ...vgBand(t, n.vg_low, n.vg_high, low, "Virtual gage range", C.bubblegum, 0.55),
            line(t, n.nwm_ol_q, "NWM Open Loop", C.blueberry)];
    ls = LAYOUT("Depth above DEM channel (m)");
    stage = vgBand(t, depthLow(n.depth_low, n.depth_high), n.depth_high, low, "Virtual gage depth range (all Manning n)", C.grape, 0.45);
    if (n.below_table.some(Boolean)) {
      ls.annotations = [{ xref: "paper", yref: "paper", x: 0.01, y: 0.95, xanchor: "left", showarrow: false,
        text: `Band down to 0 = low end below the HAND table (depth &lt; ${fmt(p.hand_min_depth_m, 2)} m); blank = whole range below it`, font: { size: 11, color: C.muted } }];
    }
  }
  Plotly.newPlot("nc-flow", flow, ly, CONFIG);
  Plotly.newPlot("nc-stage", stage, ls, CONFIG);
}

function drawForecast(p) {
  const f = p.forecast, t = f.t;
  // light shade over the hours whose upstream flow is already measured (0 to lag)
  const known = t.filter((_, i) => f.hour_type[i] === "upstream measured");
  const shade = known.length ? [{ type: "rect", xref: "x", yref: "paper", x0: shiftH(known[0], -0.5), x1: shiftH(known[known.length - 1], 0.5), y0: 0, y1: 1,
    fillcolor: rgba(C.lilacs, 0.45), line: { width: 0 }, layer: "below" }] : [];
  const dryX = t.filter((_, i) => f.dry_day[i]);
  let flow, stage, ly = LAYOUT("Flow (cfs)"), ls;
  if (p.kind === "test") {
    const dryY = f.vg_q.filter((_, i) => f.dry_day[i]);
    const low = lowMask(f.vg_q);
    flow = [...vgLine(t, f.vg_q, low, "Virtual gage forecast", C.orange, { line: { width: 2.5 } }), line(t, f.nwm_sr_q, "NWM short-range forecast", C.blueberry, { line: { dash: "dash" } })];
    if (dryX.length) flow.push({ x: dryX, y: dryY, type: "scatter", mode: "markers", name: "Hour using dry-day rule (R = 1)", marker: { color: "#fff", size: 7, line: { color: C.orange, width: 2 } }, hoverinfo: "skip" });
    ls = LAYOUT("Water level (ft)");
    stage = [...vgLine(t, f.vg_h_hand, low, "Virtual gage forecast, HAND rating", C.orange, { line: { width: 2.5 } }),
             ...vgLine(t, f.vg_h_usgs, low, "Virtual gage forecast, current USGS rating", C.orange, { line: { dash: "dot" } })];
    nwsLines(p, ls, [...f.vg_h_hand, ...f.vg_h_usgs]);
  } else {
    const dryY = f.vg_high.filter((_, i) => f.dry_day[i]);
    const low = lowMask(f.vg_high);
    flow = [...band(t, f.band_low, f.band_high, "Typical error (±30.1 %)", C.lilacs, 0.5), ...vgBand(t, f.vg_low, f.vg_high, low, "Virtual gage forecast range", C.orange, 0.5),
            line(t, f.nwm_sr_q, "NWM short-range forecast", C.blueberry, { line: { dash: "dash" } })];
    if (dryX.length) flow.push({ x: dryX, y: dryY, type: "scatter", mode: "markers", name: "Hour using dry-day rule (R = 1)", marker: { color: "#fff", size: 7, line: { color: C.orange, width: 2 } }, hoverinfo: "skip" });
    ls = LAYOUT("Depth above DEM channel (m)");
    stage = vgBand(t, depthLow(f.depth_low, f.depth_high), f.depth_high, low, "Virtual gage forecast depth range", C.orange, 0.45);
  }
  // grey shade after "now + horizon" (config: forecast.reliable_horizon_h): less reliable, not tested
  const fi = DATA.forecast_info, h0 = shiftH(DATA.now, fi.reliable_horizon_h);
  const late = [{ type: "rect", xref: "x", yref: "paper", x0: h0, x1: t[t.length - 1], y0: 0, y1: 1, fillcolor: rgba(C.muted, 0.09), line: { width: 0 }, layer: "below" }];
  const lateNote = { xref: "paper", yref: "paper", x: 0.995, y: 0.98, xanchor: "right", yanchor: "top", showarrow: false, bgcolor: "rgba(255,255,255,0.75)",
    text: `After +${fi.reliable_horizon_h} h: ${esc(fi.horizon_label)}`, font: { size: 10, color: C.muted } };
  const knownNote = known.length ? [{ xref: "x", yref: "paper", x: known[0], y: 0.9, xanchor: "left", yanchor: "top", showarrow: false,
    text: "upstream flow already measured", font: { size: 10, color: C.grape } }] : [];
  ly.shapes = [...shade, ...late];
  ly.annotations = [lateNote, ...knownNote];
  ls.shapes = [...(ls.shapes || []), ...shade, ...late];
  ls.annotations = [...(ls.annotations || []), lateNote];
  Plotly.newPlot("fc-flow", flow, ly, CONFIG);
  Plotly.newPlot("fc-stage", stage, ls, CONFIG);
}

function shiftH(s, h) {
  const d = new Date(s + ":00Z"); d.setTime(d.getTime() + h * 3600e3);
  return d.toISOString().slice(0, 16);
}

// ---------- footer
function buildFooter() {
  $("#footer").innerHTML = `
    <h4>Status</h4>
    <p>${esc(DATA.status_label)} Method ${esc(DATA.method_version)}. Last update ${when(DATA.generated)}.</p>
    <h4>Method</h4>
    <p><strong>Test points:</strong> virtual gage M13 = upstream USGS flow (sum of two gages, smoothed and delayed) × (1 + r · c · R<sup>p</sup>), where r is the
      ungaged-area ratio and R the 24-h MRMS rain ratio (ungaged part ÷ upstream). The USGS gage at the point is hidden from the method and shown only for comparison.
      <strong>Points without a gage:</strong> no-gage default M2 = upstream flow × (1 + r · R), with two area ratios, shown as a range with its typical error (±30.1 %).
      <strong>Water level:</strong> HAND channel geometry + Manning equation; at test points shifted to the USGS gage datum, and also shown with the current USGS rating.
      Without a gage: depth above the DEM channel, for all Manning n options. ${esc(DATA.low_flow_note)}
      <strong>Forecast (experimental, not tested):</strong> upstream flow held at its last measured value; rain from the NWM short-range forecast after the last MRMS hour.
      <a href="${esc(DATA.recipes_url)}" target="_blank" rel="noopener">Step-by-step recipes</a>.</p>
    <h4>Data sources</h4>
    <p>USGS Water Data API (flow 00060, gage height 00065; provisional data, may be revised). NOAA MRMS Caribbean MultiSensor QPE 1-h (Pass 2, Pass 1 when Pass 2 is missing).
      NOAA National Water Model v3.1 Puerto Rico: Open Loop analysis (no assimilation) and short-range forecast (no assimilation; rain = NBM).
      ${esc(DATA.nws_stages.source)}. Map © OpenStreetMap contributors.</p>
    <p>Victoria Vega Zapata, NOAA NERTO / CESSRST-II. Not an official NWS product. Do not use for warnings or decisions.</p>`;
}
