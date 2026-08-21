// Imperative story behaviours bundled by Astro: theme toggle, scroll reveal,
// reading-progress bar, KPI count-up, and the three MapLibre maps. Canvas/map
// widgets are inherently imperative, so they live here rather than in React.
// The agent (a React island) talks to the maps through window CustomEvents.
import maplibregl from 'maplibre-gl';
import { webglSupported, mapFallback } from './webgl';

const root = document.documentElement;
root.classList.add('js-reveal');
// The theme toggle (#tog) is wired + persisted by the shared script in Base.astro.

const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: 0.1 });
document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

const prog = document.getElementById('progress');
const onScroll = () => { const h = document.documentElement, max = h.scrollHeight - h.clientHeight; if (prog) prog.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%'; };
addEventListener('scroll', onScroll, { passive: true }); onScroll();

function countUp(el: HTMLElement, dur: number) {
  const final = el.textContent || '';
  // Grouping commas would be split into separate numeric runs and animate to
  // nonsense (1,700 → "0,315"); leave any such value static.
  if (final.indexOf(',') >= 0) return;
  const tokens = final.match(/[0-9]*\.?[0-9]+|[^0-9]+/g) || [final];
  let start: number | null = null;
  const fr = (ts: number) => {
    if (start === null) start = ts;
    const p = Math.min(1, (ts - start) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = tokens.map((t) => { if (/^[0-9]*\.?[0-9]+$/.test(t)) { const d = (t.split('.')[1] || '').length; return (parseFloat(t) * e).toFixed(d); } return t; }).join('');
    if (p < 1) requestAnimationFrame(fr); else el.textContent = final;
  };
  requestAnimationFrame(fr);
}
if (!matchMedia('(prefers-reduced-motion:reduce)').matches) {
  document.querySelectorAll<HTMLElement>('.kpi .n').forEach((el, i) => setTimeout(() => countUp(el, 900), 120 + i * 90));
}

const SAT: any = { version: 8, sources: { sat: { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' } }, layers: [{ id: 'sat', type: 'raster', source: 'sat' }] };
function eachCoord(geom: any, cb: (c: number[]) => void) {
  if (!geom) return;
  if (geom.type === 'GeometryCollection') { (geom.geometries || []).forEach((g: any) => eachCoord(g, cb)); return; }
  if (!geom.coordinates) return;
  (function walk(a: any) { if (typeof a[0] === 'number') { cb(a); return; } a.forEach(walk); })(geom.coordinates);
}
const MAPS: Record<string, { map: any; bbox: any; ready: boolean }> = {};

// ---- corridor ----
(function () {
  const status = document.getElementById('status-corridor');
  const container = document.getElementById('map-corridor');
  if (!container) return;
  if (!webglSupported()) { mapFallback(container); return; }
  const map = new maplibregl.Map({ container, center: [-108.26, 36.745], zoom: 11.4, style: SAT, cooperativeGestures: true });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }));
  const BBOX: any = [[-108.33, 36.7], [-108.19, 36.79]];
  MAPS.corridor = { map, bbox: BBOX, ready: false };
  map.on('error', (e: any) => { if (status) status.textContent = 'map error: ' + (e.error && e.error.message); });
  map.on('load', () => {
    map.addSource('corridor', { type: 'geojson', data: 'maps/present-extent-2020.geojson' });
    map.addLayer({ id: 'corridor', type: 'fill', source: 'corridor', paint: { 'fill-color': '#16a34a', 'fill-opacity': 0.42 } });
    map.addSource('invasive', { type: 'geojson', data: 'maps/present-invasive-in-corridor.geojson' });
    map.addLayer({ id: 'invasive', type: 'fill', source: 'invasive', paint: { 'fill-color': '#e11d48', 'fill-opacity': 0.82, 'fill-outline-color': '#7f1d3a' } });
    map.addSource('askhi', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'askhi', type: 'line', source: 'askhi', paint: { 'line-color': '#2563eb', 'line-width': 3 } });
    map.fitBounds(BBOX, { padding: 22, duration: 0 }); MAPS.corridor.ready = true;
    map.on('idle', () => { if (status && status.textContent === 'loading…') status.textContent = 'corridor 7.6 km² · invasive 1.7 km² (23%)'; });
  });
})();

// ---- arroyo: RF vs FM vs NMRipMap truth over the held-out reach ----
(function () {
  const status = document.getElementById('status-arroyo');
  const container = document.getElementById('map-arroyo');
  if (!container) return;
  if (!webglSupported()) { mapFallback(container); return; }
  const map = new maplibregl.Map({ container, center: [-108.76, 36.85], zoom: 11.7, style: SAT, cooperativeGestures: true });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }));
  const BBOX: any = [[-108.82, 36.806], [-108.696, 36.893]];
  MAPS.arroyo = { map, bbox: BBOX, ready: false };
  map.on('error', (e: any) => { if (status) status.textContent = 'map error: ' + (e.error && e.error.message); });
  map.on('load', () => {
    // Fills first, then the NMRipMap truth outline on top — otherwise the opaque
    // RF fill hides the boundaries the map is meant to let you compare against.
    map.addSource('a-fm', { type: 'geojson', data: 'maps/fm_malpais.geojson' });
    map.addLayer({ id: 'a-fm', type: 'fill', source: 'a-fm', paint: { 'fill-color': '#16a34a', 'fill-opacity': 0.45 } });
    map.addSource('a-rf', { type: 'geojson', data: 'maps/reach-malpais-rf.geojson' });
    map.addLayer({ id: 'a-rf', type: 'fill', source: 'a-rf', paint: { 'fill-color': '#f97316', 'fill-opacity': 0.9, 'fill-outline-color': '#7c2d12' } });
    map.addSource('a-truth', { type: 'geojson', data: 'maps/truth_malpais.geojson' });
    map.addLayer({ id: 'a-truth', type: 'line', source: 'a-truth', paint: { 'line-color': '#e2e8f0', 'line-width': 1.1, 'line-opacity': 0.85 } });
    map.fitBounds(BBOX, { padding: 20, duration: 0 }); MAPS.arroyo.ready = true;
    map.on('idle', () => { if (status && status.textContent === 'loading…') status.textContent = 'RF barely fires · FM tracks the corridor'; });
  });
})();

// ---- time slider: invasive over the epochs ----
(function () {
  const YEARS = ['1990', '2000', '2010', '2020'];
  const CONF: Record<string, { c: string; t: string; warn: boolean }> = {
    '1990': { c: 'warn', t: 'not robust · recipe-dependent', warn: true },
    '2000': { c: 'mid', t: 'stable window (edge)', warn: false },
    '2010': { c: 'mid', t: 'stable window', warn: false },
    '2020': { c: 'ok', t: 'present-day · calibrated', warn: false },
  };
  const cache: Record<string, any> = {}; let ready = false;
  const yearEl = document.getElementById('tyear'), confEl = document.getElementById('tconf'),
    warnEl = document.getElementById('twarn') as HTMLElement | null, slider = document.getElementById('yr') as HTMLInputElement | null,
    ticks = document.querySelectorAll('.tticks span'), status = document.getElementById('status-time');
  const container = document.getElementById('map-time');
  if (!container) return;
  if (!webglSupported()) { mapFallback(container); return; }
  const map = new maplibregl.Map({ container, center: [-108.26, 36.745], zoom: 11.4, style: SAT, cooperativeGestures: true });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }));
  const BBOX: any = [[-108.33, 36.7], [-108.19, 36.79]];
  function setEpoch(idx: number) {
    const y = YEARS[idx], cf = CONF[y];
    if (yearEl) yearEl.textContent = y;
    if (confEl) { confEl.textContent = cf.t; confEl.className = 'cf ' + cf.c; }
    if (warnEl) warnEl.hidden = !cf.warn;
    ticks.forEach((s, k) => s.classList.toggle('on', k === idx));
    if (!ready) return;
    const apply = (gj: any) => { const src = map.getSource('epoch') as any; if (src) src.setData(gj); };
    if (cache[y]) { apply(cache[y]); if (status) status.textContent = ''; return; }
    if (status) status.textContent = 'loading ' + y + ' composite…';
    fetch('maps/deep-invasive-' + y + '.geojson').then((r) => r.json()).then((gj) => {
      cache[y] = gj;
      // A slower earlier request must not overwrite a newer selection: only
      // apply if this year is still the one the slider points at.
      if (YEARS[parseInt(slider?.value || '3', 10)] !== y) return;
      apply(gj); if (status) status.textContent = '';
    }).catch(() => { if (YEARS[parseInt(slider?.value || '3', 10)] === y && status) status.textContent = 'could not load ' + y; });
  }
  map.on('load', () => {
    map.addSource('t-corridor', { type: 'geojson', data: 'maps/present-extent-2020.geojson' });
    map.addLayer({ id: 't-corridor', type: 'line', source: 't-corridor', paint: { 'line-color': '#16a34a', 'line-width': 1.3, 'line-opacity': 0.9 } });
    map.addSource('epoch', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'epoch', type: 'fill', source: 'epoch', paint: { 'fill-color': '#e11d48', 'fill-opacity': 0.72, 'fill-outline-color': '#7f1d3a' } });
    map.fitBounds(BBOX, { padding: 22, duration: 0 }); ready = true; setEpoch(parseInt(slider?.value || '3', 10));
  });
  slider?.addEventListener('input', () => setEpoch(parseInt(slider.value, 10)));
  ticks.forEach((s, k) => s.addEventListener('click', () => { if (slider) slider.value = String(k); setEpoch(k); }));
  setEpoch(slider ? parseInt(slider.value, 10) : 3);
})();

// legend layer toggles
document.querySelectorAll<HTMLElement>('.maplegend .row[data-layer]').forEach((row) => {
  row.addEventListener('click', () => {
    const m = MAPS[row.dataset.map || '']; if (!m || !m.map.getLayer(row.dataset.layer)) return;
    const id = row.dataset.layer as string, vis = m.map.getLayoutProperty(id, 'visibility') === 'none' ? 'visible' : 'none';
    m.map.setLayoutProperty(id, 'visibility', vis);
    row.classList.toggle('off', vis === 'none'); row.setAttribute('aria-pressed', String(vis === 'visible'));
  });
});

// ---- bridge from the agent island ----
function focusMap(which: string) {
  const m = MAPS[which]; if (!m || !m.ready) return;
  const wrap = document.getElementById('wrap-' + which);
  m.map.fitBounds(m.bbox, { padding: 24, duration: 700 });
  if (wrap) { wrap.classList.add('pulse'); setTimeout(() => wrap.classList.remove('pulse'), 1600); }
}
function showGeom(features: any[]) {
  const m = MAPS.corridor; if (!m || !m.ready || !m.map.getSource('askhi')) return;
  (m.map.getSource('askhi') as any).setData({ type: 'FeatureCollection', features });
  try { const b = new maplibregl.LngLatBounds(); features.forEach((f) => eachCoord(f.geometry, (c) => b.extend(c as any))); if (!b.isEmpty()) m.map.fitBounds(b, { padding: 60, maxZoom: 13, duration: 600 }); } catch {}
}
addEventListener('story:answer', (e: any) => {
  const t = (e.detail?.text || '').toLowerCase();
  if (/malpais|arroyo/.test(t)) focusMap('arroyo');
  else if (/farmington|corridor|invasive|23\s*%/.test(t)) focusMap('corridor');
});
addEventListener('story:geom', (e: any) => { const f = e.detail?.features; if (f && f.length) showGeom(f); });

// Contextual "ask the agent" chips ([data-ask="…"]) placed in any section → hand
// the question to the Chat island, which scrolls itself into view and asks it.
document.addEventListener('click', (e) => {
  const el = (e.target as HTMLElement | null)?.closest('[data-ask]');
  const q = el?.getAttribute('data-ask');
  if (q) dispatchEvent(new CustomEvent('story:ask', { detail: { q } }));
});
