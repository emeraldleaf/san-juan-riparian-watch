// Citation links + a small, deliberately-limited markdown renderer, shared by BOTH
// agent surfaces (the story-page chat and the map agent) so an answer renders and
// cites identically wherever it appears — and so the HTML escaping below has exactly
// one implementation to audit.
//
// Security note: the output is assigned via dangerouslySetInnerHTML, so escH()
// escapes every HTML-significant character (quotes included) BEFORE any markup is
// built. By the time links are constructed a model-supplied URL can no longer carry
// a raw quote or angle bracket to break out of an attribute.

export const CITE_PAPERS: Record<string, string> = {
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
// Corpus id -> the document's path under docs/, generated from
// docintel/corpus/seed_sources.yaml and VERIFIED against the repo tree. Exact rather
// than reconstructed: the previous version rebuilt paths from a prefix + a
// subdirectory guess, which silently produced dead links for every `audit-*` citation
// (their corpus ids drop the date prefix their filenames carry) and would have done
// the same for every spec and decision record added to the corpus.
const DOC_PATHS: Record<string, string> = {
  'audit-corip-woodward-2018': 'audits/2026-07-11-corip-woodward-2018.md',
  'audit-evangelista-2018-csu-nrel': 'audits/2026-07-12-evangelista-2018-csu-nrel.md',
  'audit-perkins-2025-canyonlands': 'audits/2026-07-12-perkins-2025-canyonlands.md',
  'audit-tamarisk-detection-established': 'audits/2026-07-11-tamarisk-detection-established.md',
  'project-2026-07-03-delineation-over-hydrology-buffers': 'decisions/2026-07-03-delineation-over-hydrology-buffers.md',
  'project-2026-07-03-stage1-riparian-delineation': 'specs/2026-07-03-stage1-riparian-delineation.md',
  'project-2026-07-04-stage3-annual-change': 'specs/2026-07-04-stage3-annual-change.md',
  'project-2026-07-11-model-and-inference-hosting': 'decisions/2026-07-11-model-and-inference-hosting.md',
  'project-2026-07-11-stage2-invasives-tamarix': 'specs/2026-07-11-stage2-invasives-tamarix.md',
  'project-2026-07-18-methods-and-metrics': '2026-07-18-methods-and-metrics.md',
  'project-2026-07-18-reach-cube-materialization': '2026-07-18-reach-cube-materialization.md',
  'project-2026-07-19-fm-vs-rf-deploy-decision': 'specs/2026-07-19-fm-vs-rf-deploy-decision.md',
  'project-2026-07-20-diverse-reach-transfer': '2026-07-20-diverse-reach-transfer.md',
  'project-2026-08-01-fm-vs-rf-loro-result': '2026-08-01-fm-vs-rf-loro-result.md',
  'project-2026-08-10-arroyo-map-extent-artifact': '2026-08-10-arroyo-map-extent-artifact.md',
  'project-2026-08-18-map-agent-runtime': 'decisions/2026-08-18-map-agent-runtime.md',
  'project-2026-08-21-basin-scale-productionization': 'decisions/2026-08-21-basin-scale-productionization.md',
  'project-2026-08-21-invasive-fm-vs-rf-loro': 'specs/2026-08-21-invasive-fm-vs-rf-loro.md',
  'project-2026-08-21-reach-provenance-gap': '2026-08-21-reach-provenance-gap.md',
  'project-RETRACTIONS': 'RETRACTIONS.md',
  'project-STATUS': 'STATUS.md',
  'project-code-review': 'code-review.md',
  'project-data-sources': 'data-sources.md',
  'project-literature-review': 'literature-review.md',
  'project-method': 'method.md',
};
const DOCS_BASE = 'https://github.com/emeraldleaf/san-juan-riparian-watch/blob/main/docs/';

export function citeUrlFor(src: string): string | null {
  if (!src) return null;
  const stem = src.replace(/\.(md|pdf|html?)$/, '');
  if (CITE_PAPERS[stem]) return CITE_PAPERS[stem];
  const path = DOC_PATHS[stem];
  if (path) return DOCS_BASE + path;
  // method.md is fetched as published HTML, so its id doesn't match a filename.
  if (stem === 'project-method-ai-assisted-research') return DOCS_BASE + 'method.md';
  if (stem.indexOf('findings-') === 0) return DOCS_BASE + stem.slice('findings-'.length) + '.md';
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
export function mdToHtml(md: string): string {
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
