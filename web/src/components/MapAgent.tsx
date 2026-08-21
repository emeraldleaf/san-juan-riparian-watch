// The "ask the map" chat island. Two modes, one conversation:
//  • Q&A — posts a question to /agent/map, renders the cited answer + tool trace,
//    and hands the resolved geometry to the imperative map (map-agent-client.ts).
//  • Presentation — an agent-narrated keynote where the slides ARE the map. The
//    map client owns the scenes (camera + layers); this panel shows the narration
//    beat by beat and lets you pause, ask, and continue — all in the same thread.
import { useEffect, useRef, useState } from 'react';
import { turnstileToken } from '../scripts/turnstile';

type Msg = { role: 'user' | 'agent'; text: string; steps?: { tool: string }[]; cited?: string[]; pres?: boolean };
type Reach = { name: string; reaches: number };
type Scene = { index: number; total: number; title: string; phenology?: boolean };

const FALLBACK: Reach[] = [
  { name: 'San Juan River', reaches: 0 },
  { name: 'Malpais Arroyo', reaches: 0 },
];

export default function MapAgent() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [val, setVal] = useState('');
  const [reaches, setReaches] = useState<Reach[]>([]);
  const [pickerOpen, setPickerOpen] = useState(true);
  // Presentation state
  const [presenting, setPresenting] = useState(false);
  const [presPlaying, setPresPlaying] = useState(false);
  const [scene, setScene] = useState<Scene | null>(null);
  const [month, setMonth] = useState<{ index: number; label: string }>({ index: 0, label: 'Jan' });
  const [pausedForAsk, setPausedForAsk] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  const scrollDown = () =>
    requestAnimationFrame(() => logRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }));

  useEffect(() => {
    fetch('/agent/map/coverage')
      .then((r) => (r.ok ? r.json() : { reaches: [] }))
      .then((d) => setReaches(Array.isArray(d.reaches) ? d.reaches : []))
      .catch(() => {});
  }, []);

  // The map client drives the scenes; we render each narration beat as an agent
  // message so the whole walkthrough reads as one conversation.
  useEffect(() => {
    const onScene = (e: any) => {
      const d = e.detail || {};
      setPresenting(true);
      setPresPlaying(!!d.playing);
      setScene({ index: d.index, total: d.total, title: d.title, phenology: !!d.phenology });
      setMsgs((m) => [...m, { role: 'agent', text: d.narration, pres: true }]);
      scrollDown();
    };
    const onMonth = (e: any) => setMonth({ index: e.detail?.index ?? 0, label: e.detail?.label ?? '' });
    const onState = (e: any) => setPresPlaying(!!e.detail?.playing);
    const onEnd = () => {
      setPresenting(false); setPresPlaying(false); setScene(null); setPausedForAsk(false);
      setMsgs((m) => [...m, { role: 'agent', text: "That's the walkthrough. Ask me anything about it, or explore the layers yourself." }]);
      scrollDown();
    };
    addEventListener('pres:scene', onScene);
    addEventListener('pres:month', onMonth);
    addEventListener('pres:state', onState);
    addEventListener('pres:end', onEnd);
    return () => {
      removeEventListener('pres:scene', onScene);
      removeEventListener('pres:month', onMonth);
      removeEventListener('pres:state', onState);
      removeEventListener('pres:end', onEnd);
    };
  }, []);

  function startPresentation() {
    setMsgs((m) => [...m, { role: 'user', text: 'Walk me through how you found the riparian.' }]);
    dispatchEvent(new CustomEvent('pres:start'));
  }
  function continuePresentation() {
    setPausedForAsk(false);
    dispatchEvent(new CustomEvent('pres:play'));
  }

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    // Asking during a presentation pauses it; a "Continue" prompt appears after.
    if (presenting) {
      dispatchEvent(new CustomEvent('pres:pause'));
      setPausedForAsk(true);
    }
    setVal('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    try {
      const token = await turnstileToken();
      const headers: Record<string, string> = { 'content-type': 'application/json' };
      if (token) headers['X-Turnstile-Token'] = token;
      const r = await fetch('/agent/map', { method: 'POST', headers, body: JSON.stringify({ question: q }) });
      const d = await r.json();
      const context = Object.values(d.display_geom || {}).filter(Boolean)[0];
      const riparian = Object.values(d.riparian_geom || {}).filter(Boolean)[0];
      const resolved = Object.values(d.resolved || {}).filter(Boolean)[0];
      const highlight = riparian || resolved;
      if (context || highlight) dispatchEvent(new CustomEvent('mapagent:geom', { detail: { context, highlight } }));
      else dispatchEvent(new CustomEvent('mapagent:clear'));
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
      scrollDown();
    }
  }

  const items = reaches.length ? reaches : FALLBACK;

  return (
    <div className="ma">
      <div className="ma-log" ref={logRef}>
        {msgs.length === 0 && (
          <div className="ma-intro">
            <p>
              A guided, agent-narrated tour of how this project maps riparian vegetation — or ask your
              own questions. Start the walkthrough and the map presents itself, scene by scene; pause any
              time to ask, then continue.
            </p>
            <button className="ma-present-cta" onClick={startPresentation} type="button">
              ▶ How we found the riparian
            </button>
            <p className="ma-intro-sub">
              Or just ask — <em>"how much of the San Juan River is riparian?"</em>,
              <em> "show me the invasive vegetation"</em>, <em>"compare RF and OlmoEarth"</em>.
            </p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={'ma-msg ' + m.role + (m.pres ? ' pres' : '')}>
            {m.role === 'agent' && m.steps && m.steps.length > 0 && (
              <div className="ma-steps">{m.steps.map((s) => s.tool).join(' → ')}</div>
            )}
            <div className="ma-text">{m.text}</div>
            {m.cited && m.cited.length > 0 && <div className="ma-cite">source: {m.cited.join(', ')}</div>}
          </div>
        ))}
        {busy && <div className="ma-msg agent"><div className="ma-text ma-busy">resolving…</div></div>}
        {presenting && pausedForAsk && !busy && (
          <button className="ma-continue" onClick={continuePresentation} type="button">
            ▶ Continue the presentation
          </button>
        )}
      </div>

      {presenting ? (
        <div className="ma-presbar">
          {scene?.phenology && (
            <div className="ma-monthrow">
              <span className="ma-monthkey">◐ color-infrared · vegetation = red</span>
              <input
                type="range" min={0} max={11} value={month.index} className="ma-monthslider"
                onChange={(e) => dispatchEvent(new CustomEvent('pres:setmonth', { detail: { index: +e.currentTarget.value } }))}
                aria-label="Scrub month"
              />
              <span className="ma-monthlbl">{month.label}</span>
            </div>
          )}
          <span className="ma-presttl">{scene?.title}</span>
          <span className="ma-presnum">Scene {(scene?.index ?? 0) + 1} / {scene?.total ?? 0}</span>
          <div className="ma-presctl">
            <button onClick={() => dispatchEvent(new CustomEvent('pres:prev'))} aria-label="Previous scene" type="button">⏮</button>
            <button
              onClick={() => dispatchEvent(new CustomEvent(presPlaying ? 'pres:pause' : 'pres:play'))}
              aria-label={presPlaying ? 'Pause' : 'Play'} type="button"
            >{presPlaying ? '⏸' : '▶'}</button>
            <button onClick={() => dispatchEvent(new CustomEvent('pres:next'))} aria-label="Next scene" type="button">⏭</button>
            <button className="ma-presexit" onClick={() => dispatchEvent(new CustomEvent('pres:exit'))} type="button">Exit</button>
          </div>
        </div>
      ) : (
        <details className="ma-picker" open={pickerOpen} onToggle={(e) => setPickerOpen((e.currentTarget as HTMLDetailsElement).open)}>
          <summary>Mapped reaches{items.length ? ` (${items.length})` : ''} — ask about any</summary>
          <div className="ma-examples">
            {msgs.length > 0 && (
              <button className="ma-chip ma-chip-present" onClick={startPresentation} type="button">▶ Walkthrough</button>
            )}
            {items.map((r) => (
              <button key={r.name} className="ma-chip" onClick={() => ask(`How much of ${r.name} is riparian?`)} type="button">
                {r.name}{r.reaches ? <span className="ma-count"> · {r.reaches} reaches</span> : null}
              </button>
            ))}
          </div>
        </details>
      )}

      <form className="ma-form" onSubmit={(e) => { e.preventDefault(); ask(val); }}>
        <input
          value={val}
          onChange={(e) => setVal(e.target.value)}
          placeholder={presenting ? 'Pause and ask a question…' : 'Ask the map…'}
          aria-label="Ask the map a question"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !val.trim()}>Ask</button>
      </form>
    </div>
  );
}
