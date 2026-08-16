import { useEffect, useRef, useState, useCallback } from 'react';

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
  citations?: Cite[];
  geoms?: Geom[];
  offline?: boolean;
};
type Tier = { id: string; label: string; note: string; available: boolean };

const SUGGEST = [
  'How much of the corridor is invasive?',
  'Does the foundation model beat the RF on the arroyo?',
  'Did the tamarisk beetle break the classifier?',
  "Why won't you claim a pre-2000 trajectory?",
  'Why is NDVI not enough?',
];

const FALLBACK: { k: string[]; a: string }[] = [
  { k: ['invasive', 'corridor', '23', 'how much', 'percent', 'share'], a: 'About 23% of the mapped riparian corridor at Farmington is invasive tamarisk / Russian olive, 1.7 km² of invasive inside a 7.6 km² woody corridor. That figure is in-sample calibration to the 2020 NMRipMap labels, not an independent validation.' },
  { k: ['foundation', 'fm', 'beat', 'rf', 'random forest', 'tie', 'arroyo', 'malpais', 'olmoearth'], a: 'On the four river-corridor reaches they tie at ~0.80–0.88 AUC. They part on the lone arroyo (Malpais): RF transfers at 0.557 (barely above random), the fine-tuned foundation model at 0.889. That under-represented morphology, the one landform type the RF had no training sibling for, is why the foundation model ships for the invasive task; for plain extent, RF is as good and needs no GPU.' },
  { k: ['beetle', 'diorhabda', 'invert', 'inversion', 'control', 'russian olive'], a: "No inversion. Tamarisk-vs-native holds 0.85 / 0.81 / 0.86 across 2020 / 2015 / 2000. The pre-registered negative control (Russian olive) moved 0.34 over the same span, about seven times the tamarisk 'signal', so the data can't resolve a beetle effect. The control vetoes the claim." },
  { k: ['trajectory', '1990', 'pre-2000', 'over time', 'history', 'deep time', 'past', '5x', 'growth'], a: "We won't claim a pre-2000 trajectory. Window composites, indices and relative radiometric normalisation stabilised 2000–2010, but before ~2000 (pure Landsat-5 TM) single-year swings of ~1 percentage point swamp any trend, the apparent '5× growth' was an artifact of an under-sampled 1990. It's a documented negative; only the present-day product is reliable." },
  { k: ['ndvi', 'phenology', 'swir', 'senescen', 'season', 'signal', 'discriminat', 'spectral'], a: 'NDVI alone is nearly random for this (AUC ≈ 0.50). The discriminator is phenological: tamarisk greens and senesces on a different schedule than native cottonwood, with a distinct SWIR water signature, so the models get the full 12-month, 144-D spectro-temporal vector, not a greenness index.' },
];

const CITE_PAPERS: Record<string, string> = {
  'diao-wang-saltcedar-phenological-trajectory': 'https://www.sciencedirect.com/science/article/abs/pii/S0034425716301924',
  'dargana-earthpt-canopy-finetune': 'https://arxiv.org/abs/2504.17321',
  'tamarix-genotypes-sentinel2-rf': 'https://peerj.com/articles/15027/',
  'wetland-sparse-annotations-temporal-sam': 'https://doi.org/10.48550/arXiv.2601.11400',
  'usgs-ofr-2018-1070-beetle-population-dynamics-san-juan': 'https://pubs.usgs.gov/publication/ofr20181070',
  'usgs-tamarisk-beetle-grand-canyon-412km': 'https://doi.org/10.1016/j.ecolind.2018.02.026',
  'usgs-tamarisk-defoliation-landsat5-detection': 'https://doi.org/10.2747/1548-1603.49.4.510',
  'usgs-tamarisk-beetle-expert-panel-synthesis': 'https://pubs.usgs.gov/publication/70168717',
  'corip-dryad-dataset': 'https://doi.org/10.5061/dryad.3g55sv8',
  'csu-nrel-crb-invasive-occurrence-2018': 'https://www.nrel.colostate.edu/improved-rip-maps-crb/',
  'sjrip-habitat-restoration-index': 'https://coloradoriverrecovery.org/sj/science/technical-reports/habitat-restoration/',
  'sjrip-bassett-2015-historical-ecology-riparian': 'https://coloradoriverrecovery.org/sj/wp-content/uploads/sites/3/2022/08/Bassett_2015_San_Juan_River_Historical_Ecology_Assessment_Riparian_Vegetation-508ish-1.pdf',
  'sjrip-standardized-monitoring-5yr-2006': 'https://coloradoriverrecovery.org/sj/wp-content/uploads/sites/3/2022/04/data_Standardized_Monitoring_Program_Five_Year_Integration_Report_2006_OCR.pdf',
  'epa-san-juan-watershed-state-tribal-projects': 'https://www.epa.gov/san-juan-watershed/san-juan-watershed-program-state-and-tribal-projects',
  'epa-san-juan-watershed-funded-projects-2017-2021': 'https://www.epa.gov/system/files/documents/2022-08/12355_San%20Juan%20Program%20FctS%20Funded%20Projects%20June%202022%20508.pdf',
  'nmed-sjb-watershed-plan-2005': 'https://www.env.nm.gov/wp-content/uploads/sites/25/2019/10/SanJuanBasinWatershedPlan01-11-05.pdf',
  'fws-ea-colorado-san-juan-recovery-2023': 'https://www.fws.gov/sites/default/files/documents/202312_Draft_EA_Colorado_River_Recovery_Programs_forPublicComment.pdf',
  'usbr-cwmp-phase1-sjswcd-2018': 'https://www.usbr.gov/watersmart/cwmp/docs/2018/applications/phase1/029-CWMP-SJSWCD.ARC_508.pdf',
  'co-san-juan-dolores-planning-model-manual': 'https://hermes.cde.state.co.us/islandora/object/co:36950/datastream/OBJ/download/San_Juan__Dolores_River_Basin_water_resources_planning_model_user_s_manual.pdf',
  'olmoearth-mangrove-recipe': 'https://github.com/allenai/olmoearth_projects/blob/main/docs/mangrove.md',
};

// project-* corpus docs live in the public repo's docs/. Those in a subdir
// (specs / decisions / audits) are mapped here, since the backend sends only
// source_file, not the path — anything not listed is a docs/ top-level file.
// (Keep in sync with the repo's docs/ layout; a wrong/missing entry 404s.)
const DOC_SUBDIR: Record<string, string> = {
  '2026-07-03-stage1-riparian-delineation': 'specs/',
  '2026-07-04-document-intelligence-rag': 'specs/',
  '2026-07-04-stage3-annual-change': 'specs/',
  '2026-07-11-stage2-invasives-tamarix': 'specs/',
  '2026-07-12-gpu-finetune-execution-plan': 'specs/',
  '2026-07-18-phase3-deeptime-change': 'specs/',
  '2026-07-19-fm-vs-rf-deploy-decision': 'specs/',
  '2026-08-01-stage2-invasives-beetle-gate': 'specs/',
  '2026-07-03-delineation-over-hydrology-buffers': 'decisions/',
  '2026-07-04-document-intelligence-subsystem': 'decisions/',
  '2026-07-04-nextaurora-rules-applicability': 'decisions/',
  '2026-07-11-confidence-weighted-label-crosswalk': 'decisions/',
  '2026-07-11-model-and-inference-hosting': 'decisions/',
  '2026-07-12-beetle-training-pool-ecoregion-matched': 'decisions/',
  '2026-07-12-olmoearth-finetune-invasives-with-extent-control': 'decisions/',
  '2026-07-11-corip-woodward-2018': 'audits/',
  '2026-07-11-tamarisk-detection-established': 'audits/',
  '2026-07-12-evangelista-2018-csu-nrel': 'audits/',
  '2026-07-12-perkins-2025-canyonlands': 'audits/',
  '2026-07-14-riparian-methods-prior-art': 'audits/',
  '2026-07-16-DECISION-MEMO-olmoearth-gpu': 'audits/',
  '2026-07-16-cross-tile-transfer-results': 'audits/',
  '2026-07-16-finetune-transfer-results': 'audits/',
  '2026-07-16-label-budget-sweep-results': 'audits/',
  '2026-07-16-malpais-reach-generalization-note': 'audits/',
  '2026-07-16-presto-arm-results': 'audits/',
  '2026-07-16-presto-species-results': 'audits/',
  '2026-07-16-riparian-fm-methods-review': 'audits/',
  '2026-07-16-three-tile-transfer-results': 'audits/',
  '2026-07-17-cropglobe-tong-2025': 'audits/',
};
const DOCS_BASE = 'https://github.com/emeraldleaf/san-juan-riparian-watch/blob/main/docs/';

function citeUrlFor(src: string): string | null {
  if (!src) return null;
  const stem = src.replace(/\.(md|pdf|html?)$/, '');
  if (CITE_PAPERS[stem]) return CITE_PAPERS[stem];
  if (stem.indexOf('findings-') === 0)
    return DOCS_BASE + stem.replace(/^findings-/, '') + '.md';
  if (stem.indexOf('project-') === 0) {
    const name = stem.replace(/^project-/, '');
    return DOCS_BASE + (DOC_SUBDIR[name] || '') + name + '.md';
  }
  return null;
}

// Escape ALL HTML-significant chars incl. quotes — the result is assigned via
// dangerouslySetInnerHTML, so an unescaped " in a model-supplied link URL could
// break out of href and inject an attribute. escH runs before mdInline, so by
// the time links are built the URL can no longer contain a raw quote or angle.
const escH = (s: string) =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
function mdInline(s: string): string {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)"'<>]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}
function mdToHtml(md: string): string {
  const lines = escH(md).replace(/\r/g, '').split('\n');
  const out: string[] = [];
  let i = 0;
  const n = lines.length;
  const isSep = (l: string) => l.indexOf('-') >= 0 && /^\s*\|?[\s:|-]*\|?\s*$/.test(l);
  const cells = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((x) => mdInline(x.trim()));
  while (i < n) {
    const line = lines[i];
    if (/^\s*$/.test(line)) { i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < n && isSep(lines[i + 1])) {
      const head = cells(line); i += 2; const rows: string[][] = [];
      while (i < n && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
      out.push('<table><thead><tr>' + head.map((c) => '<th>' + c + '</th>').join('') + '</tr></thead><tbody>' +
        rows.map((r) => '<tr>' + r.map((c) => '<td>' + c + '</td>').join('') + '</tr>').join('') + '</tbody></table>');
      continue;
    }
    const h = line.match(/^\s*#{1,6}\s+(.*)$/);
    if (h) { out.push('<h4>' + mdInline(h[1].trim()) + '</h4>'); i++; continue; }
    if (/^\s*\d+\.\s+/.test(line)) { const it: string[] = [];
      while (i < n && /^\s*\d+\.\s+/.test(lines[i])) { it.push('<li>' + mdInline(lines[i].replace(/^\s*\d+\.\s+/, '')) + '</li>'); i++; }
      out.push('<ol>' + it.join('') + '</ol>'); continue; }
    if (/^\s*[-*+]\s+/.test(line)) { const it2: string[] = [];
      while (i < n && /^\s*[-*+]\s+/.test(lines[i])) { it2.push('<li>' + mdInline(lines[i].replace(/^\s*[-*+]\s+/, '')) + '</li>'); i++; }
      out.push('<ul>' + it2.join('') + '</ul>'); continue; }
    const para = [line]; i++;
    while (i < n && !/^\s*$/.test(lines[i]) && !/^\s*(\d+\.|[-*+]|#{1,6})\s+/.test(lines[i]) && !/^\s*\|.*\|\s*$/.test(lines[i])) { para.push(lines[i]); i++; }
    out.push('<p>' + mdInline(para.join(' ')) + '</p>');
  }
  return out.join('');
}
const stripSources = (t: string) => (t || '').replace(/\n{1,}\s*SOURCE:[\s\S]*$/i, '').replace(/\s+$/, '');

function fallbackAnswer(text: string): string {
  const t = text.toLowerCase(); let best: string | null = null, bs = 0;
  FALLBACK.forEach((it) => { let s = 0; it.k.forEach((k) => { if (t.indexOf(k) >= 0) s += k.length; }); if (s > bs) { bs = s; best = it.a; } });
  return bs > 0 ? (best as string) : "Offline right now, I can speak to what's on this page: the 23% invasive share, the RF-vs-foundation-model arroyo split, the beetle control, the pre-2000 negative, or why NDVI isn't enough.";
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

// Meta-questions about the project/site itself ("what is this?", "how was this
// developed?") aren't in the watershed-literature corpus, so retrieval grabs a
// tangential "…Project is…" match. Answer those from the project's own description.
const META_RE = /(this (project|site|app|web ?app|page|watch)|what am i looking at|how (was|is) (this|it)\b[^?]*\b(develop|built|made|creat)|who (made|built|develop|creat)\b|^\s*what('?s| is) this\b[^a-z]*$)/i;
const META_ANSWER =
  "**San Juan Riparian Watch** is an independent proof-of-concept that maps riparian vegetation and its invasive share along the San Juan River from decades of satellite imagery, and field-tests a Random Forest against **Ai2's OlmoEarth** foundation model. They tie on the river corridors (~0.80–0.88 AUC); the foundation model pulls ahead on a lone arroyo (0.557 → 0.889). It runs end to end on Ai2's open stack — OlmoEarth delineates the vegetation, and **OLMo** (me) answers from the document corpus with citations. It's experimental and not independently validated. Ask me about the corridor, the invasives, the beetle test, or the RF-vs-foundation-model decision and I'll answer from the sources.";

export default function Chat({ agentUrl = '/query' }: { agentUrl?: string }) {
  const [messages, setMessages] = useState<Msg[]>([
    { role: 'assistant', text: 'Ask about the corridor, the invasives, the beetle test, or the RF-vs-foundation-model decision. Tap a question below, or type your own, answers cite their sources, and a reach mention flies the map.' },
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
  useEffect(() => { const el = chatRef.current; if (el) el.scrollTop = el.scrollHeight; }, [messages]);

  // Probe the agent + load model tiers. RE-PROBE periodically so a transient
  // backend blip (a brief restart or load spike) auto-recovers the "live" state
  // instead of latching the chat "offline" until a page reload.
  const modelsLoadedRef = useRef(false);
  useEffect(() => {
    if (!AGENT_URL) return;
    const healthUrl = AGENT_URL.replace(/\/(docs\/ask|query)\/?$/, '/health');
    let cancelled = false;
    const loadModels = () => {
      if (modelsLoadedRef.current || !isQuery) return;
      modelsLoadedRef.current = true;
      const url = AGENT_URL.replace(/\/query\/?$/, '/agent/models');
      const mt = withTimeout(8000);
      fetch(url, { signal: mt.signal }).then((r) => (r.ok ? r.json() : Promise.reject())).then((d) => {
        if (cancelled) return;
        if (d?.default) { setTier(d.default); tierRef.current = d.default; }
        setTiers(d?.tiers || null);
      }).catch(() => { modelsLoadedRef.current = false; }).finally(() => mt.clear());
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
      copy[copy.length - 1] = { role: 'assistant', text: clean, html: mdToHtml(clean || ''), citations, geoms: shownGeoms };
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

  const askLiveStream = useCallback(async (q: string, onToken: (partial: string) => void) => {
    const url = AGENT_URL.replace(/\/query\/?$/, '/query/stream');
    // Abort a stream that goes silent (no data for 30s) so the UI can't hang;
    // the timer resets on every chunk, so a long-but-active answer is fine.
    const ctrl = new AbortController();
    let idle: ReturnType<typeof setTimeout>;
    const bump = () => { clearTimeout(idle); idle = setTimeout(() => ctrl.abort(), 30000); };
    bump();
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, signal: ctrl.signal, body: JSON.stringify({ query: q, session_id: sessionRef.current || undefined, use_cache: true, model_tier: tierRef.current }) });
      if (!r.ok || !r.body) throw new Error('agent ' + r.status);
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
      const r = await fetch(AGENT_URL, { method: 'POST', headers: { 'content-type': 'application/json' }, signal: t.signal, body: JSON.stringify(body) });
      if (!r.ok) throw new Error('agent ' + r.status);
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
    if (META_RE.test(text)) {   // answer "what is this?" from the project's own description
      setTimeout(() => { finalize(META_ANSWER, [], []); setBusy(false); }, 150);
      return;
    }
    if (!live) {
      setTimeout(() => { finalize(fallbackAnswer(text), [], []); setBusy(false); }, 200);
      return;
    }
    const onToken = (partial: string) => setMessages((m) => { const c = m.slice(); c[c.length - 1] = { role: 'assistant', text: stripSources(partial), streaming: true }; return c; });
    const run = isQuery ? askLiveStream(text, onToken) : askLive(text).then((res: any) => ({ answer: res.answer, citations: res.citations, geoms: res.resolved_geometries }));
    run.then((res: any) => finalize(res.answer || '(no answer returned)', res.citations || [], res.geoms || []))
      .catch(() => { finalize(fallbackAnswer(text) + '\n\n(the live agent was unreachable just now, that was a pre-written answer.)', [], []); setLive(false); })
      .finally(() => setBusy(false));
  }, [busy, live, isQuery, askLive, askLiveStream, finalize]);

  const go = () => { const v = input.trim(); if (!v || busy) return; setInput(''); answer(v); };
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
                title={!t.available ? 'OLMo isn’t being served right now — this switch goes live the moment a host (Ai2 / OpenRouter) serves it.' : undefined}
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
