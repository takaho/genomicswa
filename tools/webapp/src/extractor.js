/*
 * extractor.js — style features of a scientific text, for the browser and for Node.
 * A JavaScript approximation of features_wide.py (spaCy). It uses wink-nlp (tokens, POS, lemmas) plus the
 * lexicons of the corpus study. Syntax-dependent features (clause subjects, passive voice, tense) are
 * approximated with POS patterns; the reference data are computed with this same code, so user texts and
 * the reference are measured with the same yardstick.
 *
 *   const { createExtractor } = require('./extractor');
 *   const ex = createExtractor(winkNLP(model));
 *   const f = ex.features(text);        // { sent_len, word_len, mattr, subj_we, ..., n_words }
 *   const h = ex.highlight(text);       // [{ start, end, kind }] for the UI
 */
'use strict';

const EVIDENCE = new Set(['datum', 'data', 'result', 'finding', 'observation', 'analysis', 'study', 'experiment', 'evidence',
  'work', 'figure', 'fig', 'table', 'investigation', 'survey', 'trial', 'measurement', 'assessment', 'comparison',
  'examination', 'screen', 'test', 'evaluation', 'paper', 'report', 'article', 'review', 'results', 'findings', 'analyses', 'studies']);
const METHOD = new Set(['method', 'approach', 'model', 'algorithm', 'tool', 'pipeline', 'technique', 'framework', 'assay',
  'strategy', 'platform', 'protocol', 'procedure', 'software', 'package', 'workflow', 'simulation', 'system']);
const HUMAN = new Set(['patient', 'participant', 'subject', 'individual', 'people', 'person', 'woman', 'man', 'child', 'adult',
  'volunteer', 'respondent', 'case', 'control', 'cohort', 'infant', 'adolescent', 'student', 'nurse', 'physician',
  'clinician', 'donor', 'user', 'worker', 'mother', 'parent', 'women', 'men', 'children']);
const ORGANISM = new Set(['mouse', 'mice', 'rat', 'animal', 'fly', 'worm', 'zebrafish', 'fish', 'plant', 'monkey', 'macaque',
  'pig', 'dog', 'cat', 'yeast', 'strain', 'bacterium', 'bacteria', 'larva', 'embryo', 'seedling', 'cattle', 'cow',
  'sheep', 'chicken', 'bird', 'insect', 'mosquito', 'frog', 'primate', 'host']);
const PRONOUN = new Set(['this', 'these', 'that', 'those', 'they', 'it', 'he', 'she', 'which', 'who', 'both', 'all', 'each',
  'none', 'one', 'some', 'many', 'most', 'other', 'others']);
const HEDGE_MODAL = new Set(['may', 'might', 'could', 'would']);
const HEDGE_VERB = new Set(['suggest', 'indicate', 'appear', 'seem', 'propose', 'speculate', 'assume', 'estimate', 'tend',
  'imply', 'hypothesize', 'hypothesise', 'postulate', 'believe', 'presume', 'suspect']);
const HEDGE_ADV = new Set(['possibly', 'possible', 'probably', 'probable', 'likely', 'unlikely', 'perhaps', 'presumably',
  'potentially', 'putative', 'putatively', 'apparently', 'approximately', 'roughly', 'largely', 'generally', 'relatively',
  'partially', 'partly', 'somewhat', 'plausible', 'plausibly', 'conceivably', 'arguably', 'tentatively', 'seemingly',
  'essentially', 'mostly', 'usually', 'often']);
const BOOSTER = new Set(['clearly', 'clear', 'definitely', 'certainly', 'undoubtedly', 'indeed', 'conclusively', 'unequivocally',
  'strongly', 'robustly', 'obviously', 'evidently', 'evident', 'undeniably', 'always', 'invariably', 'decisively', 'firmly',
  'markedly', 'dramatically', 'remarkably', 'strikingly']);
const BOOSTER_VERB = new Set(['demonstrate', 'prove', 'establish', 'reveal', 'confirm', 'show', 'uncover', 'unravel', 'highlight']);
const MARKERS = new Set(('delve delves delving underscore underscores underscoring showcase showcases showcasing pivotal crucial ' +
  'intricate intricacies notably additionally comprehensive enhance enhances enhancing enhanced robust multifaceted nuanced ' +
  'realm landscape tapestry meticulous meticulously commendable invaluable seamless seamlessly leverage leverages leveraging ' +
  'foster fosters fostering paramount noteworthy groundbreaking holistic elucidate elucidates elucidating insights garner ' +
  'garnered bolster bolsters interplay harness harnessing').split(' '));

const rx = (words) => new RegExp('\\b(?:' + words.join('|') + ')\\b', 'gi');
const MOVES = {
  aim: rx(['here,? we', 'in this (?:study|work|paper|report)', 'the (?:aim|goal|purpose|objective) of', 'we (?:aimed|sought|set out) to',
    'to (?:investigate|examine|test|address|determine|understand|explore|elucidate|characteri[sz]e|identify|assess|evaluate)']),
  novelty: rx(['novel', 'for the first time', 'first (?:report|evidence|study|demonstration)', 'unprecedented',
    'previously (?:unknown|unrecognized|uncharacteri[sz]ed|undescribed)', 'unexplored', 'poorly understood',
    'remains? (?:unclear|unknown|elusive|poorly)', 'little is known', 'gap']),
  importance: rx(['critical', 'crucial', 'key', 'essential', 'important(?:ly)?', 'pivotal', 'fundamental', 'vital',
    'significant(?:ly)? (?:contribut|improv|advanc)', 'major']),
  limitation: rx(['limitations?', 'caveats?', 'beyond the scope', 'should be interpreted with caution', 'cannot (?:rule out|exclude)',
    'may not (?:be|reflect|generali[sz]e)', 'a weakness', 'shortcomings?']),
  future: rx(['future (?:studies|work|research|investigations?)', 'further (?:studies|work|research|investigations?|experiments) (?:are|is|will|would)']),
};
const CONN = {
  conn_contrast: rx(['however', 'although', 'whereas', 'nevertheless', 'nonetheless', 'in contrast', 'conversely', 'despite', 'on the other hand', 'yet']),
  conn_additive: rx(['moreover', 'furthermore', 'additionally', 'in addition', 'also', 'likewise', 'similarly']),
  conn_causal: rx(['therefore', 'thus', 'hence', 'consequently', 'accordingly', 'as a result', 'because']),
  conn_summary: rx(['together', 'collectively', 'taken together', 'overall', 'in summary', 'in conclusion', 'altogether', 'in sum']),
};
const NOMINAL = /(?:tion|sion|ment|ness|ity|ance|ence|ism)s?$/i;
const BE = new Set(['be', 'is', 'are', 'am', 'was', 'were', 'been', 'being']);
const HAVE = new Set(['have', 'has', 'had', 'having']);
const PRES_AUX = new Set(['is', 'are', 'am', 'has', 'have', 'does', 'do']);
const PAST_AUX = new Set(['was', 'were', 'had', 'did']);
const IRREG_PAST = new Set(['found', 'shown', 'showed', 'made', 'given', 'gave', 'taken', 'took', 'seen', 'saw', 'known', 'knew',
  'led', 'held', 'kept', 'left', 'built', 'brought', 'thought', 'sought', 'became', 'become', 'began', 'begun', 'chosen', 'chose',
  'drawn', 'drew', 'driven', 'drove', 'fell', 'fallen', 'grew', 'grown', 'meant', 'met', 'paid', 'put', 'read', 'ran', 'run', 'said',
  'sent', 'set', 'spent', 'split', 'spread', 'stood', 'told', 'understood', 'undertaken', 'undertook', 'written', 'wrote', 'bound',
  'caught', 'fed', 'felt', 'got', 'gotten', 'heard', 'hidden', 'hit', 'laid', 'lain', 'lost', 'overcome', 'rose', 'risen', 'shed',
  'shut', 'struck', 'swept', 'thrown', 'threw', 'won', 'withdrawn', 'arisen', 'arose', 'broken', 'broke', 'frozen', 'stolen', 'woven']);
// sentence splitter that keeps "Fig. 1", "et al.", "e.g.", "S. aureus", "spp." inside sentences
const SPLIT = /(?<=(?<!\b(?:al|Fig|Figs|fig|figs|e\.g|i\.e|vs|ca|cf|approx|Eq|Ref|refs|sp|spp|No|no|St|Dr|Mr|Ms|[A-Z]))\.|[!?])\s+(?=[A-Z(\[])/g;
const CLAUSE_BREAK = new Set([';', ':', 'that', 'which', 'who', 'whereas', 'while', 'but', 'although', 'because', 'and', 'whether', 'if', 'when', 'where', 'since']);
const SUBJ_CLASSES = ['we', 'i', 'evidence', 'method', 'human', 'organism', 'pronoun', 'expletive', 'entity'];
const FEATURES = ['sent_len', 'word_len', 'mattr', 'subj_we', 'subj_evidence', 'subj_method', 'subj_human', 'subj_organism',
  'subj_pronoun', 'subj_expletive', 'subj_entity', 'passive_pct', 'hedge_modal', 'hedge_verb', 'hedge_adv', 'booster',
  'booster_verb', 'past_pct', 'aim', 'novelty', 'importance', 'limitation', 'future', 'conn_contrast', 'conn_additive',
  'conn_causal', 'conn_summary', 'nominal'];

function normalise(text) {
  let t = String(text || '').replace(/\r/g, '');
  t = t.replace(/\[(?:\d+(?:\s*[,–\-]\s*\d+)*)\]/g, '[REF]');                                     // [12], [3-5]
  t = t.replace(/\((?:[A-Z][A-Za-z'\-]+(?: et al\.?| and [A-Z][A-Za-z'\-]+)?,? (?:19|20)\d\d[a-z]?(?:;\s*)?)+\)/g, '[REF]'); // (Smith et al., 2020)
  return t;
}
function prep(text) {
  let t = normalise(text);
  const nRef = (t.match(/\[REF\]/g) || []).length;
  t = t.replace(/\[REF\]/g, '').replace(/\[EQ\]/g, ' X ').replace(/\[\s*[,;–\-]?\s*\]/g, '').replace(/\(\s*[,;]?\s*\)/g, '').replace(/\s+([,.;:)])/g, '$1').replace(/[ \t]+/g, ' ');
  return { t, nRef };
}
function sentences(t) {
  return t.replace(/\n+/g, ' ').split(SPLIT).map(s => s.trim()).filter(s => s.length > 1);
}
function mattr(words, w = 100) {
  if (words.length < w) return new Set(words).size / Math.max(1, words.length);
  const vals = [];
  for (let i = 0; i + w <= words.length; i += 25) vals.push(new Set(words.slice(i, i + w)).size / w);
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}
const isParticiple = (tok) => tok.pos === 'VERB' && (/(?:ed|en)$/i.test(tok.text) || IRREG_PAST.has(tok.lower));
const isPastForm = (tok) => tok.pos === 'VERB' && tok.lower !== tok.lemma && (/ed$/i.test(tok.text) || IRREG_PAST.has(tok.lower));

function createExtractor(nlp) {
  const its = nlp.its;
  function tokenize(sentence) {
    const out = [];
    nlp.readDoc(sentence).tokens().each(t => {
      const text = t.out(); const type = t.out(its.type);
      out.push({ text, lower: text.toLowerCase(), pos: t.out(its.pos), lemma: String(t.out(its.lemma) || text).toLowerCase(), type });
    });
    return out;
  }
  function classify(toks, i) {
    const low = toks[i].lower, lem = toks[i].lemma;
    if (low === 'we') return 'we';
    if (low === 'i') return 'i';
    if (EVIDENCE.has(lem) || EVIDENCE.has(low)) return 'evidence';
    if (METHOD.has(lem)) return 'method';
    if (HUMAN.has(lem) || HUMAN.has(low)) return 'human';
    if (ORGANISM.has(lem) || ORGANISM.has(low)) return 'organism';
    if (toks[i].pos === 'PRON' || PRONOUN.has(low)) return 'pronoun';
    return 'entity';
  }
  // analyse one sentence: clauses -> subject class, voice; tense counts; stance counts
  function analyseSentence(toks, acc) {
    // clause segmentation
    const clauses = []; let cur = [];
    toks.forEach((t, i) => {
      if ((t.pos === 'PUNCT' && (t.text === ';' || t.text === ':')) || (CLAUSE_BREAK.has(t.lower) && i > 0 && t.pos !== 'PUNCT')) {
        if (cur.length) clauses.push(cur); cur = [];
        if (t.pos !== 'PUNCT') cur.push(i);
      } else cur.push(i);
    });
    if (cur.length) clauses.push(cur);
    for (const cl of clauses) {
      // first finite verb group in the clause: first AUX or VERB not after "to" and not -ing after a noun
      let v = -1;
      for (const i of cl) {
        const t = toks[i];
        if ((t.pos === 'VERB' || t.pos === 'AUX') && !(i > 0 && toks[i - 1].lower === 'to') && !/ing$/i.test(t.text)) { v = i; break; }
      }
      if (v < 0) continue;
      // expletive: "It is/was/has been ...", "There is/are ..."
      const first = cl[0]; const fl = toks[first].lower;
      let cls = null; let subjIdx = -1;
      if ((fl === 'it' || fl === 'there') && first < v && (BE.has(toks[v].lower) || HAVE.has(toks[v].lower) || toks[v].pos === 'AUX')) cls = 'expletive';
      if (!cls) {
        // subject: first noun/pronoun before the verb that is not inside a prepositional phrase
        let inPP = false;
        for (const i of cl) {
          if (i >= v) break;
          const t = toks[i];
          if (t.pos === 'ADP') { inPP = true; continue; }
          if (t.pos === 'PUNCT') { inPP = false; continue; }
          if (['NOUN', 'PROPN', 'PRON'].includes(t.pos) || PRONOUN.has(t.lower) || t.lower === 'we') {
            if (inPP) continue;
            // head of a noun run: last noun in the contiguous run
            let j = i; while (j + 1 < v && ['NOUN', 'PROPN'].includes(toks[j + 1].pos)) j++;
            subjIdx = (t.pos === 'PRON' || t.lower === 'we') ? i : j; break;
          }
        }
        if (subjIdx < 0) continue;
        cls = classify(toks, subjIdx);
      }
      acc.subj[cls] = (acc.subj[cls] || 0) + 1;
      // voice: be-form + (adverb)* + participle within the clause after the subject
      let passive = false;
      for (const i of cl) {
        if (i < v) continue;
        if (BE.has(toks[i].lower)) {
          let k = i + 1; while (k < toks.length && toks[k].pos === 'ADV') k++;
          if (k < toks.length && cl.includes(k) && isParticiple(toks[k])) { passive = true; break; }
        }
        if (toks[i].pos === 'VERB' && !BE.has(toks[i].lower)) break;
      }
      if (passive) acc.passive++; else acc.active++;
    }
    // tense and stance
    toks.forEach((t, i) => {
      const prev = i > 0 ? toks[i - 1].lower : '', prev2 = i > 1 ? toks[i - 2].lower : '';
      const afterAux = BE.has(prev) || HAVE.has(prev) || BE.has(prev2) || HAVE.has(prev2) || prev === 'to' || HEDGE_MODAL.has(prev) || ['can', 'will', 'shall', 'must', 'should'].includes(prev);
      if (PAST_AUX.has(t.lower) && !(['to'].includes(prev))) acc.past++;
      else if (PRES_AUX.has(t.lower) && t.pos === 'AUX' && !afterAux) acc.pres++;
      else if (t.pos === 'VERB' && !afterAux) {
        if (isPastForm(t)) acc.past++;
        else if (/s$/i.test(t.text) && t.lower !== t.lemma) acc.pres++;
        else if (t.lower === t.lemma && ['we', 'they', 'i', 'you', 'these', 'those'].includes(prev)) acc.pres++;
      }
      if (t.pos === 'AUX' && HEDGE_MODAL.has(t.lower)) acc.hm++;
      else if (t.pos === 'VERB' && HEDGE_VERB.has(t.lemma)) acc.hv++;
      else if ((t.pos === 'ADV' || t.pos === 'ADJ') && HEDGE_ADV.has(t.lower)) acc.ha++;
      else if ((t.pos === 'ADV' || t.pos === 'ADJ') && BOOSTER.has(t.lower)) acc.bo++;
      else if (t.pos === 'VERB' && BOOSTER_VERB.has(t.lemma)) acc.bv++;
      if (t.pos === 'NOUN' && t.text.length > 6 && NOMINAL.test(t.text)) acc.nom++;
    });
  }

  function features(text) {
    const { t, nRef } = prep(text);
    const sents = sentences(t);
    const acc = { subj: {}, passive: 0, active: 0, past: 0, pres: 0, hm: 0, hv: 0, ha: 0, bo: 0, bv: 0, nom: 0 };
    const alpha = []; let nw = 0, markers = 0;
    for (const s of sents) {
      const toks = tokenize(s);
      for (const tk of toks) {
        if (tk.type === 'punctuation' || tk.type === 'tabCRLF' || tk.type === 'symbol') continue;
        nw++;
        if (/^[A-Za-z]+$/.test(tk.text)) { alpha.push(tk.lower); if (MARKERS.has(tk.lower)) markers++; }
      }
      analyseSentence(toks, acc);
    }
    const f = { n_words: nw, n_sents: sents.length, n_ref: nRef };
    if (!nw) return f;
    const perK = 1000 / nw;
    f.sent_len = nw / Math.max(1, sents.length);
    f.word_len = alpha.reduce((a, w) => a + w.length, 0) / Math.max(1, alpha.length);
    f.mattr = mattr(alpha);
    const ns = Object.values(acc.subj).reduce((a, b) => a + b, 0);
    for (const c of SUBJ_CLASSES) f['subj_' + c] = ns ? 100 * (acc.subj[c] || 0) / ns : null;
    f.passive_pct = (acc.passive + acc.active) ? 100 * acc.passive / (acc.passive + acc.active) : null;
    f.hedge_modal = acc.hm * perK; f.hedge_verb = acc.hv * perK; f.hedge_adv = acc.ha * perK;
    f.booster = acc.bo * perK; f.booster_verb = acc.bv * perK;
    f.past_pct = (acc.past + acc.pres) ? 100 * acc.past / (acc.past + acc.pres) : null;
    const tx = sents.join(' ');
    for (const [k, r] of Object.entries({ ...MOVES, ...CONN })) f[k] = (tx.match(r) || []).length * perK;
    f.nominal = acc.nom * perK;
    f.markers_per10k = markers * 1e4 / Math.max(1, alpha.length);
    return f;
  }

  // spans for the UI (character offsets in the normalised text)
  const HL = [
    ['marker', new RegExp('\\b(?:' + [...MARKERS].join('|') + ')\\b', 'gi')],
    ['importance', MOVES.importance],
    ['causal', CONN.conn_causal], ['contrast', CONN.conn_contrast], ['additive', CONN.conn_additive],
    ['hedge', new RegExp('\\b(?:may|might|could|would|' + [...HEDGE_ADV].join('|') + '|suggest\\w*|indicat\\w*|appear\\w*|seem\\w*|propos\\w*)\\b', 'gi')],
    ['negation', /\b(?:not|no|never|neither|nor|without|cannot|n't|lack\w*|absence)\b/gi],
    ['passive', new RegExp('\\b(?:is|are|was|were|been|being|be)\\s+(?:\\w+ly\\s+)?(?:\\w+(?:ed|en)|' + [...IRREG_PAST].join('|') + ')\\b', 'gi')],
    ['study_subject', /(?:^|[.!?]\s+)(?:(?:This|The present|The current|Our) (?:study|work|research|analysis|paper|investigation)|(?:These|Our|The) (?:results|findings|data|observations))\b/g],
    ['we', /\b[Ww]e\b/g],
  ];
  function highlight(text) {
    const t = normalise(text); const spans = [];
    for (const [kind, r] of HL) {
      r.lastIndex = 0; let m;
      while ((m = r.exec(t)) !== null) {
        let s = m.index, e = m.index + m[0].length;
        if (kind === 'study_subject') { const lead = m[0].match(/^[.!?]?\s*/)[0].length; s += lead; }
        spans.push({ start: s, end: e, kind });
        if (m[0].length === 0) r.lastIndex++;
      }
    }
    spans.sort((a, b) => a.start - b.start || b.end - a.end);
    const out = []; let last = -1;                       // drop overlaps (first wins)
    for (const sp of spans) if (sp.start >= last) { out.push(sp); last = sp.end; }
    return { text: t, spans: out };
  }
  // counts used by the meaning check between two versions
  function guardCounts(text) {
    const t = normalise(text);
    const c = (r) => (t.match(r) || []).length;
    return { causal: c(CONN.conn_causal), contrast: c(CONN.conn_contrast), hedge: c(HL[5][1]), negation: c(HL[6][1]),
      refs: (t.match(/\[REF\]/g) || []).length, numbers: (t.match(/\d+(?:\.\d+)?/g) || []).length };
  }
  return { features, highlight, guardCounts, FEATURES };
}

if (typeof module !== 'undefined') module.exports = { createExtractor, FEATURES, normalise };
