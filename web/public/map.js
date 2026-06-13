/* ====================================================================
   map.js — geographic detection map for visual geolocation verification.

   COORDINATE ORDERING — read this carefully:
   The JSON stores positions as [lon, lat] (and bbox as
   [minLon, minLat, maxLon, maxLat]). Leaflet expects [lat, lng] for points
   and L.latLngBounds([[minLat, minLon], [maxLat, maxLon]]) for rectangles.
   Every place we hand a coordinate to Leaflet we SWAP to [lat, lon].
   The helpers `pt()` and `boundsFromBbox()` are the only conversion points.
   ==================================================================== */
(function () {
  "use strict";

  // ---- hard failure: Leaflet didn't load --------------------------------
  if (typeof L === "undefined") {
    var errEl = document.getElementById("map-error");
    if (errEl) errEl.hidden = false;
    return;
  }

  // ---- color per label (mirrors style.css variables) --------------------
  var LABEL_COLORS = {
    unverified: "#b07cf0", // --unverified (cyan/gray-ish purple per spec "unverified=cyan/gray")
    vessel: "#35c759",     // --vessel green
    island: "#4ea8de",     // --island blue
    rig: "#ff9f0a",        // --rig orange
    noise: "#2a3744"       // dark
  };
  function colorFor(label) {
    return LABEL_COLORS[label] || LABEL_COLORS.unverified;
  }

  // ---- coordinate conversion (the ONLY lon/lat -> lat/lng swaps) --------
  // Point: JSON [lon, lat] -> Leaflet [lat, lon]
  function pt(lon, lat) {
    return [lat, lon];
  }
  // bbox: JSON [minLon, minLat, maxLon, maxLat]
  //   -> Leaflet bounds [[minLat, minLon], [maxLat, maxLon]]
  function boundsFromBbox(bbox) {
    var minLon = bbox[0], minLat = bbox[1], maxLon = bbox[2], maxLat = bbox[3];
    return L.latLngBounds([minLat, minLon], [maxLat, maxLon]);
  }

  // ---- basemaps ---------------------------------------------------------
  var satellite = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution:
        "Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community"
    }
  );
  var streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  });

  var map = L.map("map", {
    layers: [satellite], // DEFAULT = satellite
    zoomControl: true,
    worldCopyJump: true
  });
  // Safe default view (Strait of Hormuz) in case data fetch is slow/fails.
  map.setView([25.2, 56.575], 11);

  L.control.layers(
    { Satellite: satellite, Streets: streets },
    {},
    { position: "topright", collapsed: false }
  ).addTo(map);

  // ---- escaping helper for popup text -----------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---- static vs moving styling -----------------------------------------
  // moving (likely vessel) = solid color box + circle marker.
  // static (island/rig)    = desaturated gray, dashed outline, diamond marker.
  var STATIC_COLOR = "#8a97a3"; // desaturated gray
  function isStatic(d) {
    return d && d.is_static === true;
  }

  // ---- build a detection popup ------------------------------------------
  function popupHtml(d, timesteps) {
    var label = d.label || "unverified";
    var stat = isStatic(d);
    var col = stat ? STATIC_COLOR : colorFor(label);
    var chip = d.chip ? "artifacts/" + d.chip : "";
    var img = chip
      ? '<img class="det-chip" src="' + esc(chip) +
        '" alt="SAR chip" onerror="this.style.display=\'none\'" />'
      : "";
    var lat = (typeof d.lat === "number") ? d.lat.toFixed(5) : "—";
    var lon = (typeof d.lon === "number") ? d.lon.toFixed(5) : "—";

    // Kind line: STATIC (recurring fixed feature) vs moving candidate vessel.
    var kindHtml;
    if (stat) {
      var pdates = (typeof d.persistence_dates === "number") ? d.persistence_dates : null;
      var denom = (typeof timesteps === "number" && timesteps > 0) ? timesteps : null;
      var frac = (pdates != null && denom != null) ? (pdates + "/" + denom) : (pdates != null ? String(pdates) : "multiple");
      kindHtml =
        '<p class="det-kind det-kind-static">STATIC — recurs on ' + esc(frac) +
        ' dates (likely island/rig)</p>';
    } else {
      kindHtml = '<p class="det-kind det-kind-moving">moving — candidate vessel</p>';
    }

    return (
      '<div class="det-popup">' +
      img +
      '<span class="det-tag" style="background:' + col + '">' + esc(label) + "</span>" +
      kindHtml +
      "<dl>" +
      "<dt>lat</dt><dd>" + lat + "</dd>" +
      "<dt>lon</dt><dd>" + lon + "</dd>" +
      "<dt>area_px</dt><dd>" + esc(d.area_px) + "</dd>" +
      "<dt>max_int</dt><dd>" + esc(d.max_intensity) + "</dd>" +
      "</dl>" +
      "</div>"
    );
  }

  // ---- status badge styling ---------------------------------------------
  function applyStatusBadge(el, status) {
    var s = String(status || "").trim();
    el.textContent = "Strait: " + (s || "—");
    var key = s.toLowerCase();
    el.classList.remove("status-closed", "status-disrupted", "status-open");
    if (key === "closed") el.classList.add("status-closed");
    else if (key === "disrupted") el.classList.add("status-disrupted");
    else if (key === "open") el.classList.add("status-open");
  }

  // ---- crude oil price panel --------------------------------------------
  // `sceneDate` is the SAME date the map displays as the scene (data.start),
  // which matches the scene_status key. We use it to index oil.by_date.
  function renderOil(oil, sceneDate) {
    var panel = document.getElementById("ml-oil");
    if (!panel) return;
    var byDate = (oil && typeof oil === "object" && oil.by_date &&
                  typeof oil.by_date === "object") ? oil.by_date : {};
    var rows = document.getElementById("oil-rows");
    var naEl = document.getElementById("oil-na");
    var dateEl = document.getElementById("oil-date");

    if (dateEl) dateEl.textContent = sceneDate ? "— " + sceneDate : "";

    var entry = sceneDate ? byDate[sceneDate] : null;
    if (entry && (typeof entry.brent === "number" || typeof entry.wti === "number")) {
      var fmt = function (v) {
        return typeof v === "number" ? "$" + v.toFixed(2) + "/bbl" : "n/a";
      };
      document.getElementById("oil-brent").textContent = fmt(entry.brent);
      document.getElementById("oil-wti").textContent = fmt(entry.wti);
      if (rows) rows.hidden = false;
      if (naEl) naEl.hidden = true;
    } else {
      // No data for this date: show explicit n/a rather than hiding silently.
      if (rows) rows.hidden = true;
      if (naEl) naEl.hidden = false;
    }
    panel.hidden = false;
  }

  // ---- news / signals panel ---------------------------------------------
  // Acquisition (stepper) dates rarely match a headline exactly, so the
  // matching rule is: show all items dated EXACTLY on the active date; if
  // none, fall back to the most recent item(s) ON OR BEFORE the active date
  // (the prevailing/standing headline) and label them "as of <itemdate>".
  // Items are kept sorted ascending by date in NEWS (set at load time).
  function renderNews(activeDate) {
    var panel = document.getElementById("news-panel");
    if (!panel) return;
    var listEl = document.getElementById("news-list");
    var dateEl = document.getElementById("news-date");
    var emptyEl = document.getElementById("news-empty");

    // No data (fetch failed) => keep panel hidden, never break the map.
    if (!Array.isArray(NEWS) || !NEWS.length) { panel.hidden = true; return; }
    panel.hidden = false;

    if (dateEl) dateEl.textContent = activeDate ? "— " + activeDate : "";

    // Items exactly on the active date.
    var exact = [];
    var onOrBefore = [];
    NEWS.forEach(function (it) {
      if (!it || !it.date) return;
      if (activeDate && it.date === activeDate) exact.push(it);
      if (activeDate && it.date <= activeDate) onOrBefore.push(it);
    });

    var picked, asOf = false;
    if (exact.length) {
      picked = exact.slice(0, 3);
    } else if (onOrBefore.length) {
      // Most recent on/before: NEWS is ascending, so take from the tail.
      // Show the most recent item plus any sharing that same (latest) date.
      var latest = onOrBefore[onOrBefore.length - 1].date;
      picked = onOrBefore.filter(function (it) { return it.date === latest; }).slice(0, 3);
      asOf = true;
    } else {
      picked = [];
    }

    if (!picked.length) {
      if (listEl) listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    var html = picked.map(function (it) {
      var isSocial = String(it.kind || "").toLowerCase() === "social";
      var badge = isSocial ? "X" : "NEWS";
      var badgeCls = isSocial ? "news-badge news-badge-social" : "news-badge news-badge-news";
      var asOfHtml = asOf
        ? '<span class="news-asof">as of ' + esc(it.date) + "</span>"
        : "";
      var srcHtml = it.source
        ? '<span class="news-source">' + esc(it.source) + "</span>"
        : "";
      var headline = esc(it.headline || "(untitled)");
      var headHtml = it.url
        ? '<a class="news-link" href="' + esc(it.url) +
          '" target="_blank" rel="noopener">' + headline + "</a>"
        : '<span class="news-link news-link-plain">' + headline + "</span>";
      var summaryHtml = it.summary
        ? '<p class="news-summary">' + esc(it.summary) + "</p>"
        : "";
      return (
        '<article class="news-item">' +
        '<div class="news-meta">' +
        '<span class="' + badgeCls + '">' + badge + "</span>" +
        '<span class="news-itemdate">' + esc(it.date) + "</span>" +
        asOfHtml +
        srcHtml +
        "</div>" +
        '<div class="news-headline">' + headHtml + "</div>" +
        summaryHtml +
        "</article>"
      );
    }).join("");

    if (listEl) listEl.innerHTML = html;
  }

  // ---- SAR scene panel --------------------------------------------------
  // Shows the actual annotated Sentinel-1 overlay PNG for the active date.
  // Picks the scene_id of the detection on that date with the most detections
  // (ties broken by first seen). Loads artifacts/chips/<scene_id>_overlay.png.
  // Graceful: no detection for the date OR image 404 => muted empty message.
  function sceneIdForDate(activeDate) {
    if (!activeDate || !DATA || !Array.isArray(DATA.detections)) return null;
    var counts = {};
    var order = [];
    DATA.detections.forEach(function (d) {
      if (!d || d.date !== activeDate || !d.scene_id) return;
      if (!(d.scene_id in counts)) { counts[d.scene_id] = 0; order.push(d.scene_id); }
      counts[d.scene_id]++;
    });
    var best = null, bestN = -1;
    order.forEach(function (sid) {
      if (counts[sid] > bestN) { bestN = counts[sid]; best = sid; }
    });
    return best;
  }

  function renderScene(activeDate) {
    var panel = document.getElementById("scene-panel");
    if (!panel) return;
    var dateEl = document.getElementById("scene-date");
    var linkEl = document.getElementById("scene-link");
    var imgEl = document.getElementById("scene-img");
    var capEl = document.getElementById("scene-caption");
    var emptyEl = document.getElementById("scene-empty");

    panel.hidden = false;
    if (dateEl) dateEl.textContent = activeDate ? "— " + activeDate : "";

    var sid = sceneIdForDate(activeDate);

    // No scene for this date: show muted message, hide image.
    if (!sid) {
      if (imgEl) { imgEl.removeAttribute("src"); imgEl.style.display = "none"; }
      if (linkEl) { linkEl.style.display = "none"; linkEl.removeAttribute("href"); }
      if (capEl) capEl.hidden = true;
      if (emptyEl) emptyEl.hidden = false;
      return;
    }

    var src = "artifacts/chips/" + sid + "_overlay.png";
    if (linkEl) {
      linkEl.style.display = "";
      linkEl.href = src;
    }
    if (imgEl) {
      imgEl.style.display = "";
      // onerror (e.g. overlay 404s): hide image + link, show muted message.
      imgEl.onerror = function () {
        imgEl.style.display = "none";
        if (linkEl) linkEl.style.display = "none";
        if (capEl) capEl.hidden = true;
        if (emptyEl) emptyEl.hidden = false;
      };
      imgEl.onload = function () {
        imgEl.style.display = "";
        if (linkEl) linkEl.style.display = "";
        if (capEl) capEl.hidden = false;
        if (emptyEl) emptyEl.hidden = true;
      };
      imgEl.src = src;
    }
    if (capEl) {
      capEl.textContent =
        "Sentinel-1 radar image, " + activeDate +
        " — bright marks are detected vessels; boxes are detections.";
      capEl.hidden = false;
    }
    if (emptyEl) emptyEl.hidden = true;
  }

  // ---- multi-timestep date list -----------------------------------------
  // Source of truth for the steppable dates: persistence.dates, then a sorted
  // unique set of detection dates, then scene_status keys. Always non-empty
  // when there is any data so the legend still renders for single-date runs.
  function computeDates(data, dets) {
    var p = data.persistence;
    if (p && Array.isArray(p.dates) && p.dates.length) {
      return p.dates.slice();
    }
    var seen = {};
    var out = [];
    dets.forEach(function (d) {
      if (d && d.date && !seen[d.date]) { seen[d.date] = 1; out.push(d.date); }
    });
    if (out.length) { out.sort(); return out; }
    if (data.scene_status && typeof data.scene_status === "object") {
      var keys = Object.keys(data.scene_status);
      if (keys.length) { keys.sort(); return keys; }
    }
    // Last resort: the single start date (or empty placeholder).
    var single = data.start || data.end || "";
    return single ? [single] : [""];
  }

  // ---- module-level state -----------------------------------------------
  var detBounds = null;       // L.latLngBounds covering active-date boxes
  var detLayer = null;        // L.layerGroup holding active-date detections
  var DATA = null;            // raw detections.json
  var OIL = null;             // raw oil.json (may stay null)
  var NEWS = null;            // sorted news items from data/news.json (may stay null)
  var DATES = [];             // steppable date list
  var ACTIVE_IDX = 0;         // index into DATES
  var TIMESTEPS = 1;          // persistence.timesteps (or DATES.length)
  var hideStatic = false;     // "Hide static" toggle state

  // ---- draw detections for ONE date -------------------------------------
  function drawDate(date) {
    if (!map) return;
    if (detLayer) { map.removeLayer(detLayer); detLayer = null; }
    detLayer = L.layerGroup().addTo(map);
    detBounds = L.latLngBounds([]);

    var dets = Array.isArray(DATA.detections) ? DATA.detections : [];
    var moving = 0, staticN = 0;

    dets.forEach(function (d) {
      // Only this date's detections. If detections carry no date (legacy
      // single-date), draw them all on the single active date.
      if (d.date && date && d.date !== date) return;

      var stat = isStatic(d);
      if (stat) staticN++; else moving++;
      if (stat && hideStatic) return; // filtered out, but still counted above

      var baseCol = stat ? STATIC_COLOR : colorFor(d.label);
      var rectOpts = stat
        ? { color: baseCol, weight: 1, dashArray: "5 4", fillColor: baseCol, fillOpacity: 0.12 }
        : { color: baseCol, weight: 1, fillColor: baseCol, fillOpacity: 0.25 };

      if (Array.isArray(d.bbox_geo) && d.bbox_geo.length === 4) {
        var b = boundsFromBbox(d.bbox_geo);
        detBounds.extend(b);
        L.rectangle(b, rectOpts)
          .bindPopup(popupHtml(d, TIMESTEPS), { maxWidth: 220, minWidth: 170 })
          .addTo(detLayer);
      }

      if (typeof d.lon === "number" && typeof d.lat === "number") {
        var center = pt(d.lon, d.lat);
        detBounds.extend(center);
        var marker = stat
          // static => diamond marker (rotated square) via a divIcon
          ? L.marker(center, {
              icon: L.divIcon({
                className: "static-diamond-wrap",
                html: '<span class="static-diamond" style="background:' + baseCol + '"></span>',
                iconSize: [12, 12],
                iconAnchor: [6, 6]
              })
            })
          // moving => solid green circle marker
          : L.circleMarker(center, {
              radius: 4, color: baseCol, weight: 1,
              fillColor: baseCol, fillOpacity: 0.45
            });
        marker.bindPopup(popupHtml(d, TIMESTEPS), { maxWidth: 220, minWidth: 170 })
          .addTo(detLayer);
      }
    });

    return { moving: moving, staticN: staticN };
  }

  // ---- update everything that depends on the active date ----------------
  function applyDate(idx) {
    if (!DATES.length) return;
    ACTIVE_IDX = Math.max(0, Math.min(idx, DATES.length - 1));
    var date = DATES[ACTIVE_IDX];

    var counts = drawDate(date) || { moving: 0, staticN: 0 };

    // Legend date.
    var dateEl = document.getElementById("ml-date");
    if (dateEl) dateEl.textContent = date || "";

    // Strait status from scene_status[date] (fallback: any value, then det status).
    var status = "";
    var ss = DATA.scene_status;
    if (ss && typeof ss === "object") {
      if (date && ss[date]) status = ss[date];
      else { var vals = Object.values(ss); if (vals.length) status = vals[0]; }
    }
    applyStatusBadge(document.getElementById("ml-status"), status);

    // Per-date moving/static split.
    var countEl = document.getElementById("ml-count");
    if (countEl) {
      countEl.textContent =
        "Moving (vessels): " + counts.moving +
        " · Static (islands/rigs): " + counts.staticN;
    }

    // Oil panel keyed off the active date.
    renderOil(OIL, date);

    // News panel keyed off the same active date (lockstep with the stepper).
    renderNews(date);

    // SAR scene overlay panel, same active date (lockstep with the stepper).
    renderScene(date);

    // Stepper UI sync.
    var sel = document.getElementById("ds-select");
    if (sel && sel.selectedIndex !== ACTIVE_IDX) sel.selectedIndex = ACTIVE_IDX;
    var slider = document.getElementById("ds-slider");
    if (slider && Number(slider.value) !== ACTIVE_IDX) slider.value = String(ACTIVE_IDX);
    var prev = document.getElementById("ds-prev");
    var next = document.getElementById("ds-next");
    if (prev) prev.disabled = (ACTIVE_IDX <= 0);
    if (next) next.disabled = (ACTIVE_IDX >= DATES.length - 1);
  }

  function stepDate(delta) { applyDate(ACTIVE_IDX + delta); }

  // ---- wire up the date stepper controls --------------------------------
  function initStepper() {
    var wrap = document.getElementById("date-stepper");
    if (!wrap) return;

    // Single date (or no real dates): hide the stepper entirely.
    var realDates = DATES.filter(function (d) { return !!d; });
    if (realDates.length <= 1) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;

    var sel = document.getElementById("ds-select");
    var slider = document.getElementById("ds-slider");
    if (sel) {
      sel.innerHTML = "";
      DATES.forEach(function (d, i) {
        var o = document.createElement("option");
        o.value = String(i);
        o.textContent = d;
        sel.appendChild(o);
      });
      sel.addEventListener("change", function () { applyDate(Number(sel.value)); });
    }
    if (slider) {
      slider.min = "0";
      slider.max = String(DATES.length - 1);
      slider.step = "1";
      slider.value = String(ACTIVE_IDX);
      slider.addEventListener("input", function () { applyDate(Number(slider.value)); });
    }
    var prev = document.getElementById("ds-prev");
    var next = document.getElementById("ds-next");
    if (prev) prev.addEventListener("click", function () { stepDate(-1); });
    if (next) next.addEventListener("click", function () { stepDate(1); });
  }

  // ---- render data ------------------------------------------------------
  function render(data) {
    DATA = data;
    var dets = Array.isArray(data.detections) ? data.detections : [];
    DATES = computeDates(data, dets);
    ACTIVE_IDX = 0;

    var p = data.persistence;
    TIMESTEPS = (p && typeof p.timesteps === "number" && p.timesteps > 0)
      ? p.timesteps
      : DATES.filter(function (d) { return !!d; }).length || 1;

    // (a) AOI footprint rectangle from data.bbox (JSON [lon,lat] order).
    var aoiBounds = null;
    if (Array.isArray(data.bbox) && data.bbox.length === 4) {
      aoiBounds = boundsFromBbox(data.bbox);
      L.rectangle(aoiBounds, {
        color: "#4ea8de",
        weight: 2,
        dashArray: "8 6",
        fill: false,
        interactive: true
      })
        .bindTooltip("AOI footprint", { sticky: true })
        .addTo(map);
    }

    // Legend / context overlay (static parts).
    var legend = document.getElementById("map-legend");
    var loc = data.location || {};
    document.getElementById("ml-region").textContent =
      loc.region || "Strait of Hormuz";

    // Multi-timestep summary line: "N timesteps · first → last".
    var summaryEl = document.getElementById("ml-summary");
    if (summaryEl) {
      var realDates = DATES.filter(function (d) { return !!d; });
      if (realDates.length > 1) {
        summaryEl.textContent =
          TIMESTEPS + " timesteps · " +
          realDates[0] + " → " + realDates[realDates.length - 1];
        summaryEl.hidden = false;
      } else {
        summaryEl.hidden = true;
      }
    }

    // Static toggle: only meaningful if the dataset actually marks anything
    // static. Default = shown (checkbox unchecked).
    var hasStatic = dets.some(isStatic);
    var toggleWrap = document.getElementById("ml-static-toggle");
    var toggle = document.getElementById("ds-hide-static");
    if (toggle) {
      toggle.checked = false;
      hideStatic = false;
      toggle.addEventListener("change", function () {
        hideStatic = toggle.checked;
        applyDate(ACTIVE_IDX);
      });
    }
    if (toggleWrap) toggleWrap.hidden = !hasStatic;

    // Build the stepper, then draw the first date.
    initStepper();
    applyDate(0);

    // Fit to AOI footprint on load (fall back to active-date detections).
    if (aoiBounds && aoiBounds.isValid()) {
      map.fitBounds(aoiBounds, { padding: [40, 40] });
    } else if (detBounds && detBounds.isValid()) {
      map.fitBounds(detBounds, { padding: [40, 40] });
    }

    if (legend) legend.hidden = false;

    // "Zoom to detections" control (uses current active-date bounds).
    var btn = document.getElementById("btn-zoom-det");
    if (btn) {
      btn.addEventListener("click", function () {
        if (detBounds && detBounds.isValid()) {
          map.fitBounds(detBounds, { padding: [40, 40] });
        }
      });
    }

    // Arrow-key Left/Right step through dates.
    document.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { stepDate(-1); }
      else if (e.key === "ArrowRight") { stepDate(1); }
    });
  }

  // ---- fetch data -------------------------------------------------------
  // Fetch oil first (best-effort) so the panel is ready when dates render.
  fetch("artifacts/oil.json", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (oil) {
      OIL = oil; // may be null; renderOil handles that gracefully
      // News is best-effort too: panel stays hidden if it fails.
      return fetch("data/news.json", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    })
    .then(function (news) {
      var items = (news && Array.isArray(news.items)) ? news.items.slice() : null;
      if (items) {
        // Keep ascending by date so renderNews can scan/slice deterministically.
        items.sort(function (a, b) {
          var da = (a && a.date) || "", db = (b && b.date) || "";
          return da < db ? -1 : (da > db ? 1 : 0);
        });
      }
      NEWS = items; // may be null; renderNews handles that gracefully
      return fetch("artifacts/detections.json", { cache: "no-store" });
    })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(render)
    .catch(function (e) {
      // Data failed: keep the map (basemap still useful) but tell the user.
      var legend = document.getElementById("map-legend");
      if (legend) {
        legend.hidden = false;
        document.getElementById("ml-region").textContent =
          "Could not load detections (" + e.message + ").";
      }
    });
})();
