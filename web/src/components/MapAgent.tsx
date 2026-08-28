// The "ask the map" chat island. Two modes, one conversation:
//  • Q&A — posts a question to /agent/map, renders the cited answer + tool trace,
//    and hands the resolved geometry to the imperative map (map-agent-client.ts).
//  • Presentation — an agent-narrated keynote where the slides ARE the map. The
//    map client owns the scenes (camera + layers); this panel shows the narration
//    beat by beat and lets you pause, ask, and continue — all in the same thread.
import { useEffect, useRef, useState } from 'react';
import { turnstileToken, lastTurnstileFailure } from '../scripts/turnstile';
import { citeUrlFor, mdToHtml } from '../lib/agent-format';

type Msg = { role: 'user' | 'agent'; text: string; steps?: { tool: string }[]; cited?: string[]; pres?: boolean;
  // Layers this answer switched on — offered as explicit "Zoom to" buttons rather
  // than moving the camera automatically. The user decides when to travel.
  zoomTo?: { layer: string; label: string }[] };
type Reach = { name: string; reaches: number };
type Scene = { index: number; total: number; title: string; phenology?: boolean };

// Human labels for the overlay ids the agent can switch on.
const LAYER_LABEL: Record<string, string> = {
  rf: 'the Random Forest riparian layer',
  fm: 'the OlmoEarth riparian layer',
  invasive: 'the invasive layer',
  truth: 'the NMRipMap truth layer',
};

// One conversation per page load. Sent with every question so the agent can see its
// own prior turns — without it, "give me a list of those" has no referent and the
// agent can only ask what you meant.
//
// It must come from a CSPRNG: this id is the key to a conversation's stored history,
// so a guessable one would let a visitor load someone else's. If no CSPRNG exists we
// send NO id and the agent answers statelessly — degraded but private. Never a shared
// constant, which would merge every such visitor into one conversation.
function newSessionId(): string | undefined {
  const c = typeof crypto !== 'undefined' ? crypto : undefined;
  if (c?.randomUUID) return c.randomUUID();
  if (c?.getRandomValues) {
    return Array.from(c.getRandomValues(new Uint8Array(16)))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  }
  return undefined;
}
const SESSION_ID = newSessionId();

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

  // Pin to the bottom whenever the log changes — as an effect (after the DOM has
  // committed the new, possibly-tall message), so it always lands at the true
  // bottom rather than a stale height. A trailing rAF covers late layout.
  useEffect(() => {
    const el = logRef.current;
    if (!el) return;

    // Two layouts, two scrollers. On desktop .ma-panel has a bounded height so the
    // log scrolls INSIDE itself. On mobile the grid row is `auto`, so the log has no
    // height to overflow — it just grows and the PAGE scrolls. Pinning scrollTop
    // there is a no-op, which is why a phone left the newest answer far below the
    // map with nothing bringing it into view.
    const pin = () => {
      const scrollsItself = el.scrollHeight > el.clientHeight + 1;
      if (scrollsItself) {
        el.scrollTop = el.scrollHeight;
      } else {
        // The page is the scroller: bring the newest message to the viewport.
        // block:'nearest' scrolls the minimum needed, so it never yanks the map
        // off-screen when the answer was already visible.
        el.lastElementChild?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    };
    pin();
    const id = requestAnimationFrame(pin);   // covers late layout (images, tables)
    return () => cancelAnimationFrame(id);
  }, [msgs, busy, pausedForAsk]);

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
    };
    const onMonth = (e: any) => setMonth({ index: e.detail?.index ?? 0, label: e.detail?.label ?? '' });
    const onState = (e: any) => setPresPlaying(!!e.detail?.playing);
    const onEnd = () => {
      setPresenting(false); setPresPlaying(false); setScene(null); setPausedForAsk(false);
      setMsgs((m) => [...m, { role: 'agent', text: "That's the walkthrough. Ask me anything about it, or explore the layers yourself." }]);
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
      const r = await fetch('/agent/map', { method: 'POST', headers, body: JSON.stringify(SESSION_ID ? { question: q, session_id: SESSION_ID } : { question: q }), signal: AbortSignal.timeout(30000) });
      // 403 here means the bot check did not mint a token, NOT that the agent is down.
      if (!r.ok) throw Object.assign(new Error(`agent responded ${r.status}`), { status: r.status });
      const d = await r.json();
      const context = Object.values(d.display_geom || {}).filter(Boolean)[0];
      const riparian = Object.values(d.riparian_geom || {}).filter(Boolean)[0];
      const resolved = Object.values(d.resolved || {}).filter(Boolean)[0];
      const highlight = riparian || resolved;
      if (context || highlight) dispatchEvent(new CustomEvent('mapagent:geom', { detail: { context, highlight } }));
      else dispatchEvent(new CustomEvent('mapagent:clear'));
      // The agent can toggle overlays (rf/fm/invasive) via map(action="layer", …).
      // Turning one on does NOT move the camera; instead each switched-on layer
      // becomes a "Zoom to" button under the answer.
      const turnedOn: { layer: string; label: string }[] = [];
      (d.map_actions || []).forEach((a: any) => {
        if (a && a.action === 'layer' && a.layer) {
          const visible = a.visible !== false;
          dispatchEvent(new CustomEvent('mapagent:layer', { detail: { layer: a.layer, visible } }));
          if (visible) turnedOn.push({ layer: a.layer, label: LAYER_LABEL[a.layer] || a.layer });
        }
      });
      setMsgs((m) => [...m, { role: 'agent', text: d.answer || '(no answer)', steps: d.steps,
        cited: d.cited_sources, zoomTo: turnedOn.length ? turnedOn : undefined }]);
    } catch (e: any) {
      const why = lastTurnstileFailure();
      setMsgs((m) => [...m, { role: 'agent', text: e?.status === 403
        ? `The bot check did not complete${why ? ` (${why})` : ''}. Reload the page and ask again.`
        : 'The map agent is unreachable right now.' }]);
    } finally {
      setBusy(false);
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
            {m.role === 'agent' && !m.pres
              ? <div className="ma-text md" dangerouslySetInnerHTML={{ __html: mdToHtml(m.text) }} />
              : <div className="ma-text">{m.text}</div>}
            {m.cited && m.cited.length > 0 && (
              <div className="ma-cite">
                source:{' '}
                {m.cited.map((c, j) => {
                  const href = citeUrlFor(c);
                  return (
                    <span key={c}>
                      {j > 0 && ', '}
                      {href
                        ? <a href={href} target="_blank" rel="noopener noreferrer">{c}</a>
                        : c}
                    </span>
                  );
                })}
              </div>
            )}
            {m.zoomTo && m.zoomTo.length > 0 && (
              <div className="ma-zoomrow">
                {m.zoomTo.map((z) => (
                  <button
                    key={z.layer}
                    className="ma-zoom"
                    type="button"
                    onClick={() => dispatchEvent(new CustomEvent('mapagent:zoomto', { detail: { layer: z.layer } }))}
                  >⤢ Zoom to {z.label}</button>
                ))}
              </div>
            )}
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
          <summary>What you can ask</summary>
          <div className="ma-examples">
            {msgs.length > 0 && (
              <button className="ma-chip ma-chip-present" onClick={startPresentation} type="button">▶ Walkthrough</button>
            )}
            {/* Capability chips: one per thing the agent genuinely does — a measured
                number, an overlay, a head-to-head, and an honest refusal. Better than
                N copies of the same question with a different place name. */}
            <button className="ma-chip" onClick={() => ask('Show me the invasive vegetation')} type="button">Show the invasive layer</button>
            <button className="ma-chip" onClick={() => ask('Compare the Random Forest and OlmoEarth riparian maps')} type="button">Compare RF vs OlmoEarth</button>
            {items[0] && (
              <button className="ma-chip" onClick={() => ask(`How much riparian is along ${items[0].name}?`)} type="button">
                Riparian acres along {items[0].name}
              </button>
            )}
            <button className="ma-chip" onClick={() => ask('How much of the corridor is invasive?')} type="button">How much is invasive?</button>
          </div>
          {items.length > 1 && (
            <div className="ma-examples ma-places">
              <span className="ma-places-label">…or a place:</span>
              {items.slice(1).map((r) => (
                <button key={r.name} className="ma-chip ma-chip-quiet" onClick={() => ask(`How much riparian is along ${r.name}?`)} type="button">
                  {r.name}
                </button>
              ))}
            </div>
          )}
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
