import { Source, Layer } from 'react-map-gl/maplibre';

const API_URL = import.meta.env.VITE_API_URL || window.location.origin;
// MVT endpoint for buffer centroids
const TILE_URL = `${API_URL}/api/tiles/centroids/{z}/{x}/{y}.pbf`;

/**
 * Renders an NDVI vegetation health heatmap overlay using MapLibre GL's native
 * heatmap layer backed by Vector Tiles (MVT).
 *
 * Buffer centroids are weighted by their mean_ndvi value to produce a red-to-green
 * gradient matching NDVI health thresholds:
 *   bare (<0.15) → degraded (0.15–0.3) → healthy (>0.3)
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
          'heatmap-weight': ['coalesce', ['get', 'mean_ndvi'], 0],
          'heatmap-intensity': [
            'interpolate', ['linear'], ['zoom'],
            8, 1,
            15, 3,
          ],
          'heatmap-color': [
            'interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(0,0,0,0)',
            0.15, '#d73027',  // bare / unhealthy
            0.3, '#fc8d59',   // degraded
            0.5, '#fee08b',   // moderate
            0.7, '#91cf60',   // recovering
            1, '#1a9850',     // healthy
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
