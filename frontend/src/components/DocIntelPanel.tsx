import { useState } from 'react';
import type { Feature, FeatureCollection, Geometry } from 'geojson';

/**
 * Document-intelligence Q&A panel. Calls the docintel backend's POST /docs/ask
 * (see the private riparian-rag-harness + docintel/API_CONTRACT.md), renders the
 * cited answer, and lifts the resolved geometries up so App.tsx can highlight the
 * mentioned rivers/reaches/HUCs on the MapLibre map. RAG explains; the map shows.
 */

interface ResolvedGeometry {
  mention_text: string;
  resolved: boolean;
  kind: string | null;
  ref: string | null;
  confidence: number | null;
  geom: Geometry | null;
}

interface AskResponse {
  answer: string;
  geo_available: boolean;
  citations: { source_file: string }[];
  geo_mentions: { text: string; type: string }[];
  resolved_geometries: ResolvedGeometry[];
}

interface DocIntelPanelProps {
  docintelUrl: string;
  onResolved: (features: FeatureCollection | null) => void;
}

const S = {
  panel: {
    // Below the nav control (top-right corner) + basemap toggle (top-16 right-4),
    // so the right edge stacks cleanly: zoom → basemap → this panel. Capped so it
    // doesn't reach the bottom-right legend.
    position: 'absolute' as const, top: 108, right: 12, width: 340,
    maxHeight: 'calc(100vh - 320px)',
    overflowY: 'auto' as const, background: 'rgba(17,24,39,0.94)', color: '#e5e7eb',
    borderRadius: 10, padding: 14, zIndex: 5, fontSize: 13, lineHeight: 1.5,
    boxShadow: '0 6px 24px rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)',
  },
  title: { fontWeight: 700, fontSize: 14, marginBottom: 8, color: '#93c5fd' },
  textarea: {
    width: '100%', boxSizing: 'border-box' as const, background: '#111827',
    color: '#e5e7eb', border: '1px solid #374151', borderRadius: 6, padding: 8, resize: 'vertical' as const,
  },
  button: {
    marginTop: 8, width: '100%', background: '#2563eb', color: 'white', border: 'none',
    borderRadius: 6, padding: '8px 10px', fontWeight: 600, cursor: 'pointer',
  },
  answer: { marginTop: 12, whiteSpace: 'pre-wrap' as const },
  cites: { marginTop: 10, fontSize: 12, color: '#cbd5e1' },
  geo: { marginTop: 10, fontSize: 12, color: '#86efac' },
  error: { marginTop: 8, color: '#fca5a5', fontSize: 12 },
};

export default function DocIntelPanel({ docintelUrl, onResolved }: DocIntelPanelProps) {
  const [question, setQuestion] = useState('');
  const [resp, setResp] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResp(null);
    onResolved(null);
    try {
      const r = await fetch(`${docintelUrl}/docs/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      if (!r.ok) throw new Error(`docintel HTTP ${r.status}`);
      const data: AskResponse = await r.json();
      setResp(data);
      const features: Feature[] = data.resolved_geometries
        .filter((g) => g.resolved && g.geom)
        .map((g) => ({
          type: 'Feature',
          geometry: g.geom as Geometry,
          properties: { label: g.ref, kind: g.kind, mention: g.mention_text },
        }));
      onResolved(features.length ? { type: 'FeatureCollection', features } : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'request failed');
    } finally {
      setLoading(false);
    }
  };

  const resolved = resp?.resolved_geometries.filter((g) => g.resolved) ?? [];

  return (
    <div style={S.panel}>
      <div style={S.title}>Ask the watershed documents</div>
      <textarea
        style={S.textarea}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask();
        }}
        placeholder="e.g. What restoration actions are described for the Animas River near Farmington?"
        rows={3}
      />
      <button style={S.button} onClick={ask} disabled={loading}>
        {loading ? 'Asking…' : 'Ask (⌘⏎)'}
      </button>
      {error && <div style={S.error}>{error}</div>}
      {resp && (
        <>
          <div style={S.answer}>{resp.answer}</div>
          {resp.citations.length > 0 && (
            <div style={S.cites}>
              <strong>Sources</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                {resp.citations.map((c) => (
                  <li key={c.source_file}>{c.source_file}</li>
                ))}
              </ul>
            </div>
          )}
          <div style={S.geo}>
            {resolved.length > 0
              ? `📍 Highlighted on map: ${resolved.map((g) => g.mention_text).join(', ')}`
              : resp.geo_available
                ? 'No mapped locations in this answer.'
                : 'Geo layer unavailable (DB offline).'}
          </div>
        </>
      )}
    </div>
  );
}
