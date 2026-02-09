import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet';
import type { FeatureCollection, Feature } from 'geojson';
import type { Layer, PathOptions } from 'leaflet';
import NDVILayer from './components/NDVILayer';
import 'leaflet/dist/leaflet.css';

const API_URL = import.meta.env.VITE_API_URL ?? '';

// Unique session ID for this browser tab — sent with every API call for telemetry correlation.
const SESSION_ID = crypto.randomUUID();

// San Juan Basin center (HUC8 14080101)
const MAP_CENTER: [number, number] = [37.3, -107.8];
const DEFAULT_ZOOM = 10;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ComplianceSummary {
  id: number;
  watershedId: number;
  huc8: string;
  totalParcels: number;
  compliantParcels: number;
  focusAreaParcels: number;
  compliancePct: number | null;
  avgNdvi: number | null;
  healthyBufferPct: number | null;
  degradedBufferPct: number | null;
  bareBufferPct: number | null;
}

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { 'X-Session-Id': SESSION_ID },
  });

  const correlationId = res.headers.get('X-Correlation-Id');
  if (correlationId) {
    console.debug(`[API] ${url} correlation=${correlationId}`);
  }

  if (!res.ok) {
    let errorDetail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.error) {
        errorDetail = `${body.error} (correlation: ${body.correlationId})`;
      }
    } catch {
      // Response was not JSON; use status text
    }
    throw new Error(errorDetail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Layer styles
// ---------------------------------------------------------------------------

function streamStyle(feature?: Feature): PathOptions {
  const order = (feature?.properties?.stream_order as number) ?? 1;
  return { color: '#2563eb', weight: Math.max(1, order), opacity: 0.8 };
}

const BUFFER_STYLE: PathOptions = {
  color: '#059669',
  weight: 1,
  fillColor: '#34d399',
  fillOpacity: 0.25,
};

function parcelStyle(feature?: Feature): PathOptions {
  const focusArea = feature?.properties?.is_focus_area as boolean | null;
  if (focusArea === true) return { color: '#dc2626', weight: 2, fillOpacity: 0.4 };
  if (focusArea === false) return { color: '#16a34a', weight: 2, fillOpacity: 0.3 };
  return { color: '#6b7280', weight: 1, fillOpacity: 0.2 };
}

// ---------------------------------------------------------------------------
// Popups
// ---------------------------------------------------------------------------

function onEachStream(feature: Feature, layer: Layer) {
  const p = feature.properties;
  if (!p) return;
  layer.bindPopup(
    `<strong>${p.gnis_name ?? 'Unnamed Stream'}</strong><br/>` +
    `COMID: ${p.comid}<br/>` +
    `Order: ${p.stream_order ?? 'N/A'}<br/>` +
    `Length: ${p.length_km ? p.length_km + ' km' : 'N/A'}`,
  );
}

function onEachBuffer(feature: Feature, layer: Layer) {
  const p = feature.properties;
  if (!p) return;
  const acres = p.area_sq_m ? (p.area_sq_m / 4046.86).toFixed(2) : 'N/A';
  layer.bindPopup(
    `<strong>Riparian Buffer</strong><br/>` +
    `Stream: ${p.stream_name ?? 'Unknown'}<br/>` +
    `Distance: ${p.buffer_distance_m} m<br/>` +
    `Area: ${acres} acres`,
  );
}

function onEachParcel(feature: Feature, layer: Layer) {
  const p = feature.properties;
  if (!p) return;
  let status = 'No data';
  if (p.is_focus_area === true) status = 'Focus Area';
  else if (p.is_focus_area === false) status = 'Compliant';
  const extra = [
    p.overlap_pct == null ? '' : `Overlap: ${p.overlap_pct}%`,
    p.focus_area_reason ? `Reason: ${p.focus_area_reason}` : '',
  ].filter(Boolean).join('<br/>');

  layer.bindPopup(
    `<strong>Parcel ${p.parcel_id}</strong><br/>` +
    `Owner: ${p.owner_name ?? 'Unknown'}<br/>` +
    `Land Use: ${p.land_use_desc ?? 'N/A'}<br/>` +
    `Acres: ${p.land_acres ?? 'N/A'}<br/>` +
    `Status: ${status}` +
    (extra ? `<br/>${extra}` : ''),
  );
}

// ---------------------------------------------------------------------------
// NDVI heat points from buffer centroids
// ---------------------------------------------------------------------------

function computeHeatPoints(
  buffers: FeatureCollection | null,
): Array<[number, number, number]> {
  if (!buffers?.features) return [];

  return buffers.features
    .map((f) => {
      const coords = extractCoords(f.geometry);
      if (coords.length === 0) return null;
      const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length;
      const lng = coords.reduce((s, c) => s + c[0], 0) / coords.length;
      return [lat, lng, 0.5] as [number, number, number];
    })
    .filter((p): p is [number, number, number] => p !== null);
}

function extractCoords(geometry: Feature['geometry']): number[][] {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return geometry.coordinates[0] ?? [];
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.flatMap((ring) => ring[0] ?? []);
  }
  return [];
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [streams, setStreams] = useState<FeatureCollection | null>(null);
  const [buffers, setBuffers] = useState<FeatureCollection | null>(null);
  const [parcels, setParcels] = useState<FeatureCollection | null>(null);
  const [summary, setSummary] = useState<ComplianceSummary[]>([]);

  useEffect(() => {
    Promise.allSettled([
      fetchJson<FeatureCollection>(`${API_URL}/api/streams`),
      fetchJson<FeatureCollection>(`${API_URL}/api/buffers`),
      fetchJson<FeatureCollection>(`${API_URL}/api/parcels`),
      fetchJson<ComplianceSummary[]>(`${API_URL}/api/summary`),
    ]).then(([s, b, p, sum]) => {
      if (s.status === 'fulfilled') setStreams(s.value);
      if (b.status === 'fulfilled') setBuffers(b.value);
      if (p.status === 'fulfilled') setParcels(p.value);
      if (sum.status === 'fulfilled') setSummary(sum.value);
    });
  }, []);

  const ndviPoints = useMemo(() => computeHeatPoints(buffers), [buffers]);
  const stats = summary[0] ?? null;

  return (
    <div className="flex flex-col h-screen">
      {/* Summary header */}
      <header className="bg-slate-800 text-white px-4 py-3 flex items-center gap-6 text-sm shrink-0">
        <h1 className="text-lg font-semibold whitespace-nowrap">
          Riparian Buffer Compliance
        </h1>
        {stats && (
          <>
            <span>Parcels: {stats.totalParcels}</span>
            <span className="text-green-400">
              Compliant: {stats.compliantParcels}
            </span>
            <span className="text-red-400">
              Focus Areas: {stats.focusAreaParcels}
            </span>
            {stats.compliancePct != null && (
              <span>Compliance: {stats.compliancePct}%</span>
            )}
            {stats.avgNdvi != null && (
              <span>Avg NDVI: {stats.avgNdvi.toFixed(3)}</span>
            )}
          </>
        )}
      </header>

      {/* Map */}
      <div className="flex-1 relative">
        <MapContainer
          center={MAP_CENTER}
          zoom={DEFAULT_ZOOM}
          className="h-full w-full"
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />

          {buffers && (
            <GeoJSON
              data={buffers}
              style={() => BUFFER_STYLE}
              onEachFeature={onEachBuffer}
            />
          )}
          {streams && (
            <GeoJSON
              data={streams}
              style={streamStyle}
              onEachFeature={onEachStream}
            />
          )}
          {parcels && (
            <GeoJSON
              data={parcels}
              style={parcelStyle}
              onEachFeature={onEachParcel}
            />
          )}

          <NDVILayer points={ndviPoints} />
        </MapContainer>

        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white rounded-lg shadow-lg p-4 z-[1000]">
          <h3 className="font-semibold mb-2 text-sm">Legend</h3>
          <div className="space-y-1.5 text-xs">
            <LegendItem color="bg-blue-600" shape="line" label="Streams" />
            <LegendItem color="bg-emerald-400/50" shape="box" label="Riparian Buffers" />
            <LegendItem color="bg-green-600/60" shape="box" label="Compliant Parcels" />
            <LegendItem color="bg-red-600/60" shape="box" label="Focus Area Parcels" />
            <LegendItem color="bg-gray-500/40" shape="box" label="Unknown Status" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legend item
// ---------------------------------------------------------------------------

function LegendItem({
  color,
  shape,
  label,
}: Readonly<{
  color: string;
  shape: 'line' | 'box';
  label: string;
}>) {
  const sizeClass = shape === 'line' ? 'w-4 h-0.5' : 'w-4 h-4 rounded';
  return (
    <div className="flex items-center gap-2">
      <span className={`${sizeClass} ${color} inline-block`} />
      {label}
    </div>
  );
}
