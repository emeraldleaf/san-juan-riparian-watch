// The "ask the map" chat island. Posts a plain-language question to /agent/map,
// renders the cited answer + the tool trace, and hands the resolved geometry to
// the imperative map (map-agent-client.ts) via a window CustomEvent. Same seam the
// story maps use: React fetches, the map listens.
import { useEffect, useRef, useState } from 'react';
import { turnstileToken } from '../scripts/turnstile';

type Msg = { role: 'user' | 'agent'; text: string; steps?: { tool: string }[]; cited?: string[] };
type Reach = { name: string; reaches: number };

// Fallback if the live /agent/map/coverage list can't be fetched.
const FALLBACK: Reach[] = [
  { name: 'San Juan River', reaches: 0 },
  { name: 'Malpais Arroyo', reaches: 0 },
  { name: 'Yellow Arroyo', reaches: 0 },
];

export default function MapAgent() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [val, setVal] = useState('');
  const [reaches, setReaches] = useState<Reach[]>([]);
  const [pickerOpen, setPickerOpen] = useState(true);

  // The named reaches the model actually mapped, straight from the data.
  useEffect(() => {
    fetch('/agent/map/coverage')
      .then((r) => (r.ok ? r.json() : { reaches: [] }))
      .then((d) => setReaches(Array.isArray(d.reaches) ? d.reaches : []))
      .catch(() => {});
  }, []);
  const logRef = useRef<HTMLDivElement>(null);

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setVal('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    try {
      const token = await turnstileToken();
      const headers: Record<string, string> = { 'content-type': 'application/json' };
      if (token) headers['X-Turnstile-Token'] = token;
      const r = await fetch('/agent/map', {
        method: 'POST',
        headers,
        body: JSON.stringify({ question: q }),
      });
      const d = await r.json();
      const context = Object.values(d.display_geom || {}).filter(Boolean)[0];
      // Prefer the riparian delineation polygons for the highlight, so the map
      // shows the actual riparian area (never off into non-riparian) and only
      // falls back to the reach centerline when there are no polygons.
      const riparian = Object.values(d.riparian_geom || {}).filter(Boolean)[0];
      const resolved = Object.values(d.resolved || {}).filter(Boolean)[0];
      const highlight = riparian || resolved;
      if (context || highlight) dispatchEvent(new CustomEvent('mapagent:geom', { detail: { context, highlight } }));
      else dispatchEvent(new CustomEvent('mapagent:clear'));
      // The agent can toggle overlays (rf/fm/invasive) via map(action="layer", …).
      (d.map_actions || []).forEach((a: any) => {
        if (a && a.action === 'layer' && a.layer) {
          dispatchEvent(new CustomEvent('mapagent:layer', { detail: { layer: a.layer, visible: a.visible !== false } }));
        }
      });
      setMsgs((m) => [...m, { role: 'agent', text: d.answer || '(no answer)', steps: d.steps, cited: d.cited_sources }]);
    } catch {
      setMsgs((m) => [...m, { role: 'agent', text: 'The map agent is unreachable right now.' }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => logRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }));
    }
  }

  return (
    <div className="ma">
      <div className="ma-log" ref={logRef}>
        {msgs.length === 0 && (
          <div className="ma-intro">
            <p>
              This agent has riparian-extent data for the reaches the model mapped — pick one below,
              or ask in your own words. It resolves the place, queries the data, moves the map, and
              cites the source. Ask about a river it hasn't mapped (like the Animas) and it says so,
              instead of guessing. You can also say <em>"show me the invasive vegetation"</em> or
              <em>"compare RF and OlmoEarth"</em> to toggle the model overlays.
            </p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={'ma-msg ' + m.role}>
            {m.role === 'agent' && m.steps && m.steps.length > 0 && (
              <div className="ma-steps">{m.steps.map((s) => s.tool).join(' → ')}</div>
            )}
            <div className="ma-text">{m.text}</div>
            {m.cited && m.cited.length > 0 && <div className="ma-cite">source: {m.cited.join(', ')}</div>}
          </div>
        ))}
        {busy && (
          <div className="ma-msg agent"><div className="ma-text ma-busy">resolving…</div></div>
        )}
      </div>
      <details
        className="ma-picker"
        open={pickerOpen}
        onToggle={(e) => setPickerOpen((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>
          Mapped reaches{(reaches.length ? reaches : FALLBACK).length ? ` (${(reaches.length ? reaches : FALLBACK).length})` : ''} — ask about any
        </summary>
        <div className="ma-examples">
          {(reaches.length ? reaches : FALLBACK).map((r) => (
            <button
              key={r.name}
              className="ma-chip"
              onClick={() => ask(`How much of ${r.name} is riparian?`)}
              type="button"
            >
              {r.name}
              {r.reaches ? <span className="ma-count"> · {r.reaches} reaches</span> : null}
            </button>
          ))}
        </div>
      </details>
      <form className="ma-form" onSubmit={(e) => { e.preventDefault(); ask(val); }}>
        <input
          value={val}
          onChange={(e) => setVal(e.target.value)}
          placeholder="Ask the map…"
          aria-label="Ask the map a question"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !val.trim()}>Ask</button>
      </form>
    </div>
  );
}
