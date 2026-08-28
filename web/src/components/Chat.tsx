import { useEffect, useRef, useState, useCallback } from 'react';
import { turnstileToken } from '../scripts/turnstile';

// The grounded RAG agent, as a React island. It streams tokens from the full
// Quartzose /query/stream pipeline, renders numbered source chips, and lets the
// visitor switch the generation model (fast / balanced / OLMo). Map focus is
// decoupled: this island dispatches window events the map module listens for.

type Cite = { source_file: string; source_url: string | null };
type Geom = { mention_text?: string; ref?: string; geom?: any };
type Msg = {
  role: 'user' | 'assistant';
  text: string;
  streaming?: boolean;
  html?: string; // final rendered markdown
  standalone?: string; // for a follow-up: the query the agent resolved it to, using prior turns
  citations?: Cite[];
  geoms?: Geom[];
  offline?: boolean;
};
type Tier = { id: string; label: string; note: string; available: boolean };

const SUGGEST = [
  "What are the biggest threats to this project's central claim, and how does it defend against them?",
  'What did this project get wrong, and how did it catch it?',
  'Summarize the project: its methods, findings, and what makes it novel.',
  'How does OlmoEarth compare to the Random Forest?',
  'How was this agent built?',
];

const FALLBACK: { k: string[]; a: string }[] = [
  { k: ['invasive', 'corridor', '23', 'how much', 'percent', 'share'], a: 'About 23% of the mapped riparian corridor at Farmington is invasive tamarisk / Russian olive, 1.7 km² of invasive inside a 7.6 km² woody corridor. That figure is in-sample calibration to the 2020 NMRipMap labels, not an independent validation.' },
  { k: ['foundation', 'fm', 'beat', 'rf', 'random forest', 'tie', 'arroyo', 'malpais', 'olmoearth', 'distribution'], a: "On the three familiar reaches the two models essentially tie (about 0.85 to 0.90 AUC; OlmoEarth even trails slightly). The decisive result is the held-out unfamiliar reach, Malpais: the Random Forest collapses to a coin flip (0.557) while OlmoEarth holds (0.889). That result was re-verified: the Random-Forest scores reproduced on a re-run, and both models were scored on the same held-out pixels, so the comparison is valid and the number stands. What was retracted is only the \"desert arroyo\" label. Malpais is a river-dominated San-Juan-valley subwatershed (the attribution to arroyo morphology is unverified), and the mechanism is not arroyo terrain and not tamarisk (the Random Forest is near-chance on native and invasive vegetation alike, 0.59 vs 0.53). It is brittleness on unfamiliar ground, and that is exactly why OlmoEarth is the right model for the unlabeled basin: you pay for robustness on ground you can't hand-check." },
  { k: ['beetle', 'diorhabda', 'invert', 'inversion', 'control', 'russian olive'], a: "No inversion. Tamarisk-vs-native holds 0.85 / 0.81 / 0.86 across 2020 / 2015 / 2000. The pre-registered negative control (Russian olive) moved 0.34 over the same span, about seven times the tamarisk 'signal', so the data can't resolve a beetle effect. The control vetoes the claim." },
  { k: ['trajectory', '1990', 'pre-2000', 'over time', 'history', 'deep time', 'past', '5x', 'growth'], a: "I won't claim a pre-2000 trend. Window composites, indices and relative radiometric normalisation stabilised 2000 to 2010, but before ~2000 (pure Landsat-5 TM) single-year swings of ~1 percentage point swamp any trend, the apparent '5× growth' was an artifact of an under-sampled 1990. It's a documented negative; only the present-day product is reliable." },
  { k: ['ndvi', 'phenology', 'swir', 'senescen', 'season', 'signal', 'discriminat', 'spectral'], a: 'NDVI alone is nearly random for this (AUC ≈ 0.50). The discriminator is phenological: tamarisk greens and senesces on a different schedule than native cottonwood, with a distinct SWIR water signature, so the models get the full 12-month, 144-D spectro-temporal vector, not a greenness index.' },
];

import { citeUrlFor, mdToHtml } from '../lib/agent-format';

const stripSources = (t: string) => (t || '').replace(/\n{1,}\s*SOURCE:[\s\S]*$/i, '').replace(/\s+$/, '');

function fallbackAnswer(text: string): string {
  const t = text.toLowerCase(); let best: string | null = null, bs = 0;
  FALLBACK.forEach((it) => { let s = 0; it.k.forEach((k) => { if (t.indexOf(k) >= 0) s += k.length; }); if (s > bs) { bs = s; best = it.a; } });
  return bs > 0 ? (best as string) : "Offline right now, I can speak to what's on this page: the 23% invasive share, the RF-vs-OlmoEarth transfer test (OlmoEarth holds on the unfamiliar reach where the Random Forest collapses), the beetle control, the pre-2000 negative, or why NDVI isn't enough.";
}

// Cross-island bridge: tell the map module to focus / show geometry.
function emitAnswerToMap(text: string) { try { window.dispatchEvent(new CustomEvent('story:answer', { detail: { text } })); } catch {} }
function emitGeom(features: any[]) { try { window.dispatchEvent(new CustomEvent('story:geom', { detail: { features } })); } catch {} }

// Abort a fetch that stalls so the UI never gets stuck on "Connecting…" or busy.
// On timeout the fetch rejects (AbortError) and the caller's existing fallback runs.
function withTimeout(ms: number) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  return { signal: ctrl.signal, clear: () => clearTimeout(id) };
}

// (Removed the "what is this?" meta-intercept: it hardcoded an answer for any query
// containing "this project", which hijacked substantive questions like "the biggest
// threats to this project's claim". The corpus now has an about-doc and the retrieval
// layer anchors self-referential queries to the project, so the grounded, cited RAG
// answers these itself — which is the whole point.)

export default function Chat({ agentUrl = '/query' }: { agentUrl?: string }) {
  const [messages, setMessages] = useState<Msg[]>([
    { role: 'assistant', text: "I'm the assistant for this project. Ask about the riparian science and findings, how the maps were made, the RF-vs-OlmoEarth field test, the engineering method behind it, or how this agent itself was built. Tap a question below or type your own. When I'm live, answers are grounded in the sources with citations, and a reach mention flies the map; offline, you'll get short pre-written notes." },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [tier, setTier] = useState('balanced');
  const [tiers, setTiers] = useState<Tier[] | null>(null);
  const sessionRef = useRef('');
  const tierRef = useRef('balanced');
  const chatRef = useRef<HTMLDivElement>(null);
  const AGENT_URL = agentUrl;
  const isQuery = /\/query\/?$/.test(AGENT_URL);

  useEffect(() => { tierRef.current = tier; }, [tier]);
  const prevLenRef = useRef(messages.length);
  // On a NEW exchange, bring the just-asked question to the top of the panel so the
  // answer reads from its beginning as it streams — instead of pinning to the bottom
  // (which forced the reader to scroll up to the start of every answer). During
  // streaming (token updates keep the message count the same) we leave scroll put.
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    if (messages.length > prevLenRef.current) {
      const qs = el.querySelectorAll('.msg.u');
      const lastQ = qs[qs.length - 1] as HTMLElement | undefined;
      if (lastQ) {
        // Which element actually scrolls depends on the layout. On desktop .chat is
        // capped at 400px and scrolls inside itself; on mobile that cap is removed
        // (two nested scrollers fight each other on a phone) and the PAGE scrolls.
        // Calling scrollTo on a non-scrolling element is a silent no-op, which is
        // how the map agent ended up leaving new answers below the fold.
        const scrollsItself = el.scrollHeight > el.clientHeight + 1;
        if (scrollsItself) {
          el.scrollTo({ top: el.scrollTop + lastQ.getBoundingClientRect().top - el.getBoundingClientRect().top - 8, behavior: 'smooth' });
        } else {
          // Same intent, page-level: put the question you just asked at the top so
          // the answer streams in below it.
          lastQ.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    }
    prevLenRef.current = messages.length;
  }, [messages]);

  // Probe the agent + load model tiers. RE-PROBE periodically so a transient
  // backend blip (a brief restart or load spike) auto-recovers the "live" state
  // instead of latching the chat "offline" until a page reload.
  const modelsLoadedRef = useRef(false);
  useEffect(() => {
    if (!AGENT_URL) return;
    const healthUrl = AGENT_URL.replace(/\/(docs\/ask|query)\/?$/, '/health');
    let cancelled = false;
    // Re-fetch on every healthy probe so tier availability stays live — e.g. OLMo
    // flips to enabled the moment a provider serves it, which is what the UI copy
    // promises. Only the FIRST load sets the default tier; later refreshes update
    // availability without clobbering the visitor's current selection.
    const loadModels = () => {
      if (!isQuery) return;
      const url = AGENT_URL.replace(/\/query\/?$/, '/agent/models');
      const mt = withTimeout(8000);
      fetch(url, { signal: mt.signal }).then((r) => (r.ok ? r.json() : Promise.reject())).then((d) => {
        if (cancelled) return;
        if (!modelsLoadedRef.current && d?.default) { setTier(d.default); tierRef.current = d.default; }
        modelsLoadedRef.current = true;
        setTiers(d?.tiers || null);
      }).catch(() => {}).finally(() => mt.clear());
    };
    const probe = () => {
      const ht = withTimeout(8000);
      fetch(healthUrl, { signal: ht.signal }).then((r) => (r.ok ? r.json() : Promise.reject()))
        .then(() => { if (!cancelled) { setLive(true); loadModels(); } })
        .catch(() => { if (!cancelled) setLive(false); })
        .finally(() => ht.clear());
    };
    probe();
    const id = setInterval(probe, 25000);
    return () => { cancelled = true; clearInterval(id); };
  }, [AGENT_URL, isQuery]);

  const finalize = useCallback((text: string, citations: Cite[], geoms: Geom[]) => {
    const clean = stripSources(text);
    // Dedup/filter once here (citations already deduped upstream) so the render
    // doesn't repeat O(n²) passes on every re-render of the log.
    const shownGeoms = (geoms || []).filter((g) => g?.geom);
    setMessages((m) => {
      const copy = m.slice();
      copy[copy.length - 1] = { ...copy[copy.length - 1], role: 'assistant', text: clean, html: mdToHtml(clean || ''), citations, geoms: shownGeoms, streaming: false };
      return copy;
    });
    // A resolved geometry highlights the corridor map. Only fall back to
    // keyword-routing (which flies to a *different* map with no highlight layer)
    // when there is no resolved geometry to show.
    if (shownGeoms.length) {
      emitGeom(shownGeoms.map((g) => ({ type: 'Feature', geometry: g.geom, properties: {} })));
    } else {
      emitAnswerToMap(clean);
    }
  }, []);

  const askLiveStream = useCallback(async (q: string, onToken: (partial: string) => void, onRewrite?: (s: string) => void) => {
    const url = AGENT_URL.replace(/\/query\/?$/, '/query/stream');
    // Abort a stream that goes silent (no data for 30s) so the UI can't hang;
    // the timer resets on every chunk, so a long-but-active answer is fine.
    const ctrl = new AbortController();
    let idle: ReturnType<typeof setTimeout>;
    const bump = () => { clearTimeout(idle); idle = setTimeout(() => ctrl.abort(), 30000); };
    bump();
    try {
      const mint = await turnstileToken();
      const headers: Record<string, string> = { 'content-type': 'application/json' };
      if (mint.token) headers['X-Turnstile-Token'] = mint.token;
      const r = await fetch(url, { method: 'POST', headers, signal: ctrl.signal, body: JSON.stringify({ query: q, session_id: sessionRef.current || undefined, use_cache: true, model_tier: tierRef.current }) });
      if (!r.ok || !r.body) throw Object.assign(new Error('agent ' + r.status), { status: r.status, mintReason: mint.reason });
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '', full = ''; const ctx: any[] = [];
      for (;;) {
        const out = await reader.read(); if (out.done) break;
        bump();
        buf += dec.decode(out.value, { stream: true }); const blocks = buf.split('\n\n'); buf = blocks.pop() || '';
        for (const block of blocks) {
          let ev = 'message', data = '';
          block.split('\n').forEach((ln) => { if (ln.indexOf('event:') === 0) ev = ln.slice(6).trim(); else if (ln.indexOf('data:') === 0) data += ln.slice(5).trim(); });
          if (!data) continue; let d: any; try { d = JSON.parse(data); } catch { continue; }
          if (ev === 'token' && d.token) { full += d.token; onToken(full); }
          else if (ev === 'rewrite' && d.standalone && onRewrite) { onRewrite(d.standalone); }
          else if (ev === 'context') { if (Array.isArray(d)) ctx.push(...d); else if (d?.contexts) ctx.push(...d.contexts); else if (d) ctx.push(d); }
          else if (ev === 'done') { if (d.session_id) sessionRef.current = d.session_id; }
          else if (ev === 'error' || ev === 'security') throw new Error(d.error || 'blocked');
        }
      }
      const seen: Record<string, boolean> = {}; const cites: Cite[] = [];
      ctx.forEach((c) => { const s = (c?.metadata || {}).source_file || c?.source_file; if (s && !seen[s]) { seen[s] = true; cites.push({ source_file: s, source_url: citeUrlFor(s) }); } });
      return { answer: full, citations: cites };
    } finally {
      clearTimeout(idle);
    }
  }, [AGENT_URL]);

  const askLive = useCallback(async (q: string) => {
    const body = isQuery ? { query: q, session_id: sessionRef.current || undefined, use_cache: true, model_tier: tierRef.current } : { question: q, top_k: 8 };
    const t = withTimeout(60000);
    try {
      const mint = await turnstileToken();
      const headers: Record<string, string> = { 'content-type': 'application/json' };
      if (mint.token) headers['X-Turnstile-Token'] = mint.token;
      const r = await fetch(AGENT_URL, { method: 'POST', headers, signal: t.signal, body: JSON.stringify(body) });
      if (!r.ok) throw Object.assign(new Error('agent ' + r.status), { status: r.status, mintReason: mint.reason });
      const res = await r.json();
      if (isQuery) {
        if (res.session_id) sessionRef.current = res.session_id;
        const seen: Record<string, boolean> = {}; const cites: Cite[] = [];
        (res.contexts || []).forEach((c: any) => { const s = (c.metadata || {}).source_file; if (s && !seen[s]) { seen[s] = true; cites.push({ source_file: s, source_url: citeUrlFor(s) }); } });
        return { answer: res.answer, citations: cites, geoms: [] as Geom[] };
      }
      return res;
    } finally {
      t.clear();
    }
  }, [AGENT_URL, isQuery]);

  const answer = useCallback((text: string) => {
    if (busy) return;
    setBusy(true);
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '', streaming: true }]);
    if (!live) {
      setTimeout(() => { finalize(fallbackAnswer(text), [], []); setBusy(false); }, 200);
      return;
    }
    let standalone: string | undefined;
    const onToken = (partial: string) => setMessages((m) => { const c = m.slice(); c[c.length - 1] = { role: 'assistant', text: stripSources(partial), streaming: true, standalone }; return c; });
    const onRewrite = (s: string) => { standalone = s; setMessages((m) => { const c = m.slice(); c[c.length - 1] = { ...c[c.length - 1], standalone: s }; return c; }); };
    const run = isQuery ? askLiveStream(text, onToken, onRewrite) : askLive(text).then((res: any) => ({ answer: res.answer, citations: res.citations, geoms: res.resolved_geometries }));
    run.then((res: any) => finalize(res.answer || '(no answer returned)', res.citations || [], res.geoms || []))
      // A 403 is the bot check failing to mint a token, not the agent being down.
      // Saying "offline" there sends the reader to look for an outage that is not
      // happening, and hides the one thing that would fix it: reload the page.
      .catch((e: any) => {
        const denied = e?.status === 403;
        const why = e?.mintReason;
        finalize(fallbackAnswer(text) + (denied
          ? `\n\n(the bot check did not complete${why ? ` (${why})` : ''}, so that was a pre-written answer. Reload the page and ask again.)`
          : '\n\n(the live agent was unreachable just now, that was a pre-written answer.)'), [], []);
        if (!denied) setLive(false);
      })
      .finally(() => setBusy(false));
  }, [busy, live, isQuery, askLive, askLiveStream, finalize]);

  const go = () => { const v = input.trim(); if (!v || busy) return; setInput(''); answer(v); };

  // Contextual "ask" chips elsewhere on the page dispatch `story:ask`; when one
  // fires, scroll the agent into view and ask the question. answerRef keeps the
  // latest answer() so the once-registered listener never goes stale.
  const answerRef = useRef(answer);
  useEffect(() => { answerRef.current = answer; }, [answer]);
  useEffect(() => {
    let askTimer: ReturnType<typeof setTimeout>;
    const onAsk = (e: Event) => {
      const q = (e as CustomEvent)?.detail?.q;
      if (typeof q !== 'string' || !q) return;
      try { (document.querySelector('.qa') || document.getElementById('agent'))?.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch {}
      askTimer = setTimeout(() => answerRef.current(q), 450);
    };
    window.addEventListener('story:ask', onAsk as EventListener);
    return () => { clearTimeout(askTimer); window.removeEventListener('story:ask', onAsk as EventListener); };
  }, []);

  const olmo = tiers?.find((t) => t.id === 'olmo');
  const activeNote = tiers?.find((t) => t.id === tier)?.note || '';

  return (
    <div className="qa">
      <div className="qa-head">
        <div className="av">◑</div>
        <div><div className="t">Riparian document agent</div><div className="s">Hybrid RAG over the corpus + these findings</div></div>
        <div className={'live' + (live ? ' on' : '')} id="livebadge" title="agent status"><span className="pip"></span><span>{live ? 'live' : 'offline'}</span></div>
      </div>
      {tiers && (
        <div className="modelbar">
          <span className="ml">Model</span>
          <div className="seg" role="radiogroup" aria-label="Answer model">
            {tiers.map((t) => (
              <button key={t.id} role="radio" aria-checked={t.id === tier} disabled={!t.available}
                className={t.id === tier ? 'on' : ''}
                title={!t.available ? "OLMo isn't being served right now; this switch goes live the moment a host (Ai2 / OpenRouter) serves it." : undefined}
                onClick={() => { if (t.available && !busy) setTier(t.id); }}>
                {t.id === 'olmo' && <span className={'sd ' + (t.available ? 'up' : 'down')}></span>}
                <span>{t.label}</span>
              </button>
            ))}
          </div>
          <span className="mnote">{activeNote}</span>
        </div>
      )}
      {olmo && !olmo.available && (
        <div className="moffline">
          <b>OLMo is disabled</b> — no live OpenRouter endpoint yet (0 providers serve it); runs on another open model meanwhile and enables automatically when one goes live.
        </div>
      )}
      <div className="chat" ref={chatRef} role="log" aria-live="polite" aria-atomic="false">
        {messages.map((m, i) => (
          <div key={i} className={'msg ' + (m.role === 'user' ? 'u' : 'a') + (m.streaming && !m.text ? ' think' : '') + (m.streaming && m.text ? ' streaming' : '')}>
            {m.role === 'assistant' ? (
              (m.streaming && !m.text) ? '…thinking' : (
                <>
                  {m.standalone && (
                    <div className="rewrite" title="A follow-up, resolved using the conversation so far">↳ {m.standalone}</div>
                  )}
                  {/* Render markdown LIVE while streaming: m.html is set only at
                      finalize, so until then parse the partial each tick so bold,
                      lists, tables and links appear as they arrive, not all at once. */}
                  <div className="md" dangerouslySetInnerHTML={{ __html: m.html || mdToHtml(m.text) }} />
                  {!m.streaming && m.citations && m.citations.length > 0 && (
                    <div className="cites">
                      <span className="citehead">Sources</span>
                      {m.citations.map((c, k) => {
                        const label = '[' + (k + 1) + '] ' + c.source_file.replace(/^(findings|project)-/, '').replace(/\.(md|pdf|html?)$/, '');
                        return c.source_url ? <a key={k} className="cite" href={c.source_url} target="_blank" rel="noopener noreferrer">{label}</a> : <span key={k} className="cite">{label}</span>;
                      })}
                    </div>
                  )}
                  {!m.streaming && m.geoms && m.geoms.length > 0 && (
                    <div className="cites">
                      {m.geoms.map((g, k) => (
                        <span key={k} className="geo" onClick={() => emitGeom([{ type: 'Feature', geometry: g.geom, properties: {} }])}>📍 {g.mention_text || g.ref || 'location'}</span>
                      ))}
                    </div>
                  )}
                </>
              )
            ) : (
              m.text
            )}
          </div>
        ))}
        {/* Suggestions live in the empty/starter state, inside the log, so they're
            not sandwiched between the output and the input once a chat is going. */}
        {messages.length <= 1 && !busy && (
          <div className="qs qs-starter">
            <span className="qs-label">Try asking</span>
            {SUGGEST.map((q) => (<button key={q} onClick={() => { if (!busy) answer(q); }}>{q}</button>))}
          </div>
        )}
      </div>
      <div className="askrow">
        <input value={input} disabled={busy} onChange={(e) => setInput((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => { if (e.key === 'Enter') go(); }}
          type="text" placeholder="e.g. how much of the corridor is invasive?" aria-label="Ask a question" />
        <button onClick={go} disabled={busy}>Ask</button>
      </div>
      <div className="disc">
        {live
          ? 'Live: answers are generated by the model you select, grounded in the watershed corpus, with clickable citations.'
          : 'Offline: pre-written answers about this page. The live agent (grounded + cited) turns on when its endpoint is configured.'}
      </div>
    </div>
  );
}
