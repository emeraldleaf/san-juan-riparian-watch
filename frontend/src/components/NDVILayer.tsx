import { Source, Layer } from 'react-map-gl/maplibre';

const API_URL = import.meta.env.VITE_API_URL || window.location.origin;
// MVT endpoint for buffer centroids
const TILE_URL = `${API_URL}/api/tiles/centroids/{z}/{x}/{y}.pbf`;

/**
 * Renders an NDVI vegetation health heatmap overlay using MapLibre GL's native
 * heatmap layer backed by Vector Tiles (MVT).
 *
 * Buffer centroids are weighted by their mean_ndvi value to produce a red-to-green
 * gradient. This is a DENSITY surface, not a classified health map: `heatmap-weight`
 * is the raw NDVI, but `heatmap-color` interpolates over `heatmap-density` — a
 * normalized 0–1 kernel density — so the colour stops below are density stops and do
 * NOT correspond to NDVI health classes. Read the legend (or the classified buffer
 * fill) for health; read this layer for "where is the vigorous vegetation clustered".
 *
 * The canonical NDVI health thresholds live in `classify_health()` in
 * `ndvi_processor.py` — healthy >0.25 / degraded 0.10–0.25 / bare <0.10. This file
 * previously documented the retired >0.3 / 0.15 values, which is why they are
 * tombstoned (.claude/tombstones.txt): stale thresholds in a comment are how the
 * frontend and the model quietly disagree.
 *
 * The heatmap fades out at high zoom levels where individual buffer polygons
 * become visible.
 */
export default function NDVILayer() {
  return (
    <Source
      id="ndvi-centroids"
      type="vector"
      tiles={[TILE_URL]}
      minzoom={0}
      maxzoom={24}
    >
      <Layer
        id="ndvi-heatmap"
        type="heatmap"
        source-layer="centroids"
        paint={{
          // NDVI ranges -1..1, but heatmap weight must be >= 0 — clamp negatives
          // (water / bare soil) to 0 so they don't produce invalid negative weights.
          'heatmap-weight': ['max', 0, ['coalesce', ['get', 'mean_ndvi'], 0]],
          'heatmap-intensity': [
            'interpolate', ['linear'], ['zoom'],
            8, 1,
            15, 3,
          ],
          'heatmap-color': [
            'interpolate', ['linear'], ['heatmap-density'],
            // Stops are heatmap-DENSITY (0–1), not NDVI. Do not relabel them as health
            // classes — that mislabelling is what put retired NDVI thresholds in this file.
            0, 'rgba(0,0,0,0)',
            0.15, '#d73027',  // sparse cluster
            0.3, '#fc8d59',
            0.5, '#fee08b',
            0.7, '#91cf60',
            1, '#1a9850',     // dense cluster of high-NDVI centroids
          ],
          'heatmap-radius': [
            'interpolate', ['linear'], ['zoom'],
            8, 15,
            15, 30,
          ],
          'heatmap-opacity': [
            'interpolate', ['linear'], ['zoom'],
            12, 0.8,
            16, 0.2,
          ],
        }}
      />
    </Source>
  );
}
