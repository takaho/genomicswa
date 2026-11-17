/* Style map — compare versions of a scientific text. Runs entirely in the browser. */
'use strict';
const COLORS = ['#C8553D', '#1B7F79', '#E0A100', '#7A5195', '#1F3A5F'];
const CLUSTER_COLORS = { 1: '#2a78d6', 2: '#eb6834', 3: '#1baf7a', 4: '#eda100', 5: '#d36ba8', 6: '#6250d6' };
const LABEL = {
  sent_len: 'Sentence length (words)', word_len: 'Word length (characters)', mattr: 'Lexical diversity (MATTR)',
  subj_we: '“We” as subject (% of clauses)', subj_evidence: 'Data/findings/study as subject (%)', subj_method: 'Method/model as subject (%)',
  subj_human: 'Patients/participants as subject (%)', subj_organism: 'Organism as subject (%)', subj_pronoun: 'Pronoun subject (this, they…) (%)',
  subj_expletive: '“It is…/There are…” (%)', subj_entity: 'Gene/cell/molecule/other as subject (%)', passive_pct: 'Passive clauses (%)',
  hedge_modal: 'Modal hedges (may, might) /1k', hedge_verb: 'Hedging verbs (suggest) /1k', hedge_adv: 'Hedging adverbs (likely) /1k',
  booster: 'Boosters (clearly) /1k', booster_verb: 'Booster verbs (demonstrate, reveal) /1k', past_pct: 'Past tense (% of finite verbs)',
  aim: 'Aim statements /1k', novelty: 'Novelty/gap statements /1k', importance: 'Importance words (crucial, key) /1k',
  limitation: 'Limitation statements /1k', future: 'Future-work statements /1k', conn_contrast: 'Contrast connectives (however) /1k',
  conn_additive: 'Additive connectives (moreover) /1k', conn_causal: 'Causal connectives (therefore, thus) /1k',
  conn_summary: 'Summary connectives (taken together) /1k', nominal: 'Nominalisations /1k',
};
const SHORT = { word_len: 'longer words', mattr: 'lexical diversity', nominal: 'nominalisation', subj_we: '“we” subjects', subj_evidence: 'findings as subject',
  subj_method: 'methods as subject', subj_human: 'patients as subject', subj_organism: 'organisms as subject', subj_entity: 'entities as subject',
  passive_pct: 'passive', hedge_modal: 'modal hedges', hedge_verb: 'hedging verbs', hedge_adv: 'hedging adverbs', booster: 'boosters', booster_verb: 'booster verbs',
  past_pct: 'past tense', aim: 'aim statements', novelty: 'novelty claims', importance: 'importance words', limitation: 'limitations', future: 'future work',
  conn_contrast: 'contrast connectives', conn_additive: 'additive connectives', conn_causal: 'causal connectives', conn_summary: 'summary connectives', sent_len: 'long sentences' };
const MARK = [['marker', 'AI-polish words'], ['importance', 'importance words'], ['study_subject', '“This study / These results” as subject'], ['we', '“we”'],
  ['causal', 'causal connectives'], ['contrast', 'contrast connectives'], ['additive', 'additive connectives'], ['hedge', 'hedges'], ['negation', 'negations'], ['passive', 'passive (approx.)']];

let REF = null, AGREE = {}, EXAMPLES = [], LAST = null;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ------------------------------------------------------------------ setup
async function init() {
  $('status').textContent = 'loading reference data…';
  try {
    [REF, AGREE, EXAMPLES] = await Promise.all(['data/reference.json', 'data/agreement.json', 'data/examples.json'].map((u) => fetch(u).then((r) => r.json())));
  } catch (e) {
    $('status').textContent = 'Could not load data files. If you opened index.html from disk, serve the folder over http (e.g. python3 -m http.server).';
    return;
  }
  const dl = $('fieldlist');
  Object.entries(REF.fields).sort((a, b) => a[1].name.localeCompare(b[1].name)).forEach(([id, f]) => {
    const o = document.createElement('option'); o.value = `${f.name} (${id})`; dl.appendChild(o);
  });
  EXAMPLES.forEach((e, i) => { const o = document.createElement('option'); o.value = i; o.textContent = e.title; $('example').appendChild(o); });
  $('agreement').innerHTML = '<table><tr><th>Feature</th><th>r</th><th>Feature</th><th>r</th></tr>' + pairs(REF.features).map(([a, b]) =>
    `<tr><td>${esc(LABEL[a])}${REF.approximate.includes(a) ? ' *' : ''}</td><td class="num">${(AGREE[a] ?? NaN).toFixed(2)}</td>` +
    (b ? `<td>${esc(LABEL[b])}${REF.approximate.includes(b) ? ' *' : ''}</td><td class="num">${(AGREE[b] ?? NaN).toFixed(2)}</td>` : '<td></td><td></td>') + '</tr>').join('') + '</table>';
  readHash();
  if (!$('slots').children.length) { addSlot('Original'); addSlot('Rewritten'); }
  $('add').onclick = () => addSlot('');
  $('run').onclick = run;
  $('example').onchange = loadExample;
  ['field', 'section', 'group'].forEach((id) => $(id).addEventListener('change', () => { writeHash(); if (LAST) run(); }));
  $('dlJson').onclick = downloadJson; $('dlSvg').onclick = downloadSvg;
  $('status').textContent = 'ready';
}
function pairs(a) { const out = []; const h = Math.ceil(a.length / 2); for (let i = 0; i < h; i++) out.push([a[i], a[i + h]]); return out; }
function fieldId() {
  const v = $('field').value.trim(); const m = v.match(/\((\d{4})\)\s*$/); if (m && REF.fields[m[1]]) return m[1];
  if (REF.fields[v]) return v;
  const hit = Object.entries(REF.fields).find(([, f]) => f.name.toLowerCase() === v.toLowerCase()); return hit ? hit[0] : null;
}
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get('field') && REF.fields[p.get('field')]) $('field').value = `${REF.fields[p.get('field')].name} (${p.get('field')})`;
  if (p.get('section')) $('section').value = p.get('section');
  if (p.get('group')) $('group').value = p.get('group');
}
function writeHash() {
  const p = new URLSearchParams(); const f = fieldId(); if (f) p.set('field', f); p.set('section', $('section').value); p.set('group', $('group').value);
  history.replaceState(null, '', '#' + p.toString());
}
function addSlot(label, text) {
  const n = $('slots').children.length; if (n >= 5) return;
  const d = document.createElement('div'); d.className = 'slot';
  d.innerHTML = `<div class="head"><span class="dot"></span><input class="name" placeholder="label, e.g. original / SKILL d3 / ChatGPT"><span class="meta"></span>
    <input type="file" accept=".txt,.md" title="load a .txt file"><button class="rm" title="remove">✕</button></div><textarea placeholder="Paste a section (300+ words works best)."></textarea>`;
  d.querySelector('.name').value = label || ''; d.querySelector('textarea').value = text || '';
  d.querySelector('textarea').addEventListener('input', () => count(d));
  d.querySelector('input[type=file]').onchange = (e) => { const f = e.target.files[0]; if (f) f.text().then((t) => { d.querySelector('textarea').value = t; count(d); }); };
  d.querySelector('.rm').onclick = () => { d.remove(); recolour(); };
  $('slots').appendChild(d); recolour(); count(d);
}
function recolour() { [...$('slots').children].forEach((d, i) => { d.querySelector('.dot').style.background = COLORS[i]; }); $('add').disabled = $('slots').children.length >= 5; }
function count(d) {
  const n = (d.querySelector('textarea').value.match(/[A-Za-z][A-Za-z\-']*/g) || []).length; const m = d.querySelector('.meta');
  m.textContent = n ? `${n} words${n < 300 ? ' — short texts give unstable values' : ''}` : ''; m.className = 'meta' + (n && n < 300 ? ' warn' : '');
}
function loadExample() {
  const e = EXAMPLES[+$('example').value]; if (!e) return;
  $('slots').innerHTML = ''; e.texts.forEach((t) => addSlot(t.label, t.text));
  $('field').value = `${REF.fields[e.field].name} (${e.field})`; $('section').value = e.section; writeHash(); run();
}

// ------------------------------------------------------------------ analysis
function run() {
  const field = fieldId();
  if (!field) { $('status').textContent = 'Choose a field first (type and pick from the list).'; return; }
  const texts = [...$('slots').children].map((d, i) => ({ i, label: d.querySelector('.name').value || 'Text ' + 'ABCDE'[i], text: d.querySelector('textarea').value, color: COLORS[i] }))
    .filter((t) => t.text.trim().split(/\s+/).length >= 20);
  if (!texts.length) { $('status').textContent = 'Paste at least one text (20+ words).'; return; }
  $('status').textContent = 'analysing…'; writeHash();
  setTimeout(() => {
    const ex = window.StyleNLP.get(); const sec = $('section').value; const R = REF.sections[sec]; const group = $('group').value;
    texts.forEach((t) => {
      t.f = ex.features(t.text); t.h = ex.highlight(t.text); t.g = ex.guardCounts(t.text);
      t.z = REF.map_features.map((k, j) => (((t.f[k] ?? R.z_mean[j]) - R.z_mean[j]) / R.z_sd[j]));
      t.pc = R.pca.components.map((c) => c.reduce((a, w, j) => a + w * (t.z[j] - R.pca.center[j]), 0));
      const fm = R.axes.field_mean_z[field] || R.axes.field_mean_z[Object.keys(R.axes.field_mean_z)[0]];
      const W = t.z.map((v, j) => v - fm[j]);
      const dot = (u) => u.reduce((a, w, j) => a + w * W[j], 0);
      t.period = (dot(R.axes.u_period) - R.axes.period_ref[0]) / (R.axes.period_ref[1] - R.axes.period_ref[0]);
      t.en = (dot(R.axes.u_en) - R.axes.en_ref[0]) / (R.axes.en_ref[1] - R.axes.en_ref[0]);
      t.llm = Object.entries(R.llm_ref).reduce((a, [k, r]) => a + r.sign * (((t.f[k] ?? r.mean) - r.mean) / r.sd), 0) / Object.keys(R.llm_ref).length;
      const q = (R.quantiles[group][field] || R.quantiles[group].ALL);
      t.pct = Object.fromEntries(REF.features.map((k) => [k, percentile(t.f[k], q[k])]));
    });
    LAST = { field, sec, group, texts };
    render(LAST); $('results').hidden = false; $('status').textContent = '';
  }, 30);
}
function percentile(v, q) {
  if (v === null || v === undefined || isNaN(v)) return NaN;
  const P = REF.quantiles;
  if (v < q[0]) return 2.5; if (v > q[q.length - 1]) return 97.5;
  for (let i = 0; i < q.length - 1; i++) if (v >= q[i] && v <= q[i + 1]) return P[i] + (P[i + 1] - P[i]) * (q[i + 1] > q[i] ? (v - q[i]) / (q[i + 1] - q[i]) : 0.5);
  return NaN;
}

// ------------------------------------------------------------------ rendering
function render(L) {
  const R = REF.sections[L.sec]; const fname = REF.fields[L.field].name;
  // summary
  $('summary').innerHTML = '<div class="summary-cards">' + L.texts.map((t) => `<div class="card"><div class="t"><span class="dot" style="width:12px;height:12px;border-radius:50%;background:${t.color}"></span>${esc(t.label)}</div>
    <div class="v">${t.f.n_words} words · ${t.f.n_sents} sentences${t.f.n_words < 300 ? ' · <span style="color:#C8553D">short</span>' : ''}</div>
    <div class="v">LLM-style index <b>${t.llm.toFixed(2)}</b> <span title="mean signed z of 7 features LLM polishing pushes; 0 = 2019–22 average">ⓘ</span></div>
    <div class="v">AI-polish words <b>${t.f.markers_per10k.toFixed(0)}</b> /10k</div>
    <div class="v">2019–22 → 2024–25 direction <b>${t.period.toFixed(2)}</b> · English-speaking direction <b>${t.en.toFixed(2)}</b></div></div>`).join('') + '</div>';
  $('map').innerHTML = mapSvg(L, R, fname);
  const ax = (k) => R.pca[k]; const nm = (a) => a.map((k) => SHORT[k] || k).join(', ');
  $('mapcap').textContent = `Each dot is a field (median of its 2019–22 papers; colour = cluster); the ring is ${fname}. Single texts scatter much more widely than field medians, so read the arrows (direction and length of change), not the distance to the ring. ` +
    `Horizontal axis: more ${nm(ax('pc1').pos)} → right, more ${nm(ax('pc1').neg)} → left. Vertical: more ${nm(ax('pc2').pos)} ↑, more ${nm(ax('pc2').neg)} ↓.`;
  $('axes').innerHTML = axesSvg(L, R);
  $('strips').innerHTML = stripsSvg(L, R);
  $('changes').innerHTML = changes(L, R);
  $('legend').innerHTML = MARK.map(([k, l]) => `<span class="m-${k}">${esc(l)}</span>`).join('');
  $('marked').innerHTML = L.texts.map((t) => `<div class="marked"><h3 style="color:${t.color}">${esc(t.label)}</h3>${markText(t.h)}</div>`).join('');
}
function svgOpen(w, h, id) { return `<svg id="${id}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="100%" style="max-width:${w}px;background:#fff;border-radius:8px">`; }
function arrows(pts, color) {
  let s = '';
  for (let i = 0; i + 1 < pts.length; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1]; const dx = x2 - x1, dy = y2 - y1, d = Math.hypot(dx, dy) || 1;
    const ex = x2 - dx / d * 8, ey = y2 - dy / d * 8;
    s += `<line x1="${x1}" y1="${y1}" x2="${ex}" y2="${ey}" stroke="#1B2433" stroke-width="1.6" marker-end="url(#ah)"/>`;
  }
  return s;
}
const AH = '<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#1B2433"/></marker></defs>';
function mapSvg(L, R, fname) {
  const W = 560, H = 440, m = 30; const F = R.pca.fields;
  const xs = Object.values(F).map((p) => p[0]).concat(L.texts.map((t) => t.pc[0])); const ys = Object.values(F).map((p) => p[1]).concat(L.texts.map((t) => t.pc[1]));
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)], [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const pad = 0.08; const sx = (x) => m + (x - x0 + (x1 - x0) * pad) / ((x1 - x0) * (1 + 2 * pad)) * (W - 2 * m); const sy = (y) => H - m - (y - y0 + (y1 - y0) * pad) / ((y1 - y0) * (1 + 2 * pad)) * (H - 2 * m);
  let s = svgOpen(W, H, 'svg-map') + AH;
  s += `<line x1="${sx(0)}" y1="${m}" x2="${sx(0)}" y2="${H - m}" stroke="#eef0f2"/><line x1="${m}" y1="${sy(0)}" x2="${W - m}" y2="${sy(0)}" stroke="#eef0f2"/>`;
  Object.entries(F).forEach(([id, p]) => {
    const c = CLUSTER_COLORS[REF.fields[id]?.cluster] || '#999';
    s += `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="${id === L.field ? 4 : 3}" fill="${c}" fill-opacity="${id === L.field ? 1 : .35}"><title>${esc(REF.fields[id].name)}</title></circle>`;
  });
  const tf = F[L.field];
  if (tf) s += `<circle cx="${sx(tf[0])}" cy="${sy(tf[1])}" r="11" fill="none" stroke="#1F3A5F" stroke-width="2"/><text x="${sx(tf[0]) + 14}" y="${sy(tf[1]) - 8}" font-size="13" fill="#1F3A5F" font-weight="bold">${esc(fname)}</text>`;
  s += arrows(L.texts.map((t) => [sx(t.pc[0]), sy(t.pc[1])]));
  L.texts.forEach((t, i) => { const X = sx(t.pc[0]), right = X > W - 160; s += `<circle cx="${X}" cy="${sy(t.pc[1])}" r="7" fill="${t.color}" stroke="#fff" stroke-width="1.5"/><text x="${right ? X - 9 : X + 9}" y="${sy(t.pc[1]) + 14}" text-anchor="${right ? 'end' : 'start'}" font-size="12" fill="${t.color}" font-weight="bold">${esc(t.label)}</text>`; });
  const legend = Object.entries(REF.clusters).map(([k, n], i) => `<circle cx="${m + (i % 3) * 175}" cy="${H - 22 + Math.floor(i / 3) * 14}" r="4" fill="${CLUSTER_COLORS[k]}" fill-opacity=".6"/><text x="${m + 8 + (i % 3) * 175}" y="${H - 18 + Math.floor(i / 3) * 14}" font-size="10" fill="#6B7480">${esc(n)}</text>`).join('');
  return s + legend + '</svg>';
}
function axesSvg(L, R) {
  const W = 560, H = 440, m = 46;
  const pts = Object.entries(R.axes.regions).map(([k, v]) => [v[0], v[1]]).concat([R.axes.post_point, [0, 0]]).concat(L.texts.map((t) => [t.period, t.en]));
  const x0 = Math.min(-0.6, ...pts.map((p) => p[0])) - 0.1, x1 = Math.max(1.6, ...pts.map((p) => p[0])) + 0.1;
  const y0 = Math.min(-0.8, ...pts.map((p) => p[1])) - 0.1, y1 = Math.max(1.4, ...pts.map((p) => p[1])) + 0.1;
  const sx = (x) => m + (x - x0) / (x1 - x0) * (W - m - 16), sy = (y) => H - m - (y - y0) / (y1 - y0) * (H - m - 16);
  let s = svgOpen(W, H, 'svg-axes') + AH;
  [0, 1].forEach((v) => { s += `<line x1="${sx(v)}" y1="16" x2="${sx(v)}" y2="${H - m}" stroke="#D9DEE3" stroke-dasharray="${v ? '4 3' : ''}"/><line x1="${m}" y1="${sy(v)}" x2="${W - 16}" y2="${sy(v)}" stroke="#D9DEE3" stroke-dasharray="${v ? '4 3' : ''}"/>`; });
  s += `<text x="${sx(0)}" y="${H - m + 16}" font-size="11" fill="#6B7480" text-anchor="middle">2019–22 average</text><text x="${sx(1)}" y="${H - m + 16}" font-size="11" fill="#6B7480" text-anchor="middle">2024–25 average</text>`;
  s += `<text x="${(W + m) / 2}" y="${H - 8}" font-size="12" fill="#1B2433" text-anchor="middle">change in prose, 2019–22 → 2024–25 →</text>`;
  s += `<text transform="translate(14 ${(H - m) / 2}) rotate(-90)" font-size="12" fill="#1B2433" text-anchor="middle">other authors → English-speaking authors (2019–22) →</text>`;
  Object.entries(R.axes.regions).forEach(([k, v]) => { s += `<rect x="${sx(v[0]) - 3}" y="${sy(v[1]) - 3}" width="6" height="6" fill="#8A97A3"/><text x="${sx(v[0]) + 6}" y="${sy(v[1]) + 4}" font-size="11" fill="#6B7480">${esc(k)}</text>`; });
  s += `<rect x="${sx(R.axes.post_point[0]) - 3}" y="${sy(R.axes.post_point[1]) - 3}" width="6" height="6" fill="#C8553D" fill-opacity=".5"/><text x="${sx(R.axes.post_point[0]) + 6}" y="${sy(R.axes.post_point[1]) + 14}" font-size="11" fill="#C8553D">all papers 2024–25</text>`;
  s += arrows(L.texts.map((t) => [sx(t.period), sy(t.en)]));
  L.texts.forEach((t) => { const X = sx(t.period), right = X > W - 160; s += `<circle cx="${X}" cy="${sy(t.en)}" r="7" fill="${t.color}" stroke="#fff" stroke-width="1.5"/><text x="${right ? X - 9 : X + 9}" y="${sy(t.en) - 9}" text-anchor="${right ? 'end' : 'start'}" font-size="12" fill="${t.color}" font-weight="bold">${esc(t.label)}</text>`; });
  return s + '</svg>';
}
function stripsSvg(L, R) {
  const feats = REF.features; const rowH = 22, W = 1180, lab = 330, x0 = lab + 10, x1 = W - 20, top = 26;
  const H = top + feats.length * rowH + 10; const sx = (p) => x0 + p / 100 * (x1 - x0);
  const tg = R.targets[L.field] || { selected: [], values: {} }; const q = R.quantiles[L.group][L.field] || R.quantiles[L.group].ALL;
  const qEN = (R.quantiles.pre_en[L.field] || R.quantiles.pre_en.ALL);
  let s = svgOpen(W, H, 'svg-strips');
  [0, 25, 50, 75, 100].forEach((p) => { s += `<text x="${sx(p)}" y="14" font-size="10" fill="#6B7480" text-anchor="middle">${p}</text>`; });
  s += `<text x="${x0}" y="14" font-size="10" fill="#6B7480" text-anchor="end" dx="-6">percentile</text>`;
  feats.forEach((k, i) => {
    const y = top + i * rowH + rowH / 2; const sel = tg.selected.includes(k);
    s += `<text x="${lab}" y="${y + 4}" font-size="12" text-anchor="end" fill="${sel ? '#1F3A5F' : '#1B2433'}" font-weight="${sel ? 'bold' : 'normal'}">${esc(LABEL[k])}${REF.approximate.includes(k) ? ' *' : ''}</text>`;
    s += `<line x1="${sx(5)}" y1="${y}" x2="${sx(95)}" y2="${y}" stroke="#C9D1D6" stroke-width="1.2"/><line x1="${sx(25)}" y1="${y}" x2="${sx(75)}" y2="${y}" stroke="#8FA3AE" stroke-width="7"/><line x1="${sx(50)}" y1="${y - 6}" x2="${sx(50)}" y2="${y + 6}" stroke="#1F3A5F"/>`;
    const tv = tg.values[k];
    if (tv !== undefined) { const tp = percentile(tv, q[k]); if (!isNaN(tp)) s += `<path d="M${sx(tp)},${y - 7} l5,7 l-5,7 l-5,-7 z" fill="${sel ? '#E0A100' : 'none'}" stroke="#E0A100" stroke-width="1.3"><title>English-speaking authors, 2019–22 average${sel ? ' (listed in the SKILL d3 file)' : ''}</title></path>`; }
    L.texts.forEach((t, j) => { const p = t.pct[k]; if (!isNaN(p)) s += `<circle cx="${sx(p)}" cy="${y + (j - (L.texts.length - 1) / 2) * 3}" r="5" fill="${t.color}" fill-opacity=".9"><title>${esc(t.label)}: ${(t.f[k] ?? NaN).toFixed(2)} (percentile ${p.toFixed(0)})</title></circle>`; });
  });
  return s + '</svg><p class="caption">Bold labels with a filled ◆ are the features listed in this field\'s SKILL d3 file. * approximate in the browser version.</p>';
}
function changes(L, R) {
  if (L.texts.length < 2) return '<p class="caption">Add a second version to see changes.</p>';
  const tg = R.targets[L.field] || { selected: [], values: {} }; const idx = Object.fromEntries(REF.map_features.map((k, j) => [k, j]));
  let html = '';
  for (let i = 0; i + 1 < L.texts.length; i++) {
    const a = L.texts[i], b = L.texts[i + 1];
    const rows = REF.features.map((k) => {
      const j = idx[k]; const sd = j !== undefined ? R.z_sd[j] : null; const va = a.f[k], vb = b.f[k];
      if (va == null || vb == null) return null;
      const dz = sd ? (vb - va) / sd : NaN; const t = tg.values[k];
      const rel = t === undefined ? '' : Math.abs(vb - t) < Math.abs(va - t) - 1e-9 ? '<span class="closer">closer</span>' : Math.abs(vb - t) > Math.abs(va - t) + 1e-9 ? '<span class="farther">farther</span>' : '';
      return { k, va, vb, dz, rel, sel: tg.selected.includes(k) };
    }).filter((r) => r && !isNaN(r.dz) && Math.abs(r.dz) >= 0.25).sort((x, y) => Math.abs(y.dz) - Math.abs(x.dz));
    html += `<h3 style="font-size:15px;margin:10px 0 6px"><span style="color:${a.color}">${esc(a.label)}</span> → <span style="color:${b.color}">${esc(b.label)}</span></h3>`;
    html += guard(a, b);
    html += rows.length ? '<table><tr><th>Feature</th><th class="num">before</th><th class="num">after</th><th class="num">change (SD)</th><th>vs English-speaking 2019–22 average</th></tr>' +
      rows.slice(0, 14).map((r) => `<tr><td>${r.sel ? '<b>' : ''}${esc(LABEL[r.k])}${r.sel ? '</b> ◆' : ''}</td><td class="num">${r.va.toFixed(2)}</td><td class="num">${r.vb.toFixed(2)}</td><td class="num">${r.dz > 0 ? '+' : ''}${r.dz.toFixed(2)}</td><td>${r.rel}</td></tr>`).join('') + '</table>'
      : '<p class="caption">No feature changed by 0.25 SD or more.</p>';
    html += `<p class="caption">Map: (${a.pc[0].toFixed(2)}, ${a.pc[1].toFixed(2)}) → (${b.pc[0].toFixed(2)}, ${b.pc[1].toFixed(2)}); 2019–22 → 2024–25 direction ${a.period.toFixed(2)} → ${b.period.toFixed(2)}; English-speaking direction ${a.en.toFixed(2)} → ${b.en.toFixed(2)}; LLM-style index ${a.llm.toFixed(2)} → ${b.llm.toFixed(2)}.</p>`;
  }
  return html;
}
function guard(a, b) {
  const w = [];
  if (b.g.causal > a.g.causal) w.push(`causal connectives added (${a.g.causal} → ${b.g.causal}) — check that the reasoning is really causal`);
  if (b.g.contrast > a.g.contrast) w.push(`contrast connectives added (${a.g.contrast} → ${b.g.contrast}) — check that a contrast is really meant`);
  if (b.g.hedge !== a.g.hedge) w.push(`number of hedges changed (${a.g.hedge} → ${b.g.hedge}) — the strength of claims may have changed`);
  if (b.g.negation !== a.g.negation) w.push(`number of negations changed (${a.g.negation} → ${b.g.negation})`);
  if (b.g.refs < a.g.refs) w.push(`citation markers lost (${a.g.refs} → ${b.g.refs})`);
  if (b.g.numbers < a.g.numbers) w.push(`numbers lost (${a.g.numbers} → ${b.g.numbers})`);
  return w.length ? `<div class="warnbox"><b>Check the meaning:</b><ul style="margin:4px 0 0 18px;padding:0">${w.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`
    : '<div class="okbox">Connectives, hedges, negations, citations and numbers: no change that would alter the argument (simple counts).</div>';
}
function markText(h) {
  let out = '', pos = 0;
  for (const sp of h.spans) { out += esc(h.text.slice(pos, sp.start)) + `<mark class="m-${sp.kind}">${esc(h.text.slice(sp.start, sp.end))}</mark>`; pos = sp.end; }
  return out + esc(h.text.slice(pos));
}

// ------------------------------------------------------------------ export
function save(name, blob) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function downloadJson() {
  if (!LAST) return;
  const d = { field: LAST.field, field_name: REF.fields[LAST.field].name, section: LAST.sec, reference: LAST.group,
    texts: LAST.texts.map((t) => ({ label: t.label, features: t.f, percentiles: t.pct, map: t.pc, direction_2019_22_to_2024_25: t.period, direction_english_speaking: t.en, llm_style_index: t.llm, counts: t.g })) };
  save('stylemap_results.json', new Blob([JSON.stringify(d, null, 1)], { type: 'application/json' }));
}
function downloadSvg() { ['svg-map', 'svg-axes', 'svg-strips'].forEach((id) => { const el = $(id); if (el) save(id + '.svg', new Blob([el.outerHTML], { type: 'image/svg+xml' })); }); }

init();
