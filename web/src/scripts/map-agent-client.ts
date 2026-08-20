// The "ask the map" page's MapLibre map. The MapAgent React island posts questions
// to /agent/map and hands the resolved geometry back through a window CustomEvent;
// this imperative half owns the map (maps are imperative, like the story maps).
import maplibregl from 'maplibre-gl';

const SAT: any = {
  version: 8,
  sources: {
    sat: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [{ id: 'sat', type: 'raster', source: 'sat' }],
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

  map.on('load', () => {
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
}
