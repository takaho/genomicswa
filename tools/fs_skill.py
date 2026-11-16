"""Generate compact field-style SKILL.md files for a local LLM (round N).
   python3 fs_skill.py --round 1                 -> skills_r1/<sid>.md
   python3 fs_skill.py --round 2 --adjust adjust_r2.json
adjust json: {sid: {section: {feature: {"mode": "strengthen"|"cap"|"drop"|"keep", "note": str}}}, "_global": {...}}"""
import json, gzip, re, argparse, os, sys
sys.path.insert(0, '../PubMedCorpus'); import skill_corpus as SC

P = json.load(open('profiles.json')); D = json.load(gzip.open('../PubMedCorpus/fieldstyle/digests_all.json.gz', 'rt'))
SECS = ['introduction', 'discussion']
LEX = {'hedge_modal': 'may, might, could, would', 'hedge_verb': 'suggest, indicate, appear, seem, propose',
       'hedge_adv': 'likely, possibly, probably, potentially, generally, relatively, largely, often',
       'booster': 'clearly, indeed, strongly, markedly, dramatically, remarkably',
       'booster_verb': 'show, demonstrate, reveal, confirm, establish, highlight',
       'importance': 'critical, crucial, key, essential, important(ly), fundamental, vital, major',
       'conn_contrast': 'however, although, whereas, in contrast, nevertheless, despite',
       'conn_additive': 'moreover, furthermore, in addition, also, similarly, likewise',
       'conn_causal': 'therefore, thus, hence, consequently, because, as a result',
       'conn_summary': 'together, collectively, taken together, overall, in summary, in conclusion',
       'aim': '"Here, we…", "In this study…", "We aimed to…", "To investigate/determine/assess…"',
       'novelty': '"remains unclear", "little is known", "poorly understood", "novel", "for the first time"',
       'limitation': '"A limitation of…", "should be interpreted with caution", "cannot rule out", "may not generalize"',
       'future': '"Future studies…", "Further research is needed…"'}
NAME = {'sent_len': 'Sentence length', 'word_len': 'Word length', 'mattr': 'Vocabulary variety', 'nominal': 'Nominalisations (-tion, -ment, -ity…)',
        'passive_pct': 'Passive voice', 'past_pct': 'Past tense', 'subj_we': '"We" as subject', 'subj_evidence': 'Findings/data/study as subject',
        'subj_method': 'Method/model/approach as subject', 'subj_human': 'Patients/participants as subject',
        'subj_organism': 'Organisms (mice, plants, strains) as subject', 'subj_pronoun': 'This/these/they as subject',
        'subj_expletive': '"It is…"/"There are…" constructions', 'subj_entity': 'Biological/clinical entities as subject',
        'hedge_modal': 'Modal hedges', 'hedge_verb': 'Hedging verbs', 'hedge_adv': 'Hedging adverbs', 'booster': 'Booster adverbs',
        'booster_verb': 'Booster verbs', 'importance': 'Importance words', 'conn_contrast': 'Contrast connectives',
        'conn_additive': 'Additive connectives', 'conn_causal': 'Causal connectives', 'conn_summary': 'Summary connectives',
        'aim': 'Aim statements', 'novelty': 'Gap/novelty statements', 'limitation': 'Limitation statements', 'future': 'Future-work statements'}
HOW = {  # (more, less)
 'sent_len': ('join closely related short sentences with subordinate clauses (which, whereas, because)', 'split long sentences; one idea per sentence'),
 'word_len': ('prefer precise technical and Latinate terms and noun phrases', 'prefer short plain words and verbs'),
 'mattr': ('vary wording; avoid repeating the same noun or verb in neighbouring sentences', 'repeat key terms consistently instead of synonyms'),
 'nominal': ('express processes as nouns ("the activation of X", "expression", "regulation")', 'express processes as verbs ("X activates Y")'),
 'passive_pct': ('report procedures and established facts in the passive ("X was observed", "Y has been reported")', 'turn passives into active clauses with an explicit agent'),
 'past_pct': ('report earlier studies and this study\'s observations in the past tense', 'use the present tense for established knowledge and interpretation'),
 'subj_we': ('make "we" the subject of what the study did or found ("We found…", "Here, we show…")', 'avoid "we"; make the finding, entity or method the subject, or use the passive'),
 'subj_evidence': ('make findings/data/results/this study the subject ("These findings suggest…")', 'make the entity or "we" the subject instead of data/results/study'),
 'subj_method': ('make the method/model/approach the subject ("This approach allows…")', 'make the finding or entity the subject instead of the method'),
 'subj_human': ('make patients/participants/individuals the subject where the content allows', 'foreground the biology or variable rather than patients/participants'),
 'subj_organism': ('make the organism (mice, plants, strains) the subject where the content allows', 'make the gene, molecule or process the subject rather than the organism'),
 'subj_pronoun': ('refer back with this/these/they/which as subjects', 'repeat the noun instead of this/it/they'),
 'subj_expletive': ('use "It is … that" and "There is/are …" constructions', 'replace "It is known that…"/"There are…" with the entity as subject'),
 'subj_entity': ('make genes, proteins, cells, compounds, diseases or variables the grammatical subjects', 'make "we", the study or the finding the subject instead of the entity'),
}
for k in ['hedge_modal', 'hedge_verb', 'hedge_adv', 'booster', 'booster_verb', 'importance', 'conn_contrast', 'conn_additive',
          'conn_causal', 'conn_summary', 'aim', 'novelty', 'limitation', 'future']:
    HOW[k] = (f'use more of: {LEX[k]}', f'use fewer of: {LEX[k]}')
HOW['limitation'] = ('where the excerpt mentions constraints, name them as limitations: ' + LEX['limitation'], 'avoid explicit limitation formulas: ' + LEX['limitation'])
HOW['future'] = ('phrase open questions as: ' + LEX['future'], 'avoid future-work formulas: ' + LEX['future'])
HOW['novelty'] = ('where the excerpt implies a gap, state it with: ' + LEX['novelty'], 'avoid gap/novelty formulas: ' + LEX['novelty'])
HOW['aim'] = ('state the aim explicitly: ' + LEX['aim'], 'avoid explicit aim formulas: ' + LEX['aim'])

def qty(k, v):
    if k == 'sent_len': return f'about {v:.0f} words per sentence'
    if k == 'word_len': return f'about {v:.2f} characters per word'
    if k == 'mattr': return f'MATTR about {v:.2f}'
    if k.endswith('_pct') or k.startswith('subj_'): return f'about {v/10:.1f} in 10 ' + ('finite verbs' if k == 'past_pct' else 'clause subjects')
    return f'about {v*0.3:.1f} per 300 words'

RHET = SC.FUNC | set(w for s in LEX.values() for w in re.findall(r"[a-z]+", s.lower())) | set("""study studies data results result findings finding
present previous previously recent recently shown show showed shows found observed reported suggest suggests suggested known well role
roles current our us one two first second finally next taken together overall evidence analysis work research paper report aim aimed sought
investigate investigated examine examined determine determined effect effects potential possible likely also other new similar consistent
line contrast addition conclusion summary limitation limitations future needed required remains unclear unknown little understood poorly
however furthermore moreover notably interestingly importantly additionally specifically particular particularly given demonstrated
indicated indicate indicates revealed reveal confirmed confirm explore explored address addressed whether many several some all
increasing increasingly growing number""".split())
def rhetorical(p): return all(w in RHET for w in p.split())

def build(sid, adj=None, rnd=1):
    adj = adj or {}; d = D[sid]; pr = P['profiles'][sid]; name = P['names'][sid]
    L = [f'# {name}: research-article prose style (2024–2025)', '',
         f'Use this to rewrite Introduction or Discussion prose so that it reads like a current {name} article. '
         'Change style only: never change numbers, statistics, citations, abbreviations, technical terms, claims or the subject matter.', '',
         f'Evidence: {d["n_articles"]} open-access {name} articles (2024–2025) compared with 90 life-science fields. '
         'Targets are this field\'s averages; "all fields" gives the cross-field average for contrast.', '']
    g = adj.get('_global', {})
    if g.get('preamble'): L += [g['preamble'], '']
    for sec in SECS:
        L += [f'## {sec.capitalize()}: what to change', '']
        feats = P['selected'][sid][sec]
        extra = [k for k, v in adj.get(sec, {}).items() if v.get('mode') in ('strengthen', 'cap') and k not in feats]
        n = 0
        for k in feats + extra:
            a = adj.get(sec, {}).get(k, {}); mode = a.get('mode', 'keep')
            if mode == 'drop': continue
            x = pr[sec][k]; up = x['d'] > 0
            how = HOW[k][0 if up else 1]
            line = (f'- **{NAME[k]}: {"more" if up else "less"} than other fields** — target {qty(k, x['mean'])} '
                    f'(all fields {qty(k, x['all_mean'])}). How: {how}.')
            if mode == 'strengthen': line += ' ' + a.get('note', 'Apply this throughout the excerpt, not just once.')
            if mode == 'cap': line += ' ' + a.get('note', 'Do not go beyond the target; change only as much as needed.')
            L.append(line); n += 1
        L.append('')
        op = [o[0] for o in d['openers'][sec] if rhetorical(o[0])][:8]
        bu = [b[0] for b in d['bundles'][sec] if rhetorical(b[0])][:8]
        if op or bu:
            L.append(f'Typical {sec} phrasing in {name} (use where it fits the content): ' +
                     '; '.join(f'"{x[:1].upper() + x[1:]} …"' for x in op) + ('; ' if op and bu else '') + '; '.join(f'"…{x}…"' for x in bu))
            L.append('')
    m = d['llm_markers']; top = ', '.join(w for w, r in m['top'][:10])
    L += ['## Vocabulary', f'- Words often added by AI polishing ({top}) occur about {m["field_per10k"]*0.03:.1f} times per 300 words in {name}; do not exceed that.', '']
    ex = [(s, e) for s in SECS for e in d['exemplars'].get(s, [])[:1]]
    if ex:
        L += ['## Style illustration (verbatim, CC BY; do not copy content)']
        for s, e in ex:
            sents = SC.SPLIT.split(e['text']); t = ''
            for x in sents:
                if len((t + ' ' + x).split()) > 90 and t: break
                t = (t + ' ' + x).strip()
            L += [f'- {s.capitalize()} ({e["pmcid"]}, {e["journal"]}, {e["year"]}): "{t}"']
        L.append('')
    L += ['## Procedure', '1. Identify which of the targets above the excerpt misses.',
          '2. Rewrite sentence by sentence, moving each of those features toward its target and leaving the rest unchanged.',
          '3. Check that every number, [REF] marker, abbreviation and technical term is still present and that no claim was added or removed.']
    if g.get('procedure_extra'): L += g['procedure_extra']
    return '\n'.join(L) + '\n'

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--round', type=int, default=1); ap.add_argument('--adjust', default='')
    a = ap.parse_args(); A = json.load(open(a.adjust)) if a.adjust else {}
    od = f'skills_r{a.round}'; os.makedirs(od, exist_ok=True)
    for sid in P['names']:
        adj = dict(A.get(sid, {})); adj['_global'] = A.get('_global', {})
        open(f'{od}/{sid}.md', 'w').write(build(sid, adj, a.round))
    print(len(P['names']), 'skills ->', od)
