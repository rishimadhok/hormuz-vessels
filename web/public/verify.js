/* ============================================================
   Human verification portal — verify.js
   Loads artifacts/detections.json, renders a map + card grid,
   lets a human label each candidate, persists to localStorage,
   and exports JSON/CSV. No backend.
   ============================================================ */
(function () {
  "use strict";

  var DATA_URL = "artifacts/detections.json";
  var CHIP_BASE = "artifacts/"; // chip paths in JSON are like "chips/<scene>_NNN.png"
  var LABELS = ["vessel", "island", "rig", "noise"];
  var LABEL_COLORS = {
    unverified: "#b07cf0",
    vessel: "#35c759",
    island: "#4ea8de",
    rig: "#ff9f0a",
    noise: "#8b9aa8"
  };
  var KEYMAP = { v: "vessel", i: "island", r: "rig", n: "noise", u: "unverified" };

  var state = {
    data: null,
    dets: [],          // detections array (live label edited in place)
    cards: [],         // DOM card refs, parallel to dets
    markers: [],       // leaflet markers, parallel to dets
    map: null,
    storageKey: "hormuz-verify:default"
  };

  // ---------- storage ----------
  function storageKeyFor(data) {
    // Key by the scene_id(s) present so a refresh keeps progress for this scene set.
    var scenes = {};
    (data.detections || []).forEach(function (d) { if (d.scene_id) scenes[d.scene_id] = 1; });
    var ids = Object.keys(scenes).sort().join("|") || "default";
    return "hormuz-verify:" + ids;
  }
  function loadSaved() {
    try {
      var raw = localStorage.getItem(state.storageKey);
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }
  function saveLabels() {
    var map = {};
    state.dets.forEach(function (d, i) {
      map[detKey(d, i)] = d.label;
    });
    try { localStorage.setItem(state.storageKey, JSON.stringify(map)); } catch (e) {}
  }
  function detKey(d, i) {
    // Stable per-detection key within a scene: scene_id + index of chip.
    return (d.scene_id || "scene") + "#" + i;
  }

  // ---------- load ----------
  function init() {
    fetch(DATA_URL, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        state.data = data;
        state.dets = (data.detections || []).slice();
        state.storageKey = storageKeyFor(data);
        applySaved();
        renderHeader();
        renderGrid();
        renderSummary();
        initMap(); // may no-op/fallback if Leaflet missing
        wireGlobalButtons();
      })
      .catch(function (err) {
        var grid = document.getElementById("grid");
        document.getElementById("grid-empty").hidden = false;
        document.getElementById("grid-empty").textContent =
          "Failed to load detections.json: " + err.message;
        if (grid) grid.innerHTML = "";
      });
  }

  function applySaved() {
    var saved = loadSaved();
    state.dets.forEach(function (d, i) {
      var k = detKey(d, i);
      if (saved[k]) d.label = saved[k];
      else if (!d.label) d.label = "unverified";
    });
  }

  // ---------- header / context ----------
  function renderHeader() {
    var d = state.data;
    var loc = d.location || {};
    document.getElementById("ctx-region").textContent = loc.region || "Unknown region";

    // date: prefer scene_status keys, else detection dates, else start
    var dates = Object.keys(d.scene_status || {});
    if (!dates.length) {
      var set = {};
      state.dets.forEach(function (x) { if (x.date) set[x.date] = 1; });
      dates = Object.keys(set);
    }
    var dateLabel = dates.length ? dates.sort().join(", ") : (d.start || "");
    document.getElementById("ctx-date").textContent = dateLabel;

    // status: from scene_status (first), else detection.status
    var status = "";
    if (d.scene_status && dates.length) status = d.scene_status[dates[0]];
    if (!status && state.dets.length) status = state.dets[0].status;
    status = status || "Unknown";
    var badge = document.getElementById("ctx-status");
    badge.textContent = "Strait: " + status;
    var s = String(status).toLowerCase();
    badge.classList.remove("is-closed", "is-disrupted", "is-open");
    if (s.indexOf("close") >= 0) badge.classList.add("is-closed");
    else if (s.indexOf("disrupt") >= 0) badge.classList.add("is-disrupted");
    else if (s.indexOf("open") >= 0) badge.classList.add("is-open");

    document.getElementById("ctx-count").innerHTML =
      "<strong>" + state.dets.length + "</strong> candidates";
  }

  // ---------- grid ----------
  function fmt(n, dp) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toFixed(dp);
  }
  function intFmt(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Math.round(Number(n)).toLocaleString();
  }

  function renderGrid() {
    var grid = document.getElementById("grid");
    grid.innerHTML = "";
    state.cards = [];

    state.dets.forEach(function (d, i) {
      var card = document.createElement("div");
      card.className = "card label-" + d.label;
      card.tabIndex = 0;
      card.dataset.idx = i;

      // top: chip + meta
      var top = document.createElement("div");
      top.className = "card-top";

      var img = document.createElement("img");
      img.className = "chip";
      img.alt = "SAR chip " + i;
      img.loading = "lazy";
      img.decoding = "async";
      if (d.chip) {
        img.src = CHIP_BASE + d.chip;
        img.onerror = function () {
          img.replaceWith(placeholderChip());
        };
      } else {
        top.appendChild(placeholderChip());
      }
      if (d.chip) top.appendChild(img);

      var meta = document.createElement("div");
      meta.className = "card-meta";
      meta.innerHTML =
        '<div class="card-idx">#' + i + '</div>' +
        '<dl>' +
        '<dt>lat</dt><dd>' + fmt(d.lat, 4) + '</dd>' +
        '<dt>lon</dt><dd>' + fmt(d.lon, 4) + '</dd>' +
        '<dt>area</dt><dd>' + intFmt(d.area_px) + ' px</dd>' +
        '<dt>max I</dt><dd>' + intFmt(d.max_intensity) + '</dd>' +
        '</dl>' +
        '<div class="card-current label-' + d.label + '">' + d.label + '</div>';
      top.appendChild(meta);
      card.appendChild(top);

      // label buttons
      var btns = document.createElement("div");
      btns.className = "label-btns";
      LABELS.forEach(function (lab) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "lbtn";
        b.dataset.label = lab;
        b.textContent = lab.charAt(0).toUpperCase() + lab.slice(1);
        b.addEventListener("click", function (ev) {
          ev.stopPropagation();
          setLabel(i, lab, true);
        });
        btns.appendChild(b);
      });
      var unsure = document.createElement("button");
      unsure.type = "button";
      unsure.className = "lbtn lbtn-unsure";
      unsure.dataset.label = "unverified";
      unsure.textContent = "Unsure (reset)";
      unsure.addEventListener("click", function (ev) {
        ev.stopPropagation();
        setLabel(i, "unverified", false);
      });
      btns.appendChild(unsure);
      card.appendChild(btns);

      // interactions: focus/hover pans the map
      card.addEventListener("focus", function () { panToMarker(i); });
      card.addEventListener("mouseenter", function () { panToMarker(i, true); });
      card.addEventListener("keydown", function (ev) {
        var key = ev.key.toLowerCase();
        if (KEYMAP[key]) {
          ev.preventDefault();
          setLabel(i, KEYMAP[key], KEYMAP[key] !== "unverified");
        }
      });

      grid.appendChild(card);
      state.cards.push(card);
      refreshButtons(i);
    });
  }

  function placeholderChip() {
    var div = document.createElement("div");
    div.className = "chip placeholder";
    div.textContent = "no chip";
    return div;
  }

  function refreshButtons(i) {
    var card = state.cards[i];
    if (!card) return;
    var label = state.dets[i].label;
    card.querySelectorAll(".lbtn").forEach(function (b) {
      b.dataset.active = (b.dataset.label === label) ? "1" : "0";
    });
    card.className = "card label-" + label;
    var cur = card.querySelector(".card-current");
    if (cur) { cur.textContent = label; cur.className = "card-current label-" + label; }
  }

  // ---------- labeling ----------
  function setLabel(i, label, advance) {
    state.dets[i].label = label;
    refreshButtons(i);
    updateMarker(i);
    renderSummary();
    saveLabels();
    if (advance) advanceToNextUnlabeled(i);
  }

  function advanceToNextUnlabeled(from) {
    var n = state.dets.length;
    for (var step = 1; step <= n; step++) {
      var j = (from + step) % n;
      if (state.dets[j].label === "unverified") {
        var card = state.cards[j];
        if (card) {
          card.focus();
          card.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        return;
      }
    }
    // none left unlabeled — keep focus where it is
  }

  // ---------- summary ----------
  function renderSummary() {
    var counts = { vessel: 0, island: 0, rig: 0, noise: 0, unverified: 0 };
    state.dets.forEach(function (d) {
      counts[d.label] = (counts[d.label] || 0) + 1;
    });
    var total = state.dets.length;
    var verified = total - counts.unverified;

    var order = ["vessel", "island", "rig", "noise", "unverified"];
    var html = order.map(function (lab) {
      var name = lab.charAt(0).toUpperCase() + lab.slice(1);
      return '<span class="scount s-' + lab + '"><span class="dot"></span>' +
        name + ' <strong>' + counts[lab] + '</strong></span>';
    }).join("");
    document.getElementById("summary-counts").innerHTML = html;

    document.getElementById("summary-verified").textContent =
      verified + " of " + total + " verified";
    var pct = total ? Math.round((verified / total) * 100) : 0;
    document.getElementById("progress-fill").style.width = pct + "%";
  }

  // ---------- map ----------
  function initMap() {
    var fallback = document.getElementById("map-fallback");
    if (typeof L === "undefined" || !L.map) {
      showMapFallback();
      return;
    }
    try {
      var loc = state.data.location || {};
      var center = [
        (typeof loc.lat === "number") ? loc.lat : 25.2,
        (typeof loc.lon === "number") ? loc.lon : 56.575
      ];
      var map = L.map("map", { zoomControl: true, attributionControl: true }).setView(center, 10);
      state.map = map;

      var tiles = L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          maxZoom: 18,
          attribution: '© OpenStreetMap contributors'
        }
      );
      var tileErrors = 0;
      tiles.on("tileerror", function () {
        tileErrors++;
        // If essentially no tiles render, fall back but keep the (empty) map non-fatal.
        if (tileErrors > 8 && !state._tilesOk) showMapFallback();
      });
      tiles.on("tileload", function () { state._tilesOk = true; });
      tiles.addTo(map);

      state.dets.forEach(function (d, i) {
        if (typeof d.lat !== "number" || typeof d.lon !== "number") {
          state.markers.push(null);
          return;
        }
        var m = L.circleMarker([d.lat, d.lon], markerStyle(d.label));
        m.bindPopup(
          "#" + i + " · " + d.label + "<br>" +
          fmt(d.lat, 4) + ", " + fmt(d.lon, 4) + "<br>" +
          "area " + intFmt(d.area_px) + "px"
        );
        m.on("click", function () { focusCard(i); });
        m.addTo(map);
        state.markers.push(m);
      });
    } catch (e) {
      showMapFallback();
    }
  }

  function markerStyle(label) {
    var c = LABEL_COLORS[label] || LABEL_COLORS.unverified;
    return {
      radius: 6,
      color: "#0b1016",
      weight: 1,
      fillColor: c,
      fillOpacity: 0.9
    };
  }

  function updateMarker(i) {
    var m = state.markers[i];
    if (m && m.setStyle) {
      m.setStyle(markerStyle(state.dets[i].label));
      m.setPopupContent(
        "#" + i + " · " + state.dets[i].label + "<br>" +
        fmt(state.dets[i].lat, 4) + ", " + fmt(state.dets[i].lon, 4) + "<br>" +
        "area " + intFmt(state.dets[i].area_px) + "px"
      );
    }
  }

  function panToMarker(i, quiet) {
    var m = state.markers[i];
    if (state.map && m && m.getLatLng) {
      state.map.panTo(m.getLatLng(), { animate: true });
      if (!quiet && m.openPopup) m.openPopup();
    }
  }

  function focusCard(i) {
    var card = state.cards[i];
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.focus();
    card.classList.add("is-flash");
    setTimeout(function () { card.classList.remove("is-flash"); }, 900);
  }

  function showMapFallback() {
    var sec = document.getElementById("map");
    var fb = document.getElementById("map-fallback");
    if (sec) sec.hidden = true;
    if (fb) fb.hidden = false;
  }

  // ---------- bulk / reset / export ----------
  function wireGlobalButtons() {
    document.getElementById("btn-bulk-vessel").addEventListener("click", function () {
      var remaining = state.dets.filter(function (d) { return d.label === "unverified"; }).length;
      if (remaining === 0) { alert("No unlabeled candidates remain."); return; }
      if (!confirm("Mark all " + remaining + " remaining unlabeled candidates as Vessel?")) return;
      state.dets.forEach(function (d, i) {
        if (d.label === "unverified") { d.label = "vessel"; refreshButtons(i); updateMarker(i); }
      });
      renderSummary();
      saveLabels();
    });

    document.getElementById("btn-reset").addEventListener("click", function () {
      if (!confirm("Reset all labels to unverified? This clears saved progress.")) return;
      state.dets.forEach(function (d, i) {
        d.label = "unverified"; refreshButtons(i); updateMarker(i);
      });
      try { localStorage.removeItem(state.storageKey); } catch (e) {}
      renderSummary();
    });

    document.getElementById("btn-export-json").addEventListener("click", exportJSON);
    document.getElementById("btn-export-csv").addEventListener("click", exportCSV);
  }

  function exportJSON() {
    // Rebuild same shape with human labels applied in place.
    var out = JSON.parse(JSON.stringify(state.data));
    (out.detections || []).forEach(function (d, i) {
      if (state.dets[i]) d.label = state.dets[i].label;
    });
    out.verified_by = "human";
    out.verified_at = new Date().toISOString();
    download(
      new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }),
      "detections.verified.json"
    );
  }

  function exportCSV() {
    var rows = [["index", "lat", "lon", "area_px", "max_intensity", "label"]];
    state.dets.forEach(function (d, i) {
      rows.push([i, d.lat, d.lon, d.area_px, d.max_intensity, d.label]);
    });
    var csv = rows.map(function (r) {
      return r.map(function (c) {
        var s = (c === null || c === undefined) ? "" : String(c);
        return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      }).join(",");
    }).join("\n");
    download(new Blob([csv], { type: "text/csv" }), "detections.verified.csv");
  }

  function download(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  // ---------- go ----------
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
