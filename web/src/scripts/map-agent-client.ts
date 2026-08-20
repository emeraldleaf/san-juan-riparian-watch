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
  const PRODUCTS: Record<string, { color: string; opacity: number; files: string[] }> = {
    // Absolute paths: this page is served at /map/, so a RELATIVE 'maps/x' would
    // resolve to /map/maps/x and the box returns the SPA-fallback HTML (not the
    // GeoJSON) — MapLibre renders nothing and fitToProduct's fetch throws.
    rf: { color: '#16a34a', opacity: 0.5, files: ['/maps/present-extent-2020.geojson', '/maps/rf_malpais_full.geojson', '/maps/extent-bloomfield-rf.geojson'] },
    fm: { color: '#0891b2', opacity: 0.5, files: ['/maps/fm_bloomfield.geojson', '/maps/fm_malpais.geojson'] },
    invasive: { color: '#e11d48', opacity: 0.72, files: ['/maps/present-invasive-in-corridor.geojson'] },
  };
  const layerIds: Record<string, string[]> = { rf: [], fm: [], invasive: [] };

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
      });
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
        (layerIds[key] || []).forEach((id) =>
          map.setLayoutProperty(id, 'visibility', cb.checked ? 'visible' : 'none'));
        if (cb.checked) fitToProduct(key);
      });
    });
    ready = true;
  });

  // Draw the full river (context) with the analyzed reach highlighted, fit to the
  // whole river so you see its full in-AOI extent — not just the scored stretch.
  addEventListener('mapagent:geom', (e: any) => {
    if (!ready) return;
    const context = e.detail?.context;
    const highlight = e.detail?.highlight;
    (map.getSource('context') as any)?.setData(fc(context));
    (map.getSource('resolved') as any)?.setData(fc(highlight));
    try {
      const b = new maplibregl.LngLatBounds();
      eachCoord(context || highlight, (c) => b.extend(c as any));
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
