/* Strait of Hormuz vessel detection — static frontend.
 * Reads pre-computed pipeline artifacts via fetch(). Falls back to bundled
 * sample data (./sample/) when the real artifacts 404, and shows a SAMPLE DATA badge.
 */

// Artifacts are synced into this directory (see sync_artifacts.sh). The page is
// served from web/public, so artifacts live at ./artifacts and ./data.
const REAL = {
  detections: "artifacts/detections.json",
  timeseries: "artifacts/timeseries.json",
  oil: "artifacts/oil.json",
  brief: "artifacts/brief.md",
  timeline: "data/timeline.json",
  news: "data/news.json",
  chipBase: "artifacts/", // chip/overlay paths in JSON are relative to this
};
const SAMPLE = {
  detections: "sample/detections.json",
  timeseries: "sample/timeseries.json",
  oil: "sample/oil.json",
  brief: "sample/brief.md",
  timeline: "sample/timeline.json",
  news: "sample/news.json",
  chipBase: "sample/",
};

const LABEL_COLORS = {
  vessel: "#35c759",
  rig: "#ff9f0a",
  island: "#4ea8de",
  noise: "#8b9aa8",
  unverified: "#b07cf0",
};

// Timeline event type -> color + which CSS class group it maps to.
// Covers the schema's documented types plus the richer set the live pipeline emits.
const EVENT_COLORS = {
  incident: "#ff453a",
  escalation: "#ff453a",
  disruption: "#ff453a",
  closure: "#ff9f0a",
  closed: "#ff9f0a",
  reopen: "#35c759",
  open: "#35c759",
  deescalation: "#35c759",
  _default: "#4ea8de",
};
// Group an arbitrary type into one of the 4 CSS legend classes (red/orange/green/blue).
function eventClass(t) {
  if (["incident", "escalation", "disruption"].includes(t)) return "incident";
  if (["closure", "closed"].includes(t)) return "closed";
  if (["reopen", "open", "deescalation"].includes(t)) return "open";
  return "other";
}

let usingSample = false;

// --- small fetch helpers -----------------------------------------------------
async function fetchJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
async function fetchText(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.text();
}

// Try real artifacts first; if detections.json is missing, fall back to sample.
async function loadConfig() {
  try {
    await fetchJSON(REAL.detections);
    return REAL;
  } catch (e) {
    usingSample = true;
    const badge = document.getElementById("sample-badge");
    if (badge) badge.hidden = false;
    return SAMPLE;
  }
}

// --- SECTION 1: hero / detections -------------------------------------------
function deriveOverlayPath(cfg, det) {
  // overlay is <scene_id>_overlay.png inside the chips dir.
  // Infer chips dir from a detection chip path, else default to "chips/".
  let chipsDir = "chips/";
  const sample = det.detections.find((d) => d.chip);
  if (sample && sample.chip.includes("/")) {
    chipsDir = sample.chip.slice(0, sample.chip.lastIndexOf("/") + 1);
  }
  return `${cfg.chipBase}${chipsDir}${det.scene_id}_overlay.png`;
}

function pickHeroScene(det) {
  // Prefer the scene with the most detections so the overlay is interesting.
  const bySc = {};
  for (const d of det.detections) bySc[d.scene_id] = (bySc[d.scene_id] || 0) + 1;
  let best = null, bestN = -1;
  for (const [sc, n] of Object.entries(bySc)) {
    if (n > bestN) { best = sc; bestN = n; }
  }
  return best;
}

function pickExampleDetections(dets, n = 6) {
  // Prefer verified, interesting labels; show variety; fall back to strongest signals.
  const priority = { vessel: 0, rig: 1, island: 2, noise: 3, unverified: 4 };
  const withReasoning = dets.filter((d) => (d.reasoning || "").trim().length > 0);
  const pool = withReasoning.length ? withReasoning : dets.slice();
  pool.sort((a, b) => {
    const pa = priority[a.label] ?? 5, pb = priority[b.label] ?? 5;
    if (pa !== pb) return pa - pb;
    return (b.confidence || 0) - (a.confidence || 0) || (b.max_intensity || 0) - (a.max_intensity || 0);
  });
  return pool.slice(0, n);
}

function labelCounts(dets) {
  const c = {};
  for (const d of dets) c[d.label] = (c[d.label] || 0) + 1;
  return c;
}

function renderHero(cfg, det) {
  const sceneId = { scene_id: pickHeroScene(det), detections: det.detections };
  const overlaySrc = deriveOverlayPath(cfg, sceneId);

  const img = document.getElementById("overlay-img");
  const fb = document.getElementById("overlay-fallback");
  img.onerror = () => { img.hidden = true; fb.hidden = false; };
  img.onload = () => { img.hidden = false; fb.hidden = true; };
  img.src = overlaySrc;

  // caption — collection · date · candidates · Strait open/closed status · location
  const cap = document.getElementById("scene-caption");
  const date = (det.detections.find((d) => d.scene_id === sceneId.scene_id) || {}).date || det.start || "";
  const loc = det.location || {};
  const status = (det.scene_status || {})[date] || "";
  const statusClass = "status-" + status.toLowerCase().replace(/[^a-z]/g, "");
  cap.innerHTML =
    `${det.collection || "sentinel-1-grd"} · <strong>${date}</strong> · ${det.count ?? det.detections.length} candidates` +
    (status ? ` <span class="status-badge ${statusClass}">Strait: ${status}</span>` : "") +
    (loc.region ? `<div class="scene-loc">\u{1F4CD} ${loc.region}${loc.lat != null ? ` (${loc.lat}, ${loc.lon})` : ""}</div>` : "");

  // verdict counts
  const counts = labelCounts(det.detections);
  const countsEl = document.getElementById("verdict-counts");
  countsEl.textContent = Object.entries(counts)
    .map(([k, v]) => `${v} ${k}`)
    .join(" · ");

  // note when nothing is verified yet
  const note = document.getElementById("verdicts-note");
  const verified = det.detections.some((d) => d.label !== "unverified");
  note.textContent = verified
    ? ""
    : "Vision verification has not run yet — all candidates are unverified. Showing the strongest returns.";

  // list
  const list = document.getElementById("verdict-list");
  list.innerHTML = "";
  for (const d of pickExampleDetections(det.detections)) {
    list.appendChild(verdictItem(cfg, d));
  }
}

function verdictItem(cfg, d) {
  const li = document.createElement("li");
  li.className = `verdict label-${d.label}`;

  // chip thumbnail (graceful fallback to a placeholder)
  const chip = document.createElement("img");
  chip.className = "verdict-chip";
  chip.alt = `${d.label} candidate chip`;
  chip.loading = "lazy";
  if (d.chip) {
    chip.src = `${cfg.chipBase}${d.chip}`;
    chip.onerror = () => {
      const ph = document.createElement("div");
      ph.className = "verdict-chip placeholder";
      ph.textContent = "no chip";
      chip.replaceWith(ph);
    };
  } else {
    chip.replaceWith(Object.assign(document.createElement("div"),
      { className: "verdict-chip placeholder", textContent: "no chip" }));
  }

  const body = document.createElement("div");
  body.className = "verdict-body";

  const top = document.createElement("div");
  top.className = "verdict-top";
  const tag = document.createElement("span");
  tag.className = `tag tag-${d.label}`;
  tag.textContent = d.label;
  const conf = document.createElement("span");
  conf.className = "conf";
  conf.textContent = `conf ${Number(d.confidence || 0).toFixed(2)}`;
  top.append(tag, conf);

  const coords = document.createElement("div");
  coords.className = "coords";
  coords.textContent = `${(+d.lat).toFixed(4)}°, ${(+d.lon).toFixed(4)}° · ${d.area_px} px`;

  const reason = document.createElement("p");
  const txt = (d.reasoning || "").trim();
  reason.className = txt ? "reasoning" : "reasoning empty";
  reason.textContent = txt || "No reasoning recorded (candidate not yet sent to vision pass).";

  body.append(top, coords, reason);
  li.append(chip, body);
  return li;
}

// --- SECTION 2: "Why SAR?" primer -------------------------------------------
// Picks real vessel chips from detections.json: one strong example for the
// EO-vs-SAR comparison tile, plus a handful for the "what ships look like" row.
// Prefers brighter / larger returns so the bright-blob signature is obvious.
// Degrades gracefully: if a chip fails to load it's removed; if none load the
// black EO tile + a captioned placeholder remain so the section never breaks.
function pickGalleryVessels(dets, n) {
  const vessels = dets.filter((d) => d.label === "vessel" && d.chip);
  vessels.sort((a, b) =>
    (b.max_intensity || 0) - (a.max_intensity || 0) ||
    (b.area_px || 0) - (a.area_px || 0));
  // Spread picks across the sorted list for visual variety, not 6 near-identical blobs.
  if (vessels.length <= n) return vessels;
  const top = vessels.slice(0, Math.min(vessels.length, n * 4));
  const step = Math.max(1, Math.floor(top.length / n));
  const out = [];
  for (let i = 0; i < top.length && out.length < n; i += step) out.push(top[i]);
  return out.slice(0, n);
}

function renderPrimer(cfg, det) {
  const dets = (det && det.detections) || [];
  const picks = pickGalleryVessels(dets, 6);

  // (1) EO-vs-SAR comparison: drop the strongest vessel into the SAR tile.
  const frame = document.getElementById("cmp-sar-frame");
  if (frame) {
    const lead = picks[0];
    if (lead) {
      const img = document.createElement("img");
      img.className = "cmp-sar-img";
      img.alt = "Real SAR chip: a vessel as a bright return on dark water";
      img.loading = "lazy";
      img.src = `${cfg.chipBase}${lead.chip}`;
      img.onload = () => { frame.innerHTML = ""; frame.appendChild(img); };
      img.onerror = () => {
        frame.innerHTML = '<div class="cmp-placeholder">SAR chip unavailable</div>';
      };
    } else {
      frame.innerHTML = '<div class="cmp-placeholder">No vessel chip available</div>';
    }
  }

  // (2) Gallery row of real vessel chips.
  const gal = document.getElementById("chip-gallery");
  if (gal) {
    gal.innerHTML = "";
    const galPicks = picks.length ? picks : [];
    if (!galPicks.length) {
      gal.innerHTML = '<li class="muted small">No vessel chips available in this run.</li>';
    }
    for (const d of galPicks) {
      const li = document.createElement("li");
      li.className = "chip-cell";
      const img = document.createElement("img");
      img.className = "gallery-chip";
      img.alt = "SAR vessel chip — bright return on dark water";
      img.loading = "lazy";
      img.src = `${cfg.chipBase}${d.chip}`;
      img.onerror = () => { li.remove(); };   // drop broken chips, keep the row clean
      li.appendChild(img);
      gal.appendChild(li);
    }
  }
}

// --- SECTION 3: traffic vs. price chart -------------------------------------
// Pull moving_count per date — the vessel estimate. Older artifacts only carry
// candidate_count/vessel_count, so degrade gracefully to the next-best field.
function movingSeries(series) {
  return series.map((s) =>
    s.moving_count ?? s.vessel_count ?? s.candidate_count ?? 0);
}
// static_count = recurring fixed features (islands/rigs) filtered out. May be absent.
function staticSeries(series) {
  return series.map((s) => (s.static_count == null ? null : s.static_count));
}
// Brent price aligned to each date; null (gap) where oil data is missing.
function brentSeries(labels, oil) {
  const byDate = (oil && oil.by_date) || {};
  return labels.map((d) => {
    const v = byDate[d];
    return v && v.brent != null ? v.brent : null;
  });
}

function renderChart(ts, oil, timeline) {
  const series = (ts && ts.series) || [];
  const empty = document.getElementById("chart-empty");
  const canvas = document.getElementById("traffic-chart");
  const events = (timeline && timeline.events) || [];
  renderEventLegend(events);

  // no timeseries at all -> keep the existing "no data" placeholder.
  if (!series.length) { empty.hidden = false; canvas.style.display = "none"; return; }

  const labels = series.map((s) => s.date);
  const moving = movingSeries(series);
  const statics = staticSeries(series);
  const brent = brentSeries(labels, oil);
  const hasStatic = statics.some((v) => v != null && v > 0);
  const hasBrent = brent.some((v) => v != null);

  if (typeof Chart === "undefined") { renderSvgFallback(canvas, labels, moving); return; }

  const eventColor = (t) => EVENT_COLORS[t] || EVENT_COLORS._default;

  // Plugin: vertical lines + labels at event dates that fall within the series window.
  const eventLines = {
    id: "eventLines",
    afterDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const x = scales.x;
      events.forEach((ev) => {
        const idx = labels.indexOf(ev.date);
        if (idx < 0) return;
        const px = x.getPixelForValue(idx);
        ctx.save();
        ctx.strokeStyle = eventColor(ev.type);
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(px, chartArea.top);
        ctx.lineTo(px, chartArea.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = eventColor(ev.type);
        ctx.font = "600 10px -apple-system, sans-serif";
        ctx.textAlign = px > (chartArea.left + chartArea.right) / 2 ? "right" : "left";
        ctx.fillText((ev.type || "event").toUpperCase(), px + (ctx.textAlign === "right" ? -4 : 4), chartArea.top + 11);
        ctx.restore();
      });
    },
  };

  const datasets = [];

  // (4) static detections, drawn faintly behind as a muted area on the vessel axis.
  if (hasStatic) {
    datasets.push({
      label: "Static (islands/rigs, filtered out)",
      data: statics,
      yAxisID: "yVessels",
      borderColor: "rgba(139,154,168,0.55)",
      backgroundColor: "rgba(139,154,168,0.10)",
      fill: true, tension: 0.25, pointRadius: 0, borderWidth: 1,
    });
  }

  // (1) primary series: moving vessels on the left axis.
  datasets.push({
    label: "Vessels detected (moving)",
    data: moving,
    yAxisID: "yVessels",
    borderColor: "#35c759",
    backgroundColor: "rgba(53,199,89,0.15)",
    fill: true, tension: 0.25, pointRadius: 3, borderWidth: 2,
    order: 0,
  });

  // (2) Brent crude on the secondary right axis; spanGaps:false so missing dates gap.
  if (hasBrent) {
    datasets.push({
      label: "Brent crude ($/bbl)",
      data: brent,
      yAxisID: "yBrent",
      borderColor: "#ff9f0a",
      backgroundColor: "rgba(255,159,10,0.10)",
      fill: false, tension: 0.25, pointRadius: 3, borderWidth: 2,
      spanGaps: false,
      order: 0,
    });
  }

  const scales = {
    x: { grid: { color: "#1b2733" }, ticks: { color: "#8b9aa8", maxRotation: 0, autoSkip: true } },
    yVessels: {
      type: "linear", position: "left", beginAtZero: true,
      grid: { color: "#1b2733" },
      ticks: { color: "#8b9aa8", precision: 0 },
      title: { display: true, text: "Vessels detected", color: "#35c759" },
    },
  };
  if (hasBrent) {
    scales.yBrent = {
      type: "linear", position: "right",
      grid: { drawOnChartArea: false },
      ticks: { color: "#ff9f0a" },
      title: { display: true, text: "Brent $/bbl", color: "#ff9f0a" },
    };
  }

  // eslint-disable-next-line no-new
  new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales,
      plugins: {
        legend: { labels: { color: "#e6edf3", boxWidth: 12 } },
        tooltip: { callbacks: {
          afterBody(items) {
            const ev = events.find((e) => e.date === labels[items[0].dataIndex]);
            return ev ? `\n${(ev.type || "").toUpperCase()}: ${ev.title || ""}` : "";
          },
        }},
      },
    },
    plugins: [eventLines],
  });
}

function renderEventLegend(events) {
  const ul = document.getElementById("event-legend");
  ul.innerHTML = "";
  if (!events.length) {
    ul.innerHTML = '<li class="muted">No timeline events available (data/timeline.json not present).</li>';
    return;
  }
  for (const ev of events) {
    const li = document.createElement("li");
    li.className = `event-${eventClass(ev.type)}`;
    const bar = document.createElement("span"); bar.className = "event-bar";
    const txt = document.createElement("span");
    txt.innerHTML = `<span class="ev-date">${ev.date}</span> — ${escapeHTML(ev.title || ev.type || "event")}`;
    li.append(bar, txt);
    ul.appendChild(li);
  }
}

// Minimal SVG line chart used only if Chart.js failed to load from CDN.
function renderSvgFallback(canvas, labels, values) {
  const w = canvas.clientWidth || 600, h = 220, pad = 30;
  const max = Math.max(1, ...values);
  const stepX = labels.length > 1 ? (w - pad * 2) / (labels.length - 1) : 0;
  const pts = values.map((v, i) => `${pad + i * stepX},${h - pad - (v / max) * (h - pad * 2)}`).join(" ");
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="vessel count">
    <polyline fill="none" stroke="#35c759" stroke-width="2" points="${pts}"/>
    ${values.map((v, i) => `<circle cx="${pad + i * stepX}" cy="${h - pad - (v / max) * (h - pad * 2)}" r="3" fill="#35c759"/>`).join("")}
    <text x="${pad}" y="${h - 8}" fill="#8b9aa8" font-size="10">${labels[0] || ""}</text>
    <text x="${w - pad}" y="${h - 8}" fill="#8b9aa8" font-size="10" text-anchor="end">${labels[labels.length - 1] || ""}</text>
  </svg>`;
  const div = document.createElement("div");
  div.innerHTML = svg;
  canvas.replaceWith(div.firstElementChild);
}

// --- SECTION 5: analyst brief (tiny markdown renderer) ----------------------
function renderBrief(md) {
  const el = document.getElementById("brief-body");
  if (md == null) {
    el.innerHTML = '<p class="muted">No analyst brief yet. The pipeline will write <code>artifacts/brief.md</code> after the vision + summarization pass.</p>';
    return;
  }
  el.innerHTML = mdToHTML(md);
}

// Supports headings, bold/italic/code, links, ul/ol, blockquote, paragraphs, hr.
function mdToHTML(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let inUL = false, inOL = false, para = [];
  const closeLists = () => {
    if (inUL) { out.push("</ul>"); inUL = false; }
    if (inOL) { out.push("</ol>"); inOL = false; }
  };
  const flushPara = () => {
    if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; }
  };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) { flushPara(); closeLists(); continue; }
    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      flushPara(); closeLists();
      const lvl = m[1].length;
      out.push(`<h${lvl}>${inline(m[2])}</h${lvl}>`);
    } else if (/^(\*\*\*|---|___)\s*$/.test(line)) {
      flushPara(); closeLists(); out.push("<hr>");
    } else if ((m = line.match(/^\s*[-*+]\s+(.*)$/))) {
      flushPara();
      if (!inUL) { closeLists(); out.push("<ul>"); inUL = true; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flushPara();
      if (!inOL) { closeLists(); out.push("<ol>"); inOL = true; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\s*>\s?(.*)$/))) {
      flushPara(); closeLists();
      out.push(`<blockquote>${inline(m[1])}</blockquote>`);
    } else {
      para.push(line.trim());
    }
  }
  flushPara(); closeLists();
  return out.join("\n");
}

function inline(s) {
  s = escapeHTML(s);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  return s;
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- SECTION 4: signals — news & market -------------------------------------
// Brent on/near a date = nearest oil entry on-or-before that date. Returns
// { brent, date } or null when no entry exists on or before the news date.
function brentOnOrBefore(oil, date) {
  const byDate = (oil && oil.by_date) || {};
  let best = null;
  for (const [d, v] of Object.entries(byDate)) {
    if (d <= date && v && v.brent != null && (best === null || d > best.date)) {
      best = { date: d, brent: v.brent };
    }
  }
  return best;
}

// "03 Apr" from "2026-04-03" — short, locale-stable label for the price chip.
function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return iso || "";
  const mon = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+m[2] - 1] || "";
  return `${m[3]} ${mon}`;
}

function renderNews(news, oil) {
  const ul = document.getElementById("news-feed");
  const empty = document.getElementById("news-empty");
  if (!ul) return;
  ul.innerHTML = "";

  const items = (news && Array.isArray(news.items)) ? news.items.slice() : [];
  if (!items.length) {
    if (empty) empty.hidden = false;          // muted "no signals loaded"
    document.getElementById("signals").hidden = true;
    return;
  }
  if (empty) empty.hidden = true;

  // Newest first.
  items.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));

  for (const it of items) {
    const li = document.createElement("li");
    const isSocial = (it.kind || "news") === "social";
    li.className = `signal ${isSocial ? "signal-social" : "signal-news"}`;

    const meta = document.createElement("div");
    meta.className = "signal-meta";
    const date = document.createElement("span");
    date.className = "signal-date";
    date.textContent = it.date || "";
    const badge = document.createElement("span");
    badge.className = `signal-badge ${isSocial ? "badge-social" : "badge-news"}`;
    badge.textContent = isSocial ? "X" : "NEWS";
    const src = document.createElement("span");
    src.className = "signal-source";
    src.textContent = it.source || "";
    meta.append(date, badge, src);

    const head = document.createElement("div");
    head.className = "signal-headline";
    const text = (it.headline || "").trim() || "(untitled)";
    if (it.url) {
      const a = document.createElement("a");
      a.href = it.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = text;
      head.appendChild(a);
    } else {
      head.textContent = text;                 // no broken link for url-less items
    }

    const body = document.createElement("div");
    body.className = "signal-body";
    body.append(meta, head);

    if ((it.summary || "").trim()) {
      const sum = document.createElement("p");
      sum.className = "signal-summary";
      sum.textContent = it.summary.trim();
      body.appendChild(sum);
    }

    // The key correlation bit: Brent on/near the news date.
    const b = brentOnOrBefore(oil, it.date);
    if (b) {
      const price = document.createElement("span");
      price.className = "signal-price";
      price.textContent = `Brent $${Number(b.brent).toFixed(2)} on ${shortDate(b.date)}`;
      body.appendChild(price);
    }

    li.appendChild(body);
    ul.appendChild(li);
  }
}

// --- run-meta header --------------------------------------------------------
function renderRunMeta(det) {
  const el = document.getElementById("run-meta");
  if (!det) return;
  const bbox = (det.bbox || []).map((n) => (+n).toFixed(2)).join(", ");
  el.innerHTML =
    `<strong>${det.start || "?"} → ${det.end || "?"}</strong><br>` +
    `bbox [${bbox}]${usingSample ? " · sample" : ""}`;
}

// --- boot -------------------------------------------------------------------
(async function main() {
  const cfg = await loadConfig();

  // Each artifact loads independently so one missing file never blanks the page.
  let det = null, ts = null, oil = null, timeline = null, brief = null, news = null;

  try { det = await fetchJSON(cfg.detections); } catch (e) { /* fatal-ish, handled below */ }
  try { ts = await fetchJSON(cfg.timeseries); } catch (e) { ts = null; }
  try { oil = await fetchJSON(cfg.oil); } catch (e) { oil = null; }
  try { timeline = await fetchJSON(cfg.timeline); } catch (e) { timeline = null; }
  try { brief = await fetchText(cfg.brief); } catch (e) { brief = null; }
  try { news = await fetchJSON(cfg.news); } catch (e) { news = null; }

  if (det && det.detections) {
    renderRunMeta(det);
    renderHero(cfg, det);
    renderPrimer(cfg, det);
  } else {
    document.getElementById("overlay-fallback").hidden = false;
    document.getElementById("overlay-img").hidden = true;
    document.getElementById("verdicts-note").textContent =
      "No detections.json found. Run the pipeline, then sync artifacts.";
  }

  renderChart(ts, oil, timeline);
  renderNews(news, oil);            // reuse the oil object already loaded for the chart
  renderBrief(brief);
})();
