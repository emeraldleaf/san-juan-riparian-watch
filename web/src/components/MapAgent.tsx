// The "ask the map" chat island. Posts a plain-language question to /agent/map,
// renders the cited answer + the tool trace, and hands the resolved geometry to
// the imperative map (map-agent-client.ts) via a window CustomEvent. Same seam the
// story maps use: React fetches, the map listens.
import { useRef, useState } from 'react';

type Msg = { role: 'user' | 'agent'; text: string; steps?: { tool: string }[]; cited?: string[] };

const EXAMPLES = [
  'How much of the San Juan River corridor is riparian?',
  'How much of the Animas River is riparian?',
  'Show me the riparian extent near Kirtland.',
];

export default function MapAgent() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [val, setVal] = useState('');
  const logRef = useRef<HTMLDivElement>(null);

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setVal('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    try {
      const r = await fetch('/agent/map', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      const d = await r.json();
      const geoms = Object.values(d.resolved || {}).filter(Boolean);
      if (geoms.length) dispatchEvent(new CustomEvent('mapagent:geom', { detail: { geometry: geoms[0] } }));
      else dispatchEvent(new CustomEvent('mapagent:clear'));
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
              Ask about riparian extent anywhere in the San Juan basin. The agent resolves the place,
              queries the data, moves the map, and cites the source — and tells you plainly when the
              product does not cover an area, rather than guessing a number.
            </p>
            <div className="ma-examples">
              {EXAMPLES.map((e) => (
                <button key={e} className="ma-chip" onClick={() => ask(e)} type="button">{e}</button>
              ))}
            </div>
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
