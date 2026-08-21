// The "ask the map" page's MapLibre map. The MapAgent React island posts questions
// to /agent/map and hands the resolved geometry back through a window CustomEvent;
// this imperative half owns the map (maps are imperative, like the story maps).
import maplibregl from 'maplibre-gl';

// Satellite imagery + Esri reference overlays (transparent): roads/highways and
// place names / boundaries, so the map orients you to the region — towns, roads,
// and labeled rivers — not just bare pixels.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
const SAT: any = {
  version: 8,
  sources: {
    sat: { type: 'raster', tiles: [`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' },
    roads: { type: 'raster', tiles: [`${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, attribution: '© Esri' },
    places: { type: 'raster', tiles: [`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, attribution: '© Esri' },
  },
  layers: [
    { id: 'sat', type: 'raster', source: 'sat' },
    { id: 'roads', type: 'raster', source: 'roads' },
    { id: 'places', type: 'raster', source: 'places' },
  ],
};

function eachCoord(geom: any, cb: (c: number[]) => void) {
  if (!geom) return;
  if (geom.type === 'GeometryCollection') { (geom.geometries || []).forEach((g: any) => eachCoord(g, cb)); return; }
  if (!geom.coordinates) return;
  (function walk(a: any) { if (typeof a[0] === 'number') { cb(a); return; } a.forEach(walk); })(geom.coordinates);
}

const container = document.getElementById('map-agent-map');
if (container) {
  const map = new maplibregl.Map({ container, center: [-108.2, 36.85], zoom: 8.2, style: SAT, cooperativeGestures: true });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }));
  let ready = false;

  const fc = (g: any) => ({ type: 'FeatureCollection', features: g ? [{ type: 'Feature', geometry: g, properties: {} }] : [] });

  // The mapped model products — already materialized as served GeoJSON. Toggled by
  // the legend checkboxes. Each product is one or more files (different reaches).
  const PRODUCTS: Record<string, { color: string; opacity: number; files: string[]; outline?: string }> = {
    // Absolute paths: this page is served at /map/, so a RELATIVE 'maps/x' would
    // resolve to /map/maps/x and the box returns the SPA-fallback HTML (not the
    // GeoJSON) — MapLibre renders nothing and fitToProduct's fetch throws.
    rf: { color: '#16a34a', opacity: 0.5, files: ['/maps/present-extent-2020.geojson', '/maps/rf_malpais_full.geojson', '/maps/extent-bloomfield-rf.geojson'] },
    fm: { color: '#0891b2', opacity: 0.5, files: ['/maps/fm_bloomfield.geojson', '/maps/fm_malpais.geojson'] },
    invasive: { color: '#e11d48', opacity: 0.72, files: ['/maps/present-invasive-in-corridor.geojson'] },
    // NMRipMap expert truth for the Malpais reach (grey + white outline) — so you
    // can see where the ground truth actually is vs RF/FM.
    truth: { color: '#cbd5e1', opacity: 0.4, files: ['/maps/truth_malpais.geojson'], outline: '#f8fafc' },
  };
  const layerIds: Record<string, string[]> = { rf: [], fm: [], invasive: [], truth: [], bbox: [] };

  // The DEFINED Malpais reach bbox (validate_reach.py) vs the ACTUAL imaged window
  // coverage — a dashed outline each, so the un-imaged northern strip is visible.
  const BBOX_DEFINED = [-108.8217, 36.8096, -108.6729, 36.9508];
  const BBOX_COVERED = [-108.8239, 36.8071, -108.6962, 36.8930];
  const rect = (b: number[]) => ({ type: 'Feature' as const, properties: {}, geometry: {
    type: 'Polygon' as const, coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] } });

  // Fit the map to a product's extent (lazy-fetched, cached) so toggling a layer
  // ON also zooms you to where it has data.
  const productBounds: Record<string, maplibregl.LngLatBounds | null> = {};
  async function fitToProduct(key: string) {
    if (!(key in productBounds)) {
      const b = new maplibregl.LngLatBounds();
      for (const file of PRODUCTS[key]?.files || []) {
        try {
          const gj = await (await fetch(file)).json();
          (gj.features || []).forEach((f: any) => eachCoord(f.geometry, (c) => b.extend(c as any)));
        } catch { /* skip a missing file */ }
      }
      productBounds[key] = b.isEmpty() ? null : b;
    }
    const bb = productBounds[key];
    if (bb) map.fitBounds(bb, { padding: 60, maxZoom: 13, duration: 800 });
  }

  // ── Agent-narrated map presentation ──────────────────────────────────────
  // A keynote where the slides ARE the map: each scene sets the camera + which
  // layers are visible; the agent narrates in the panel. Presentation layers are
  // reach-SPECIFIC files (only the Malpais/corridor stretch), separate from the
  // legend's whole-product toggles.
  // Two San Juan reaches, kept honestly distinct:
  //  • reach A (truth) — the phenology reach (truth + imagery co-located here).
  //  • Bloomfield (b*) — the ONE reach with expert truth + RF + FM genuinely
  //    co-located, so the RF-vs-FM head-to-head is like-for-like (not a conflation
  //    of two different reaches, which the old rf_malpais/fm_malpais pairing was).
  // Truth reads as hand-drawn delineation: fill + a crisp white outline.
  const PRES_LAYERS: Record<string, { file: string; color: string; opacity: number; outline?: string }> = {
    truth: { file: '/maps/truth_malpais.geojson', color: '#cbd5e1', opacity: 0.45, outline: '#f8fafc' },
    btruth: { file: '/maps/nmripmap-bloomfield.geojson', color: '#cbd5e1', opacity: 0.45, outline: '#f8fafc' },
    brf: { file: '/maps/extent-bloomfield-rf.geojson', color: '#16a34a', opacity: 0.5 },
    bfm: { file: '/maps/fm_bloomfield.geojson', color: '#0891b2', opacity: 0.5 },
    invasive: { file: '/maps/present-invasive-in-corridor.geojson', color: '#e11d48', opacity: 0.72 },
  };
  const presBounds: Record<string, maplibregl.LngLatBounds | null> = {};
  async function fitToPres(key: string, opts: { pitch?: number } = {}) {
    if (!(key in presBounds)) {
      const b = new maplibregl.LngLatBounds();
      try {
        const gj = await (await fetch(PRES_LAYERS[key].file)).json();
        (gj.features || []).forEach((f: any) => eachCoord(f.geometry, (c) => b.extend(c as any)));
      } catch { /* missing file */ }
      presBounds[key] = b.isEmpty() ? null : b;
    }
    const bb = presBounds[key];
    if (bb) map.fitBounds(bb, { padding: 70, maxZoom: 14, pitch: opts.pitch ?? 0, duration: 1400 });
  }

  type Scene = { narration: string; layers: string[]; fit: string; stub?: boolean; pitch?: number; phenology?: boolean };
  const PRESENTATION: { title: string; scenes: Scene[] } = {
    title: 'How we found the riparian',
    scenes: [
      { narration: "A reach on the San Juan River, in New Mexico's high desert. A thin ribbon of riparian vegetation follows the water through otherwise dry country — and our job is to map it from space, then tell native from invasive.", layers: [], fit: 'truth', pitch: 35 },
      { narration: "The hard part: from a single summer image, riparian and an irrigated field look identical — both are just green. One snapshot can't separate them.", layers: [], fit: 'truth' },
      { narration: "So we don't use one image — we stack twelve monthly composites and read the season. Here's a year over this reach in color-infrared, where vegetation glows red. Watch the corridor and the fields pulse as the seasons turn; cottonwood and invasive tamarisk green up and drop at different times, and that seasonal fingerprint is what separates riparian from bare desert. Drag the slider to scrub the months.", layers: [], fit: 'truth', phenology: true },
      { narration: "To judge a model you need expert ground truth AND the model on the very same reach. Here's a San Juan reach near Bloomfield where we have both — this grey layer is the riparian hand-drawn by experts in 2020.", layers: ['btruth'], fit: 'btruth' },
      { narration: "The Random Forest learns the seasonal fingerprint and predicts riparian — in green, over the grey truth. It does well on the river corridors it was trained across.", layers: ['btruth', 'brf'], fit: 'brf' },
      { narration: "Ai2's OlmoEarth — a fine-tuned foundation model — predicts the same reach with spatial context (teal): it reads the surrounding shape of the land, not just each pixel. Here you can eyeball where the two models and the expert truth agree and differ along the corridor. (A rigorous scored comparison lives in a separate leave-one-reach-out evaluation, kept out of this map while we re-verify how each test reach is labeled.)", layers: ['btruth', 'bfm'], fit: 'bfm' },
      { narration: "And the invasive share — tamarisk and Russian olive — here in the Farmington corridor. One honest caveat: the model over-counts green farmland near the banks, so read these as model estimates, not ground truth.", layers: ['invasive'], fit: 'invasive' },
    ],
  };

  // 12-month phenology imagery (color-infrared monthly composites over Malpais),
  // materialized from the reach cube. The slider scene cross-fades through them.
  const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const PHENO: { bounds: any; months: string[]; loaded: boolean } = { bounds: null, months: [], loaded: false };
  let phenoMonth = 0;
  let phenoTimer: ReturnType<typeof setInterval> | null = null;
  async function loadPhenology() {
    try {
      const m = await (await fetch('/maps/phenology/malpais.json')).json();
      PHENO.bounds = m.bounds; PHENO.months = m.months; PHENO.loaded = true;
      const { w, s, e, n } = m.bounds;
      map.addSource('phenology', { type: 'image', url: `/maps/phenology/${m.months[0]}`,
        coordinates: [[w, n], [e, n], [e, s], [w, s]] });
      map.addLayer({ id: 'phenology-lyr', type: 'raster', source: 'phenology',
        layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.95, 'raster-fade-duration': 250 } });
    } catch { /* imagery not present — the scene falls back to a caption */ }
  }
  function setPhenoMonth(i: number) {
    if (!PHENO.loaded) return;
    phenoMonth = ((i % 12) + 12) % 12;
    (map.getSource('phenology') as any)?.updateImage({ url: `/maps/phenology/${PHENO.months[phenoMonth]}` });
    dispatchEvent(new CustomEvent('pres:month', { detail: { index: phenoMonth, label: MONTH_LABELS[phenoMonth] } }));
  }
  function startPheno() {
    if (!PHENO.loaded) return;
    map.setLayoutProperty('phenology-lyr', 'visibility', 'visible');
    const { w, s, e, n } = PHENO.bounds;
    map.fitBounds([[w, s], [e, n]], { padding: 30, duration: 1200, pitch: 0 });
    setPhenoMonth(0);
    if (phenoTimer) clearInterval(phenoTimer);
    phenoTimer = setInterval(() => setPhenoMonth(phenoMonth + 1), 950);
  }
  function stopPheno() {
    if (phenoTimer) { clearInterval(phenoTimer); phenoTimer = null; }
    if (PHENO.loaded) map.setLayoutProperty('phenology-lyr', 'visibility', 'none');
  }
  addEventListener('pres:setmonth', (e: any) => {
    if (phenoTimer) { clearInterval(phenoTimer); phenoTimer = null; }  // scrubbing takes over
    setPhenoMonth(e.detail?.index ?? 0);
  });

  let presIndex = -1;
  let presPlaying = false;
  let presTimer: ReturnType<typeof setTimeout> | null = null;
  const SCENE_DWELL = 11000;

  function showPresLayers(active: string[]) {
    Object.entries(PRES_LAYERS).forEach(([k, p]) => {
      const vis = active.includes(k) ? 'visible' : 'none';
      map.setLayoutProperty(`pres-lyr-${k}`, 'visibility', vis);
      if (p.outline) map.setLayoutProperty(`pres-out-${k}`, 'visibility', vis);
    });
  }
  function clearAgentGeom() {
    (map.getSource('context') as any)?.setData(fc(null));
    (map.getSource('resolved') as any)?.setData(fc(null));
  }
  function emitScene() {
    const s = PRESENTATION.scenes[presIndex];
    dispatchEvent(new CustomEvent('pres:scene', { detail: {
      index: presIndex, total: PRESENTATION.scenes.length, title: PRESENTATION.title,
      narration: s.narration, stub: !!s.stub, phenology: !!s.phenology, playing: presPlaying,
    } }));
  }
  function goToScene(i: number) {
    if (!ready || i < 0 || i >= PRESENTATION.scenes.length) return;
    presIndex = i;
    const s = PRESENTATION.scenes[i];
    clearAgentGeom();
    stopPheno();
    showPresLayers(s.layers);
    if (s.phenology) startPheno();
    else fitToPres(s.fit, { pitch: s.pitch });
    emitScene();
    if (presPlaying) scheduleAdvance();
  }
  function scheduleAdvance() {
    if (presTimer) clearTimeout(presTimer);
    presTimer = setTimeout(() => {
      if (presIndex < PRESENTATION.scenes.length - 1) goToScene(presIndex + 1);
      else endPres();
    }, SCENE_DWELL);
  }
  function setPlaying(p: boolean) {
    presPlaying = p;
    if (presTimer) { clearTimeout(presTimer); presTimer = null; }
    if (p) scheduleAdvance();
    dispatchEvent(new CustomEvent('pres:state', { detail: { playing: presPlaying } }));
  }
  function endPres() {
    presPlaying = false;
    if (presTimer) { clearTimeout(presTimer); presTimer = null; }
    presIndex = -1;
    stopPheno();
    showPresLayers([]);
    map.easeTo({ pitch: 0, duration: 600 });
    dispatchEvent(new CustomEvent('pres:end'));
  }

  addEventListener('pres:start', () => { if (ready) { presPlaying = true; goToScene(0); } });
  addEventListener('pres:play', () => setPlaying(true));
  addEventListener('pres:pause', () => setPlaying(false));
  addEventListener('pres:next', () => { if (presIndex < PRESENTATION.scenes.length - 1) goToScene(presIndex + 1); else endPres(); });
  addEventListener('pres:prev', () => goToScene(presIndex - 1));
  addEventListener('pres:exit', () => endPres());

  map.on('load', () => {
    // Product fills go on first (under the river lines). Hidden until toggled.
    for (const [key, p] of Object.entries(PRODUCTS)) {
      p.files.forEach((file, i) => {
        const id = `prod-${key}-${i}`;
        map.addSource(id, { type: 'geojson', data: file });
        map.addLayer({
          id, type: 'fill', source: id,
          layout: { visibility: 'none' },
          paint: { 'fill-color': p.color, 'fill-opacity': p.opacity, 'fill-outline-color': p.color },
        });
        layerIds[key].push(id);
        if (p.outline) {
          const oid = `prod-out-${key}-${i}`;
          map.addLayer({ id: oid, type: 'line', source: id, layout: { visibility: 'none' },
            paint: { 'line-color': p.outline, 'line-width': 1.3, 'line-opacity': 0.9 } });
          layerIds[key].push(oid);
        }
      });
    }

    // Experiment bbox outlines: the DEFINED Malpais reach (red) vs the ACTUAL
    // imaged window coverage (amber). The gap between them is the un-imaged strip.
    map.addSource('bbox-defined', { type: 'geojson', data: rect(BBOX_DEFINED) });
    map.addLayer({ id: 'bbox-defined', type: 'line', source: 'bbox-defined', layout: { visibility: 'none' },
      paint: { 'line-color': '#e11d48', 'line-width': 2, 'line-dasharray': [3, 2] } });
    map.addSource('bbox-covered', { type: 'geojson', data: rect(BBOX_COVERED) });
    map.addLayer({ id: 'bbox-covered', type: 'line', source: 'bbox-covered', layout: { visibility: 'none' },
      paint: { 'line-color': '#f59e0b', 'line-width': 2, 'line-dasharray': [3, 2] } });
    layerIds['bbox'].push('bbox-defined', 'bbox-covered');

    // Presentation layers — reach-specific, hidden until a scene shows them.
    for (const [key, p] of Object.entries(PRES_LAYERS)) {
      map.addSource(`pres-src-${key}`, { type: 'geojson', data: p.file });
      map.addLayer({
        id: `pres-lyr-${key}`, type: 'fill', source: `pres-src-${key}`,
        layout: { visibility: 'none' },
        paint: { 'fill-color': p.color, 'fill-opacity': p.opacity, 'fill-outline-color': p.color },
      });
      if (p.outline) {
        map.addLayer({
          id: `pres-out-${key}`, type: 'line', source: `pres-src-${key}`,
          layout: { visibility: 'none' },
          paint: { 'line-color': p.outline, 'line-width': 1.3, 'line-opacity': 0.9 },
        });
      }
    }

    // context = the full in-AOI river (faint, underneath); resolved = the analyzed
    // reach we actually have a metric for (bold, on top).
    map.addSource('context', { type: 'geojson', data: fc(null) });
    map.addLayer({
      id: 'context-line', type: 'line', source: 'context',
      paint: { 'line-color': '#93c5fd', 'line-width': 2, 'line-opacity': 0.75 },
    });
    map.addSource('resolved', { type: 'geojson', data: fc(null) });
    map.addLayer({
      id: 'resolved-fill', type: 'fill', source: 'resolved',
      filter: ['==', '$type', 'Polygon'],
      paint: { 'fill-color': '#2563eb', 'fill-opacity': 0.22, 'fill-outline-color': '#1d4ed8' },
    });
    map.addLayer({
      id: 'resolved-line', type: 'line', source: 'resolved',
      paint: { 'line-color': '#2563eb', 'line-width': 4 },
    });

    // Legend checkboxes (data-product="rf|fm|invasive") toggle each product's layers.
    document.querySelectorAll<HTMLInputElement>('[data-product]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const key = cb.dataset.product || '';
        // Model layers only show/hide (compare in place). The truth/bbox inspection
        // layers DO fly to the Malpais reach on enable — you're trying to find them.
        (layerIds[key] || []).forEach((id) =>
          map.setLayoutProperty(id, 'visibility', cb.checked ? 'visible' : 'none'));
        if (cb.checked && (key === 'truth' || key === 'bbox')) {
          const b = BBOX_DEFINED;
          map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, duration: 900 });
        }
      });
    });
    loadPhenology();
    ready = true;
  });

  // Draw the full river (context) faint for orientation, with the riparian area
  // highlighted — but fit to the HIGHLIGHT (the riparian polygons / mapped reaches),
  // not the full mainstem centerline, so the map lands on what the answer is about.
  addEventListener('mapagent:geom', (e: any) => {
    if (!ready) return;
    const context = e.detail?.context;
    const highlight = e.detail?.highlight;
    (map.getSource('context') as any)?.setData(fc(context));
    (map.getSource('resolved') as any)?.setData(fc(highlight));
    try {
      const b = new maplibregl.LngLatBounds();
      eachCoord(highlight || context, (c) => b.extend(c as any));
      if (!b.isEmpty()) map.fitBounds(b, { padding: 70, maxZoom: 12, duration: 800 });
    } catch { /* geometry with no coords — leave the view */ }
  });

  // Clear both layers when the agent resolved nothing (refusal / out of scope).
  addEventListener('mapagent:clear', () => {
    if (!ready) return;
    (map.getSource('context') as any)?.setData(fc(null));
    (map.getSource('resolved') as any)?.setData(fc(null));
  });

  // The agent drives the overlays too: toggle a product's layers and sync its
  // legend checkbox, so "show me the invasive extent" flips the same switch.
  addEventListener('mapagent:layer', (e: any) => {
    const key = e.detail?.layer;
    const visible = e.detail?.visible !== false;
    const ids = layerIds[key];
    if (!ids || !ready) return;
    ids.forEach((id) => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none'));
    const cb = document.querySelector<HTMLInputElement>(`[data-product="${key}"]`);
    if (cb) cb.checked = visible;
    if (visible) fitToProduct(key);
  });
}
