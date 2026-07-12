import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Map,
  Source,
  Layer,
  Popup,
  NavigationControl,
} from 'react-map-gl/maplibre';
import type { MapRef } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent, StyleSpecification } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import NDVILayer from './components/NDVILayer';
import TimeSlider from './components/TimeSlider';
import DocIntelPanel from './components/DocIntelPanel';
import 'maplibre-gl/dist/maplibre-gl.css';

const API_URL = import.meta.env.VITE_API_URL || window.location.origin;
const DOCINTEL_URL = import.meta.env.VITE_DOCINTEL_URL || 'http://localhost:8100';

// Unique session ID for this browser tab — sent with every API call for telemetry correlation.
const SESSION_ID = crypto.randomUUID();

// Centered on the loaded data extent (buffers −108.4→−106.5, parcels −107.5→−106.5)
// so streams, buffers, parcels and wetlands are all visible on first load.
const MAP_CENTER = { longitude: -107.4, latitude: 37.15 };
const DEFAULT_ZOOM = 9;

// ---------------------------------------------------------------------------
// Basemap styles
// ---------------------------------------------------------------------------

const CARTO_POSITRON =
  'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    'esri-satellite': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: 'Tiles &copy; Esri',
    },
  },
  layers: [
    { id: 'satellite-basemap', type: 'raster', source: 'esri-satellite' },
  ],
};

const NAIP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    naip: {
      type: 'raster',
      tiles: [
        'https://gis.apfo.usda.gov/arcgis/rest/services/NAIP/USDA_CONUS_PRIME/ImageServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: 'USDA NAIP Imagery',
    },
  },
  layers: [{ id: 'naip-basemap', type: 'raster', source: 'naip' }],
};

const BASEMAP_STYLES: Record<string, string | StyleSpecification> = {
  street: CARTO_POSITRON,
  satellite: SATELLITE_STYLE,
  naip: NAIP_STYLE,
};

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
  avgCompositeScore: number | null;
  gradeAPct: number | null;
  gradeBPct: number | null;
  gradeCPct: number | null;
  gradeDPct: number | null;
  gradeFPct: number | null;
}

interface PopupInfo {
  longitude: number;
  latitude: number;
  layerType: 'buffer' | 'stream' | 'parcel' | 'wetland' | 'soil';
  properties: Record<string, unknown>;
}

interface BufferDetail {
  landCover: Array<{
    nlcdDescription: string;
    areaPct: number;
    isNatural: boolean;
  }>;
  vegStructure: Array<{
    evtName: string | null;
    evhClass: string | null;
    meanHeightM: number | null;
    dominantLifeform: string | null;
    areaPct: number;
  }>;
  soils: Array<{
    muname: string | null;
    soilPctOfBuffer: number;
    hydricRating: string | null;
  }>;
  canopy: Array<{
    meanHeightM: number | null;
    maxHeightM: number | null;
    p95HeightM: number | null;
    canopyCoverPct: number | null;
  }>;
  score: ScoreDetail | null;
}

interface ScoreDetail {
  ndviScore: number | null;
  verticalComplexityScore: number | null;
  speciesCompositionScore: number | null;
  shrubLayerScore: number | null;
  patchinessScore: number | null;
  nativeRegenerationScore: number | null;
  nativeCoverScore: number | null;
  vegetationStructureScore: number | null;
  connectivityScore: number | null;
  contributingAreaScore: number | null;
  compositeScore: number | null;
  scoreGrade: string | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GRADE_COLORS: Record<string, string> = {
  A: '#16a34a',
  B: '#84cc16',
  C: '#eab308',
  D: '#f97316',
  F: '#dc2626',
};

/** All layer IDs that support click interaction. */
const INTERACTIVE_LAYER_IDS = [
  'buffer-smp-fill',
  'buffer-ndvi-fill',
  'buffer-vegetation-fill',
  'stream-line',
  'parcel-fill',
  'wetland-fill',
  'soil-fill',
];

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
// App
// ---------------------------------------------------------------------------

export default function App() {
  const mapRef = useRef<MapRef>(null);
  const [docGeo, setDocGeo] = useState<FeatureCollection | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);

  // Fit the map to the geometries a doc-intelligence answer resolved.
  useEffect(() => {
    if (!docGeo || !mapRef.current) return;
    let minX = 180;
    let minY = 90;
    let maxX = -180;
    let maxY = -90;
    const walk = (c: unknown): void => {
      if (!Array.isArray(c)) return;
      if (typeof c[0] === 'number') {
        const x = c[0] as number;
        const y = c[1] as number;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      } else {
        c.forEach(walk);
      }
    };
    docGeo.features.forEach((f) => walk((f.geometry as { coordinates?: unknown }).coordinates));
    if (minX <= maxX && minY <= maxY) {
      mapRef.current.fitBounds([[minX, minY], [maxX, maxY]], { padding: 80, duration: 800, maxZoom: 12 });
    }
  }, [docGeo]);

  // GeoJSON state (lightweight layers only)
  // Wetlands and Soils migrated to vector tiles for performance.

  // Scalar state
  const [summary, setSummary] = useState<ComplianceSummary[]>([]);
  const [ndviDates, setNdviDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [bufferLoading, setBufferLoading] = useState(false);

  // UI toggles
  const [showStreams, setShowStreams] = useState(true);
  const [showBuffers, setShowBuffers] = useState(true);
  const [showParcels, setShowParcels] = useState(true);
  const [showWetlands, setShowWetlands] = useState(true);
  const [showSoils, setShowSoils] = useState(false);
  const [showRiparianExtent, setShowRiparianExtent] = useState(false);
  const [riparianExtent, setRiparianExtent] =
    useState<FeatureCollection | null>(null);
  const [showNmripmap, setShowNmripmap] = useState(false);
  const [nmripmap, setNmripmap] = useState<FeatureCollection | null>(null);
  const [viewMode, setViewMode] = useState<'ndvi' | 'smp' | 'vegetation'>(
    'ndvi'
  );
  const [basemap, setBasemap] = useState<'street' | 'satellite' | 'naip'>(
    'street',
  );

  // Popup state
  const [popupInfo, setPopupInfo] = useState<PopupInfo | null>(null);
  const [bufferDetail, setBufferDetail] = useState<BufferDetail | null>(null);
  const [bufferDetailLoading, setBufferDetailLoading] = useState(false);
  const [cursor, setCursor] = useState('');

  // -------------------------------------------------------------------------
  // Initial fetch — lightweight data only (~2MB vs ~90MB before)
  // -------------------------------------------------------------------------

  useEffect(() => {
    Promise.allSettled([
      fetchJson<ComplianceSummary[]>(`${API_URL}/api/summary`),
      fetchJson<string[]>(`${API_URL}/api/ndvi/dates`),
    ]).then(([sumR, datesR]) => {
      if (sumR.status === 'fulfilled') setSummary(sumR.value);
      else console.error('[API] summary failed:', sumR.reason);
      if (datesR.status === 'fulfilled') setNdviDates(datesR.value);
      else console.error('[API] ndvi/dates failed:', datesR.reason);
    });
  }, []);

  // Lazy-load Stage-1 riparian extent (GeoJSON) the first time it's toggled on.
  useEffect(() => {
    if (!showRiparianExtent || riparianExtent) return;
    fetchJson<FeatureCollection>(`${API_URL}/api/riparian/extent?method=rf`)
      .then(setRiparianExtent)
      .catch((err) => console.error('[API] riparian/extent failed:', err));
  }, [showRiparianExtent, riparianExtent]);

  useEffect(() => {
    if (!showNmripmap || nmripmap) return;
    fetchJson<FeatureCollection>(`${API_URL}/api/riparian/extent?method=nmripmap`)
      .then(setNmripmap)
      .catch((err) => console.error('[API] nmripmap failed:', err));
  }, [showNmripmap, nmripmap]);

  // -------------------------------------------------------------------------
  // Tile URLs
  // -------------------------------------------------------------------------

  const ndviTileUrl = useMemo(() => {
    if (selectedDate)
      return `${API_URL}/api/tiles/buffers-ndvi/${selectedDate}/{z}/{x}/{y}.pbf`;
    return `${API_URL}/api/tiles/buffers-ndvi/{z}/{x}/{y}.pbf`;
  }, [selectedDate]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /** Attach session header to all API tile requests. */
  const transformRequest = useCallback((url: string) => {
    if (url.includes('/api/')) {
      return { url, headers: { 'X-Session-Id': SESSION_ID } };
    }
    return { url };
  }, []);

  /** NDVI date slider changed. */
  const handleDateChange = useCallback((date: string | null) => {
    setSelectedDate(date);
    setBufferLoading(true);
    // Tiles load on-demand; brief loading indicator for UX
    setTimeout(() => setBufferLoading(false), 400);
  }, []);

  /** Monotonic token so a slow buffer-detail response can't overwrite a newer click's popup. */
  const bufferDetailReq = useRef(0);

  /** Load buffer detail data on popup open. */
  const loadBufferDetail = useCallback(async (bufferId: number) => {
    const reqId = ++bufferDetailReq.current;
    setBufferDetail(null);
    setBufferDetailLoading(true);

    const [lcR, vsR, soilR, canopyR, scoreR] = await Promise.allSettled([
      fetchJson<BufferDetail['landCover']>(
        `${API_URL}/api/buffers/${bufferId}/landcover`,
      ),
      fetchJson<BufferDetail['vegStructure']>(
        `${API_URL}/api/buffers/${bufferId}/vegetation-structure`,
      ),
      fetchJson<BufferDetail['soils']>(
        `${API_URL}/api/buffers/${bufferId}/soils`,
      ),
      fetchJson<BufferDetail['canopy']>(
        `${API_URL}/api/buffers/${bufferId}/canopy`,
      ),
      fetchJson<ScoreDetail[]>(`${API_URL}/api/buffers/${bufferId}/score`),
    ]);

    // A newer buffer was clicked while these requests were in flight — discard this result.
    if (bufferDetailReq.current !== reqId) return;

    setBufferDetail({
      landCover: lcR.status === 'fulfilled' ? lcR.value : [],
      vegStructure: vsR.status === 'fulfilled' ? vsR.value : [],
      soils: soilR.status === 'fulfilled' ? soilR.value : [],
      canopy: canopyR.status === 'fulfilled' ? canopyR.value : [],
      score:
        scoreR.status === 'fulfilled'
          ? (scoreR.value[0] ?? null)
          : null,
    });
    setBufferDetailLoading(false);
  }, []);

  /** Map click handler — open popup for the clicked feature. */
  const handleMapClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) {
        setPopupInfo(null);
        return;
      }

      const { lng, lat } = event.lngLat;
      const layerId = feature.layer.id;

      let layerType: PopupInfo['layerType'];
      if (layerId.startsWith('buffer-')) layerType = 'buffer';
      else if (layerId === 'buffer-vegetation-fill') layerType = 'buffer';
      else if (layerId === 'stream-line') layerType = 'stream';
      else if (layerId === 'parcel-fill') layerType = 'parcel';
      else if (layerId === 'wetland-fill') layerType = 'wetland';
      else if (layerId === 'soil-fill') layerType = 'soil';
      else return;

      const props = (feature.properties ?? {}) as Record<string, unknown>;

      setPopupInfo({ longitude: lng, latitude: lat, layerType, properties: props });
      setBufferDetail(null);
      setBufferDetailLoading(false);

      if (layerType === 'buffer' && props.id != null) {
        loadBufferDetail(props.id as number);
      }
    },
    [loadBufferDetail],
  );

  const stats = summary[0] ?? null;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

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
            {viewMode === 'ndvi' && stats.avgNdvi != null && (
              <span>Avg NDVI: {stats.avgNdvi.toFixed(3)}</span>
            )}
            {viewMode === 'smp' && stats.avgCompositeScore != null && (
              <span className="text-emerald-300">
                SMP Score: {stats.avgCompositeScore.toFixed(1)}/100
              </span>
            )}
          </>
        )}
        <div className="ml-auto flex gap-1">
          <button
            onClick={() => setViewMode('ndvi')}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              viewMode === 'ndvi'
                ? 'bg-green-600 text-white'
                : 'bg-slate-600 text-slate-300 hover:bg-slate-500'
            }`}
          >
            NDVI Health
          </button>
          <button
            onClick={() => setViewMode('smp')}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              viewMode === 'smp'
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-600 text-slate-300 hover:bg-slate-500'
            }`}
          >
            SMP Score
          </button>
          <button
            onClick={() => setViewMode('vegetation')}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              viewMode === 'vegetation'
                ? 'bg-lime-600 text-white'
                : 'bg-slate-600 text-slate-300 hover:bg-slate-500'
            }`}
          >
            Vegetation
          </button>
        </div>
      </header>

      {/* Map */}
      <div className="flex-1 relative">
        <Map
          ref={mapRef}
          initialViewState={{
            ...MAP_CENTER,
            zoom: DEFAULT_ZOOM,
          }}
          style={{ width: '100%', height: '100%' }}
          mapStyle={BASEMAP_STYLES[basemap]}
          transformRequest={transformRequest}
          interactiveLayerIds={INTERACTIVE_LAYER_IDS}
          onClick={handleMapClick}
          onMouseEnter={() => setCursor('pointer')}
          onMouseLeave={() => setCursor('')}
          cursor={cursor}
        >
          <NavigationControl position="top-right" />

          {/* ---- Doc-intelligence highlight (rivers/reaches/HUCs from an answer) ---- */}
          {docGeo && (
            <Source id="docintel-highlight" type="geojson" data={docGeo}>
              <Layer
                id="docintel-highlight-fill"
                type="fill"
                paint={{ 'fill-color': '#f59e0b', 'fill-opacity': 0.15 }}
              />
              <Layer
                id="docintel-highlight-line"
                type="line"
                paint={{ 'line-color': '#f59e0b', 'line-width': 4, 'line-opacity': 0.95 }}
              />
            </Source>
          )}

          {/* ---- Soil fills (bottom data layer) ---- */}
          <Source
            id="soils-source"
            type="vector"
            tiles={[`${API_URL}/api/tiles/soils/{z}/{x}/{y}.pbf`]}
          >
            <Layer
              id="soil-fill"
              type="fill"
              source-layer="soils"
              layout={{ visibility: showSoils ? 'visible' : 'none' }}
              paint={{
                'fill-color': [
                  'match',
                  ['get', 'hydric_rating'],
                  'Yes', '#8b5cf6',
                  'Partial', '#c084fc',
                  '#d1d5db',
                ],
                'fill-opacity': [
                  'match',
                  ['get', 'hydric_rating'],
                  'Yes', 0.4,
                  'Partial', 0.3,
                  0.15,
                ],
                'fill-outline-color': [
                  'match',
                  ['get', 'hydric_rating'],
                  'Yes', '#7c3aed',
                  'Partial', '#a855f7',
                  '#9ca3af',
                ],
              }}
            />
          </Source>

          {/* ---- Wetland fills ---- */}
          <Source
            id="wetlands-source"
            type="vector"
            tiles={[`${API_URL}/api/tiles/wetlands/{z}/{x}/{y}.pbf`]}
          >
            <Layer
              id="wetland-fill"
              type="fill"
              source-layer="wetlands"
              layout={{ visibility: showWetlands ? 'visible' : 'none' }}
              paint={{
                'fill-color': '#22d3ee',
                'fill-opacity': 0.35,
                'fill-outline-color': '#0891b2',
              }}
            />
          </Source>

          {/* ---- Parcel tiles ---- */}
          <Source
            id="parcels-source"
            type="vector"
            tiles={[`${API_URL}/api/tiles/parcels/{z}/{x}/{y}.pbf`]}
          >
            <Layer
              id="parcel-fill"
              type="fill"
              source-layer="parcels"
              layout={{ visibility: showParcels ? 'visible' : 'none' }}
              paint={{
                'fill-color': [
                  'case',
                  ['==', ['get', 'is_focus_area'], true],
                  '#dc2626',
                  ['==', ['get', 'is_focus_area'], false],
                  '#16a34a',
                  '#6b7280',
                ],
                'fill-opacity': [
                  'case',
                  ['==', ['get', 'is_focus_area'], true],
                  0.4,
                  ['==', ['get', 'is_focus_area'], false],
                  0.3,
                  0.2,
                ],
                'fill-outline-color': [
                  'case',
                  ['==', ['get', 'is_focus_area'], true],
                  '#dc2626',
                  ['==', ['get', 'is_focus_area'], false],
                  '#16a34a',
                  '#6b7280',
                ],
              }}
            />
          </Source>

          {/* ---- Riparian extent (Stage 1 delineation, GeoJSON) ---- */}
          <Source
            id="riparian-extent-source"
            type="geojson"
            data={
              riparianExtent ??
              ({ type: 'FeatureCollection', features: [] } as FeatureCollection)
            }
          >
            <Layer
              id="riparian-extent-fill"
              type="fill"
              layout={{
                visibility: showRiparianExtent ? 'visible' : 'none',
              }}
              paint={{
                'fill-color': [
                  'interpolate',
                  ['linear'],
                  ['get', 'riparian_probability'],
                  0.5, '#a7f3d0',
                  0.75, '#34d399',
                  1.0, '#059669',
                ],
                'fill-opacity': 0.6,
                'fill-outline-color': '#047857',
              }}
            />
          </Source>

          {/* ---- NMRipMap reference (authoritative NM riparian map, simplified) ---- */}
          <Source
            id="nmripmap-source"
            type="geojson"
            data={
              nmripmap ??
              ({ type: 'FeatureCollection', features: [] } as FeatureCollection)
            }
          >
            <Layer
              id="nmripmap-fill"
              type="fill"
              layout={{ visibility: showNmripmap ? 'visible' : 'none' }}
              paint={{ 'fill-color': '#a855f7', 'fill-opacity': 0.22 }}
            />
            <Layer
              id="nmripmap-outline"
              type="line"
              layout={{ visibility: showNmripmap ? 'visible' : 'none' }}
              paint={{ 'line-color': '#7e22ce', 'line-width': 1 }}
            />
          </Source>

          {/* ---- Buffer SMP tiles ---- */}
          <Source
            id="buffer-smp-source"
            type="vector"
            tiles={[`${API_URL}/api/tiles/{z}/{x}/{y}.pbf`]}
          >
            <Layer
              id="buffer-smp-fill"
              type="fill"
              source-layer="buffers"
              layout={{
                visibility:
                  showBuffers && viewMode === 'smp' ? 'visible' : 'none',
              }}
              paint={{
                'fill-color': [
                  'match',
                  ['get', 'grade'],
                  'A', '#16a34a',
                  'B', '#84cc16',
                  'C', '#eab308',
                  'D', '#f97316',
                  'F', '#dc2626',
                  '#34d399',
                ],
                'fill-opacity': 0.5,
                'fill-outline-color': [
                  'match',
                  ['get', 'grade'],
                  'A', '#15803d',
                  'B', '#65a30d',
                  'C', '#ca8a04',
                  'D', '#ea580c',
                  'F', '#b91c1c',
                  '#059669',
                ],
              }}
            />
          </Source>

          {/* ---- Buffer Vegetation tiles ---- */}
          <Source
            id="buffer-vegetation-source"
            type="vector"
            tiles={[`${API_URL}/api/tiles/vegetation/{z}/{x}/{y}.pbf`]}
          >
            <Layer
              id="buffer-vegetation-fill"
              type="fill"
              source-layer="vegetation"
              layout={{
                visibility:
                  showBuffers && viewMode === 'vegetation' ? 'visible' : 'none',
              }}
              paint={{
                'fill-color': [
                  'match',
                  ['coalesce', ['get', 'lifeform'], 'Unknown'],
                  'Tree', '#15803d', // dark green — closed canopy
                  'Shrub', '#84cc16', // light green — shrubland
                  'Herb', '#facc15', // gold — herbaceous
                  'Agriculture', '#eab308', // amber — cropland
                  'Water/Barren', '#94a3b8', // slate — water / barren
                  '#cbd5e1', // muted gray — Unknown / other
                ],
                'fill-opacity': 0.8,
                'fill-outline-color': '#475569',
              }}
            />
          </Source>

          {/* ---- Buffer NDVI tiles ---- */}
          <Source
            key={`ndvi-tiles-${selectedDate ?? 'latest'}`}
            id="buffer-ndvi-source"
            type="vector"
            tiles={[ndviTileUrl]}
          >
            <Layer
              id="buffer-ndvi-fill"
              type="fill"
              source-layer="buffers"
              layout={{
                visibility:
                  showBuffers && viewMode === 'ndvi' ? 'visible' : 'none',
              }}
              paint={{
                'fill-color': [
                  'match',
                  ['coalesce', ['get', 'health_category'], ''],
                  'healthy', '#16a34a',
                  'degraded', '#f59e0b',
                  'bare', '#dc2626',
                  '#34d399',
                ],
                'fill-opacity': 0.45,
                'fill-outline-color': [
                  'match',
                  ['coalesce', ['get', 'health_category'], ''],
                  'healthy', '#15803d',
                  'degraded', '#b45309',
                  'bare', '#b91c1c',
                  '#059669',
                ],
              }}
            />
          </Source>

          {/* ---- Stream tiles ---- */}
          <Source
            id="streams-source"
            type="vector"
            tiles={[`${API_URL}/api/tiles/streams/{z}/{x}/{y}.pbf`]}
          >
            <Layer
              id="stream-line"
              type="line"
              source-layer="streams"
              layout={{ visibility: showStreams ? 'visible' : 'none' }}
              paint={{
                'line-color': '#2563eb',
                'line-width': [
                  'interpolate',
                  ['linear'],
                  ['coalesce', ['get', 'stream_order'], 1],
                  1, 1,
                  3, 2,
                  5, 4,
                ],
                'line-opacity': 0.8,
              }}
            />
          </Source>

          {/* ---- NDVI heatmap overlay ---- */}
          <NDVILayer />

          {/* ---- Popup ---- */}
          {popupInfo && (
            <Popup
              longitude={popupInfo.longitude}
              latitude={popupInfo.latitude}
              anchor="bottom"
              closeOnClick={false}
              onClose={() => setPopupInfo(null)}
              maxWidth="360px"
            >
              <PopupContent
                info={popupInfo}
                viewMode={viewMode}
                detail={bufferDetail}
                detailLoading={bufferDetailLoading}
              />
            </Popup>
          )}
        </Map>

        <DocIntelPanel docintelUrl={DOCINTEL_URL} onResolved={setDocGeo} />

        {/* Layer toggles */}
        <div className="absolute top-4 left-4 z-[1000] bg-white rounded-lg shadow-lg px-3 py-2 text-xs space-y-1">
          <span className="block text-[10px] font-semibold text-gray-500 uppercase tracking-wide">
            Layers
          </span>
          <LayerToggle
            label="Streams"
            checked={showStreams}
            onChange={setShowStreams}
            accent="accent-blue-600"
          />
          <LayerToggle
            label="Buffers"
            checked={showBuffers}
            onChange={setShowBuffers}
            accent="accent-green-600"
          />
          <LayerToggle
            label="Parcels"
            checked={showParcels}
            onChange={setShowParcels}
            accent="accent-amber-600"
          />
          <LayerToggle
            label="NWI Wetlands"
            checked={showWetlands}
            onChange={setShowWetlands}
            accent="accent-cyan-600"
          />
          <LayerToggle
            label="SSURGO Soils"
            checked={showSoils}
            onChange={setShowSoils}
            accent="accent-violet-600"
          />
          <LayerToggle
            label="Riparian Extent (Stage 1)"
            checked={showRiparianExtent}
            onChange={setShowRiparianExtent}
            accent="accent-emerald-600"
          />
          <LayerToggle
            label="NMRipMap (NM reference)"
            checked={showNmripmap}
            onChange={setShowNmripmap}
            accent="accent-purple-600"
          />
        </div>

        {/* Basemap toggle */}
        <button
          onClick={() =>
            setBasemap((b) => {
              const cycle = {
                street: 'satellite',
                satellite: 'naip',
                naip: 'street',
              } as const;
              return cycle[b];
            })
          }
          className="absolute top-16 right-4 z-[1000] bg-white rounded-lg shadow-lg px-3 py-2 text-xs font-medium hover:bg-gray-100 transition-colors"
        >
          {
            { street: 'Satellite', satellite: 'NAIP Aerial', naip: 'Street Map' }[
              basemap
            ]
          }
        </button>

        {/* Timelapse slider */}
        <TimeSlider
          dates={ndviDates}
          selectedDate={selectedDate}
          onDateChange={handleDateChange}
          loading={bufferLoading}
        />

        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white rounded-lg shadow-lg p-4 z-[1000]">
          <button
            type="button"
            onClick={() => setLegendOpen((o) => !o)}
            className="flex items-center gap-1.5 font-semibold text-sm w-full text-left"
          >
            <span className="text-gray-400 text-xs">{legendOpen ? '▾' : '▸'}</span>
            Legend
          </button>
          {legendOpen && (
          <div className="space-y-1.5 text-xs mt-2">
            {showStreams && (
              <LegendItem color="bg-blue-600" shape="line" label="Streams" />
            )}
            {showRiparianExtent && (
              <LegendItem
                color="bg-emerald-600"
                shape="box"
                label="Riparian extent (Stage 1, RF)"
              />
            )}
            {viewMode === 'ndvi' && (
              <>
                <span className="block text-[10px] text-gray-500 pt-1">
                  Buffer NDVI Health
                </span>
                <LegendItem
                  color="bg-green-600/70"
                  shape="box"
                  label="Healthy (>0.25)"
                />
                <LegendItem
                  color="bg-amber-400/70"
                  shape="box"
                  label="Degraded (0.10-0.25)"
                />
                <LegendItem
                  color="bg-red-600/70"
                  shape="box"
                  label="Bare (<0.10)"
                />
                <LegendItem
                  color="bg-emerald-400/50"
                  shape="box"
                  label="No NDVI Data"
                />
              </>
            )}
            {viewMode === 'smp' && (
              <>
                <span className="block text-[10px] text-gray-500 pt-1">
                  SMP Health Grade
                </span>
                <LegendItem
                  color="bg-green-600/70"
                  shape="box"
                  label={'A \u2014 Excellent (\u226580)'}
                />
                <LegendItem
                  color="bg-lime-500/70"
                  shape="box"
                  label={'B \u2014 Good (\u226560)'}
                />
                <LegendItem
                  color="bg-yellow-400/70"
                  shape="box"
                  label={'C \u2014 Fair (\u226540)'}
                />
                <LegendItem
                  color="bg-orange-500/70"
                  shape="box"
                  label={'D \u2014 Poor (\u226520)'}
                />
                <LegendItem
                  color="bg-red-600/70"
                  shape="box"
                  label="F \u2014 Failing (<20)"
                />
                <LegendItem
                  color="bg-emerald-400/50"
                  shape="box"
                  label="No Score Data"
                />
              </>
            )}
            {viewMode === 'vegetation' && (
              <>
                <span className="block text-[10px] text-gray-500 pt-1">
                  Vegetation Lifeform (LANDFIRE)
                </span>
                <LegendItem color="bg-green-700/80" shape="box" label="Tree" />
                <LegendItem color="bg-lime-500/80" shape="box" label="Shrub" />
                <LegendItem color="bg-yellow-400/80" shape="box" label="Herb" />
                <LegendItem
                  color="bg-yellow-500/80"
                  shape="box"
                  label="Agriculture"
                />
                <LegendItem
                  color="bg-slate-400/80"
                  shape="box"
                  label="Water / Barren"
                />
                <LegendItem
                  color="bg-slate-300/80"
                  shape="box"
                  label="Unknown / Other"
                />
              </>
            )}
            {showParcels && (
              <>
                <span className="block text-[10px] text-gray-500 pt-1">
                  Parcels
                </span>
                <LegendItem
                  color="bg-green-600/60"
                  shape="box"
                  label="Compliant"
                />
                <LegendItem
                  color="bg-red-600/60"
                  shape="box"
                  label="Focus Area"
                />
                <LegendItem
                  color="bg-gray-500/40"
                  shape="box"
                  label="Unknown Status"
                />
              </>
            )}
            {(showWetlands || showSoils || showNmripmap) && (
              <span className="block text-[10px] text-gray-500 pt-1">
                Overlays
              </span>
            )}
            {showWetlands && (
              <LegendItem
                color="bg-cyan-400/60"
                shape="box"
                label="NWI Wetlands"
              />
            )}
            {showSoils && (
              <>
                {/* Keep in sync with the soil fill `match` on hydric_rating above:
                    Yes -> #8b5cf6 (violet-500), Partial -> #c084fc (purple-400),
                    everything else -> #d1d5db (gray-300). SSURGO rates map units as
                    partially hydric when only some components are, and those polygons
                    were being drawn with no legend key at all. */}
                <LegendItem
                  color="bg-violet-500/50"
                  shape="box"
                  label="Hydric Soils"
                />
                <LegendItem
                  color="bg-purple-400/40"
                  shape="box"
                  label="Partially Hydric Soils"
                />
                <LegendItem
                  color="bg-gray-300/50"
                  shape="box"
                  label="Non-Hydric Soils"
                />
              </>
            )}
            {showNmripmap && (
              <LegendItem
                color="bg-purple-500/40"
                shape="box"
                label="NMRipMap (NM reference)"
              />
            )}
          </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Popup content
// ---------------------------------------------------------------------------

function PopupContent({
  info,
  viewMode,
  detail,
  detailLoading,
}: Readonly<{
  info: PopupInfo;
  viewMode: 'ndvi' | 'smp' | 'vegetation';
  detail: BufferDetail | null;
  detailLoading: boolean;
}>) {
  const p = info.properties;

  if (info.layerType === 'stream') {
    return (
      <div className="text-xs">
        <div className="font-semibold text-sm">
          {(p.gnis_name as string) ?? 'Unnamed Stream'}
        </div>
        <div>COMID: {p.comid as number}</div>
        <div>Order: {(p.stream_order as number) ?? 'N/A'}</div>
        <div>
          Length: {p.length_km ? `${p.length_km} km` : 'N/A'}
        </div>
      </div>
    );
  }

  if (info.layerType === 'parcel') {
    let status = 'No data';
    if (p.is_focus_area === true) status = 'Focus Area';
    else if (p.is_focus_area === false) status = 'Compliant';
    return (
      <div className="text-xs">
        <div className="font-semibold text-sm">
          Parcel {p.parcel_id as string}
        </div>
        <div>Owner: {(p.owner_name as string) ?? 'Unknown'}</div>
        <div>Land Use: {(p.land_use_desc as string) ?? 'N/A'}</div>
        <div>Acres: {(p.land_acres as number) ?? 'N/A'}</div>
        <div>Status: {status}</div>
        {p.overlap_pct != null && (
          <div>Buffer Overlap: {p.overlap_pct as number}%</div>
        )}
        {p.focus_area_reason ? (
          <div>Reason: {p.focus_area_reason as string}</div>
        ) : null}
      </div>
    );
  }

  if (info.layerType === 'wetland') {
    return (
      <div className="text-xs">
        <div className="font-semibold text-sm">NWI Wetland</div>
        <div>Type: {(p.wetland_type as string) ?? 'N/A'}</div>
        <div>Cowardin Code: {(p.cowardin_code as string) ?? 'N/A'}</div>
        <div>
          Acres:{' '}
          {p.acres != null ? Number(p.acres).toFixed(2) : 'N/A'}
        </div>
      </div>
    );
  }

  if (info.layerType === 'soil') {
    return (
      <div className="text-xs">
        <div className="font-semibold text-sm">SSURGO Soil</div>
        <div>
          Map Unit:{' '}
          {(p.muname as string) ??
            (p.musym as string) ??
            (p.mukey as string) ??
            'N/A'}
        </div>
        <div>MUKEY: {(p.mukey as string) ?? 'N/A'}</div>
        {p.hydric_rating ? (
          <div>
            Hydric: <strong>{p.hydric_rating as string}</strong>{' '}
            ({(p.hydric_pct as number) ?? 0}% components)
          </div>
        ) : (
          <div>Hydric: N/A</div>
        )}
      </div>
    );
  }

  // Buffer popup
  return (
    <BufferPopupContent
      properties={p}
      viewMode={viewMode}
      detail={detail}
      detailLoading={detailLoading}
    />
  );
}

// ---------------------------------------------------------------------------
// Buffer popup (with lazy-loaded detail)
// ---------------------------------------------------------------------------

const fmt = (v: number | null | undefined) =>
  v != null ? v.toFixed(1) : '-';

function BufferPopupContent({
  properties: p,
  viewMode,
  detail,
  detailLoading,
}: Readonly<{
  properties: Record<string, unknown>;
  viewMode: 'ndvi' | 'smp' | 'vegetation';
  detail: BufferDetail | null;
  detailLoading: boolean;
}>) {
  const distM = p.buffer_distance_m as number;
  const areaSqM = p.area_sq_m as number | null;
  const acres = areaSqM ? (areaSqM / 4046.86).toFixed(2) : null;
  const streamName = (p.stream_name as string) ?? null;

  // SMP properties
  const grade = (p.grade as string) ?? null;
  const compositeScore =
    p.composite_score != null ? Number(p.composite_score).toFixed(1) : null;

  // NDVI properties
  const ndvi =
    p.mean_ndvi != null ? Number(p.mean_ndvi).toFixed(3) : null;
  const healthCat = (p.health_category as string) ?? null;
  const acqDate = (p.acquisition_date as string) ?? null;

  return (
    <div className="text-xs max-w-[340px]">
      {viewMode === 'vegetation' ? (
        <>
          <div className="font-semibold text-sm">Vegetation Structure</div>
          {streamName && <div>Stream: {streamName}</div>}
          <div className="my-1">
            <span className="font-medium">Lifeform: </span>
            {p.lifeform as string}
          </div>
          <div>
            <span className="font-medium">Type: </span>
            {p.evt_name as string}
          </div>
        </>
      ) : viewMode === 'smp' ? (
        <>
          <div className="font-semibold text-sm">SMP Health Score</div>
          {streamName && <div>Stream: {streamName}</div>}
          <div>Distance: {distM}m</div>
          {acres && <div>Area: {acres} acres</div>}
          {grade && (
            <div className="flex items-center gap-2 my-1">
              <span
                className="text-2xl font-bold"
                style={{ color: GRADE_COLORS[grade] ?? '#9ca3af' }}
              >
                {grade}
              </span>
              {compositeScore && (
                <span className="text-base">{compositeScore}/100</span>
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="font-semibold text-sm">Riparian Buffer</div>
          {streamName && <div>Stream: {streamName}</div>}
          <div>Distance: {distM}m</div>
          {acres && <div>Area: {acres} acres</div>}
          {ndvi && (
            <div>
              NDVI: {ndvi} ({healthCat})
            </div>
          )}
          {acqDate && <div>Acquired: {acqDate}</div>}
        </>
      )}

      {/* Loading indicator */}
      {detailLoading && (
        <div className="text-gray-400 italic mt-2">Loading datasets...</div>
      )}

      {/* Detail sections */}
      {detail && (
        <>
          {/* SMP score breakdown */}
          {detail.score && viewMode === 'smp' && (
            <div className="border-t border-gray-200 mt-2 pt-2">
              <div className="font-semibold">
                Vegetation (80%):{' '}
                {fmt(detail.score.vegetationStructureScore)}/100
              </div>
              <div className="ml-2 text-[11px]">
                NDVI: {fmt(detail.score.ndviScore)}/10 &middot; Complexity:{' '}
                {fmt(detail.score.verticalComplexityScore)}/10
                <br />
                Species: {fmt(detail.score.speciesCompositionScore)}/10
                &middot; Shrub: {fmt(detail.score.shrubLayerScore)}/10
                <br />
                Patchiness: {fmt(detail.score.patchinessScore)}/10 &middot;
                Regen: {fmt(detail.score.nativeRegenerationScore)}/10
                <br />
                Native Cover: {fmt(detail.score.nativeCoverScore)}/10
              </div>
              <div className="font-semibold mt-1">
                Connectivity (10%):{' '}
                {fmt(detail.score.connectivityScore)}/100
              </div>
              <div className="font-semibold">
                Contributing (10%):{' '}
                {fmt(detail.score.contributingAreaScore)}/100
              </div>
            </div>
          )}

          {/* Soils */}
          {detail.soils.length > 0 && (
            <div className="border-t border-gray-200 mt-2 pt-2">
              <div className="font-semibold">
                Soils (
                {detail.soils
                  .filter(
                    (s) =>
                      s.hydricRating === 'Yes' ||
                      s.hydricRating === 'Partial',
                  )
                  .reduce((a, c) => a + (c.soilPctOfBuffer ?? 0), 0)
                  .toFixed(0)}
                % hydric)
              </div>
              <div className="text-[11px]">
                {detail.soils.slice(0, 3).map((soil, i) => {
                  const color =
                    soil.hydricRating === 'Yes'
                      ? '#7c3aed'
                      : soil.hydricRating === 'Partial'
                        ? '#a855f7'
                        : '#9ca3af';
                  return (
                    <div key={i}>
                      <span style={{ color }}>&#9632;</span>{' '}
                      {soil.muname ?? 'Unknown'}{' '}
                      {(soil.soilPctOfBuffer ?? 0).toFixed(1)}%
                      {soil.hydricRating && ` (${soil.hydricRating})`}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* NLCD Land Cover */}
          {detail.landCover.length > 0 && (
            <div className="border-t border-gray-200 mt-2 pt-2">
              <div className="font-semibold">
                NLCD Land Cover (
                {detail.landCover
                  .filter((c) => c.isNatural)
                  .reduce((a, c) => a + (c.areaPct ?? 0), 0)
                  .toFixed(0)}
                % natural)
              </div>
              <div className="text-[11px]">
                {detail.landCover.slice(0, 5).map((lc, i) => (
                  <div key={i}>
                    <span
                      style={{
                        color: lc.isNatural ? '#16a34a' : '#dc2626',
                      }}
                    >
                      {'\u2588'.repeat(
                        Math.max(1, Math.round((lc.areaPct ?? 0) / 5)),
                      )}
                    </span>{' '}
                    {lc.nlcdDescription} {(lc.areaPct ?? 0).toFixed(1)}%
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* LANDFIRE Vegetation Structure */}
          {detail.vegStructure.length > 0 && (() => {
            const vs = detail.vegStructure[0];
            return (
              <div className="border-t border-gray-200 mt-2 pt-2">
                <div className="font-semibold">Vegetation Structure</div>
                <div className="text-[11px]">
                  <div>Type: {vs.evtName ?? 'N/A'}</div>
                  <div>Lifeform: {vs.dominantLifeform ?? 'N/A'}</div>
                  <div>
                    Height: {vs.evhClass ?? 'N/A'}
                    {vs.meanHeightM != null &&
                      ` (${vs.meanHeightM.toFixed(1)}m)`}
                  </div>
                  <div>Coverage: {(vs.areaPct ?? 0).toFixed(1)}%</div>
                </div>
              </div>
            );
          })()}

          {/* 3DEP LiDAR Canopy */}
          {detail.canopy.length > 0 && (() => {
            const c = detail.canopy[0];
            return (
              <div className="border-t border-gray-200 mt-2 pt-2">
                <div className="font-semibold">
                  Canopy Height (3DEP LiDAR)
                </div>
                <div className="text-[11px]">
                  Mean:{' '}
                  {c.meanHeightM != null
                    ? c.meanHeightM.toFixed(1) + 'm'
                    : 'N/A'}{' '}
                  &middot; Max:{' '}
                  {c.maxHeightM != null
                    ? c.maxHeightM.toFixed(1) + 'm'
                    : 'N/A'}
                  <br />
                  P95:{' '}
                  {c.p95HeightM != null
                    ? c.p95HeightM.toFixed(1) + 'm'
                    : 'N/A'}{' '}
                  &middot; Cover:{' '}
                  {c.canopyCoverPct != null
                    ? c.canopyCoverPct.toFixed(1) + '%'
                    : 'N/A'}
                </div>
              </div>
            );
          })()}

          {/* No data fallback */}
          {detail.soils.length === 0 &&
            detail.landCover.length === 0 &&
            detail.vegStructure.length === 0 &&
            detail.canopy.length === 0 &&
            !detail.score && (
              <div className="text-gray-400 italic mt-2 text-[11px]">
                No raster data available
              </div>
            )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Layer toggle
// ---------------------------------------------------------------------------

function LayerToggle({
  label,
  checked,
  onChange,
  accent,
}: Readonly<{
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  accent: string;
}>) {
  return (
    <label className="flex items-center gap-1.5 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className={accent}
      />
      {label}
    </label>
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
