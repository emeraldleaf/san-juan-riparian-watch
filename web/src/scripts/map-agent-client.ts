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

  map.on('load', () => {
    map.addSource('resolved', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: 'resolved-fill', type: 'fill', source: 'resolved',
      filter: ['==', '$type', 'Polygon'],
      paint: { 'fill-color': '#2563eb', 'fill-opacity': 0.22, 'fill-outline-color': '#1d4ed8' },
    });
    map.addLayer({
      id: 'resolved-line', type: 'line', source: 'resolved',
      paint: { 'line-color': '#2563eb', 'line-width': 3 },
    });
    ready = true;
  });

  // Move + highlight the map to a resolved geometry.
  addEventListener('mapagent:geom', (e: any) => {
    const geom = e.detail?.geometry;
    if (!geom || !ready) return;
    const fc = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: geom, properties: {} }] };
    (map.getSource('resolved') as any)?.setData(fc);
    try {
      const b = new maplibregl.LngLatBounds();
      eachCoord(geom, (c) => b.extend(c as any));
      if (!b.isEmpty()) map.fitBounds(b, { padding: 70, maxZoom: 13, duration: 800 });
    } catch { /* geometry with no coords — leave the view */ }
  });

  // Clear the highlight when the agent resolved nothing (refusal / out of scope).
  addEventListener('mapagent:clear', () => {
    if (ready) (map.getSource('resolved') as any)?.setData({ type: 'FeatureCollection', features: [] });
  });
}
