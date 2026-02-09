import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';

interface NDVILayerProps {
  /** Heat points as [lat, lng, intensity] where intensity is 0–1 (NDVI scale). */
  points: Array<[number, number, number]>;
}

/**
 * Renders an NDVI vegetation health heatmap overlay on the Leaflet map.
 *
 * Uses leaflet.heat to display buffer-centroid heat points with a
 * red-to-green gradient matching NDVI health thresholds:
 *   bare (<0.3) → degraded (0.3–0.6) → healthy (>0.6)
 */
export default function NDVILayer({ points }: NDVILayerProps) {
  const map = useMap();

  useEffect(() => {
    if (points.length === 0) return;

    const heat = L.heatLayer(points, {
      radius: 25,
      blur: 15,
      maxZoom: 17,
      max: 1,
      gradient: {
        0: '#d73027', // bare / unhealthy
        0.3: '#fc8d59', // degraded
        0.6: '#91cf60', // moderate
        1: '#1a9850', // healthy
      },
    });

    heat.addTo(map);
    return () => { map.removeLayer(heat); };
  }, [map, points]);

  return null;
}
