"""(fs_skill3: adds variant d3 = 2019-22 English-speaking-author style + meaning guards)
Round-2 SKILL generator (revised from round-1 diagnostics) and de-LLM variant.
   python3 fs_skill2.py r2   -> skills_r2/<sid>.md   (current field style, revised)
   python3 fs_skill2.py d2   -> skills_d2/<sid>.md   (2019-22 field style + removal of AI-polishing style)
Reads r1_feature_moves.csv (round-1 diagnostics)."""
import json, gzip, sys, os, numpy as np, pandas as pd
import fs_skill as S1
sys.path.insert(0, '/mnt/attach/outputs/PubMedCorpus'); import rewrite_eval as RE
P = S1.P; PRE = json.load(open('profiles_pre.json'))['profiles']
_EN = json.load(open('profiles_pre_en.json'))['profiles']
PRE_EN = {sid: {sec: {k: dict(PRE[sid][sec][k], mean=_EN[sid][sec][k]['mean'],
                             d=(_EN[sid][sec][k]['mean'] - PRE[sid][sec][k]['all_mean']) / PRE[sid][sec][k]['all_sd'])
                      for k in PRE[sid][sec]} for sec in PRE[sid]} for sid in PRE}
DPRE = json.load(gzip.open('/mnt/user-data/uploads/PubMedCorpus/fieldstyle/digests_pre_all.json.gz', 'rt'))
SECS = S1.SECS; CTRL = json.load(open('classifier.json'))['introduction']['features']
CONTENT_BOUND = {'subj_human', 'subj_organism', 'subj_method'}
NEEDS_CONTENT = {'limitation', 'future', 'novelty', 'aim'}
UNMOVABLE = CONTENT_BOUND | NEEDS_CONTENT

# ---- round-1 diagnostics
M = pd.read_csv('r1_feature_moves.csv', dtype={'target': str})
s = M[M.selected & (M.need_sd.abs() >= 0.25)].copy(); s['ratio'] = s.moved_sd / s.need_sd
GLOB = s.groupby('feature').ratio.agg(med='median', over=lambda x: (x > 1.5).mean(), wrong=lambda x: (x < -0.1).mean(), none=lambda x: x.between(-0.1, 0.25).mean())
FLD = s.groupby(['target', 'section', 'feature']).ratio.median()
OVERSHOOT = set(GLOB[(GLOB.over >= 0.3) | (GLOB.med > 1.3)].index)
WRONGPRONE = set(GLOB[GLOB.wrong >= 0.25].index)

# before -> after pairs (illustrate the operation, content-neutral)
EX = {
 ('sent_len', 1): '"X was measured. It increased with age." → "X, which was measured in all samples, increased with age."',
 ('sent_len', 0): '"X, which was measured in all samples and which increased with age, was associated with Y." → "X was measured in all samples. It increased with age and was associated with Y."',
 ('word_len', 1): '"X goes up when Y is blocked" → "X increases upon inhibition of Y"',
 ('word_len', 0): '"X increases upon inhibition of Y" → "X goes up when Y is blocked"',
 ('nominal', 1): '"Y activates X, which changes how cells grow" → "Activation of X by Y alters cell proliferation"',
 ('nominal', 0): '"Activation of X by Y alters cell proliferation" → "Y activates X, which changes how cells grow"',
 ('passive_pct', 1): '"We measured X in all samples" → "X was measured in all samples"',
 ('passive_pct', 0): '"X was measured in all samples" → "We measured X in all samples"',
 ('past_pct', 1): '"Previous studies show that X regulates Y" → "Previous studies showed that X regulated Y"',
 ('past_pct', 0): '"Previous studies showed that X regulated Y" → "Previous studies show that X regulates Y"',
 ('mattr', 1): 'avoid repeating "increase" in neighbouring sentences: "rise", "elevation", "higher levels"',
 ('mattr', 0): 'keep one term for one concept: do not alternate "rise", "elevation", "increase"',
 ('subj_we', 1): '"These results show that X…" → "We show that X…"',
 ('subj_we', 0): '"We found that X increased" → "X increased"',
 ('subj_evidence', 1): '"X increased, suggesting…" → "These findings suggest that X…"',
 ('subj_evidence', 0): '"These data indicate that X binds Y" → "X binds Y"',
 ('subj_entity', 1): '"We observed that X binds Y" → "X binds Y"',
 ('subj_entity', 0): '"X binds Y" → "We found that X binds Y"',
 ('subj_pronoun', 1): '"X binds Y. The binding of X to Y…" → "X binds Y. This…"',
 ('subj_pronoun', 0): '"X binds Y. This…" → "X binds Y. The binding of X to Y…"',
 ('subj_expletive', 1): '"X is known to regulate Y" → "It is known that X regulates Y"',
 ('subj_expletive', 0): '"It is known that X regulates Y" → "X regulates Y"',
 ('hedge_modal', 1): '"X explains Y" → "X may explain Y"', ('hedge_modal', 0): '"X may explain Y" → "X explains Y" (only where the excerpt states it as a finding)',
 ('hedge_verb', 1): '"X causes Y" → "These data suggest that X causes Y"', ('hedge_verb', 0): '"This suggests that X causes Y" → "X causes Y" (only where stated as a finding)',
 ('hedge_adv', 1): '"X is involved" → "X is likely involved"', ('hedge_adv', 0): '"X is likely involved" → "X is involved" (only where stated as a finding)',
 ('booster', 1): '"X increased Y" → "X markedly increased Y"', ('booster', 0): '"X markedly increased Y" → "X increased Y"',
 ('booster_verb', 1): '"We found that X…" → "We show that X…"', ('booster_verb', 0): '"These results highlight/reveal that X…" → "These results indicate that X…"',
 ('importance', 1): '"X regulates Y" → "X is a key regulator of Y"', ('importance', 0): '"X plays a crucial role in Y" → "X regulates Y"',
 ('conn_causal', 1): '"X was absent. Y did not form." → "X was absent; therefore, Y did not form."', ('conn_causal', 0): '"Therefore, X…" → "X…" or "As a result,…" only once',
 ('conn_additive', 1): '"X… Y…" → "X… In addition, Y…"', ('conn_additive', 0): '"Moreover, X…" → "X…"',
 ('conn_contrast', 1): '"X… Y…" → "X…; however, Y…"', ('conn_contrast', 0): '"However, X…" → "X…" where no contrast is meant',
 ('conn_summary', 1): '"…" → "Taken together, …"', ('conn_summary', 0): '"Collectively, these…" → "These…"',
}
def per300(k, v):
    if k.endswith('_pct') or k.startswith('subj_') or k in ('sent_len', 'word_len', 'mattr'): return None
    return v * 0.3

def line(k, x, mode, label_all='all fields'):
    up = x['d'] > 0; how = S1.HOW[k][0 if up else 1]
    if PRE_MODE[0] and k == 'booster_verb': how = how.replace(', highlight', '')
    if EN_MODE[0] and k == 'passive_pct' and not up: how = 'write what the authors themselves did with "we" as the subject; never in sentences that report earlier work ([REF]), and keep passives whose agent is unknown or other researchers'
    if EN_MODE[0] and k == 'booster_verb' and not up: how = 'prefer plain "show" or "find" to "demonstrate", "reveal", "highlight", "underscore"; do not replace them with hedges such as "suggest" or "indicate"'
    if EN_MODE[0] and k == 'sent_len' and up: how = 'join a short sentence with the next one only when the second refers back to the first, using "which" or "and"; never add whereas/because'
    L = f'- **{S1.NAME[k]}: {"more" if up else "less"} than other fields** — target {S1.qty(k, x["mean"])} ({label_all} {S1.qty(k, x["all_mean"])}). How: {how}.'
    ex = EX.get((k, int(up)))
    if EN_MODE[0] and (k, int(up)) == ('booster_verb', 0): ex = '"These results reveal that X…" → "These results show that X…"'
    if EN_MODE[0] and (k, int(up)) == ('passive_pct', 0): ex = '"Samples were collected from 12 sites" → "We collected samples from 12 sites"'
    if mode in ('strengthen', 'add') and ex: L += f' Example: {ex}.'
    c = per300(k, x['mean'])
    if mode == 'strengthen': L += ' Apply in several places.'
    if mode == 'cap':
        L += f' Do not overshoot: stop at the target' + (f' (at most about {max(1, round(c + 0.5))} per 300 words)' if c is not None else '') + '.'
    return L

def choose(sid, sec, prof):
    """movable features ranked by |d|; mode from round-1 response"""
    keep = {'hedge_modal', 'hedge_verb', 'hedge_adv', 'conn_causal', 'conn_contrast'} if EN_MODE[0] else set()   # d3: never change hedging or logical links
    ranked = sorted([k for k in CTRL if k not in UNMOVABLE | keep], key=lambda k: -abs(prof[sec][k]['d']))
    feats = [k for k in ranked if abs(prof[sec][k]['d']) >= 0.2][:6] or ranked[:3]
    out = []
    for k in feats:
        r = FLD.get((sid, sec, k), np.nan)
        if k in OVERSHOOT or (not np.isnan(r) and r > 1.5): mode = 'cap'
        elif (not np.isnan(r) and r < 0.25) or k in WRONGPRONE or (k, sec) and np.isnan(r): mode = 'strengthen'
        else: mode = 'keep'
        out.append((k, mode))
    return out

PRE_MODE = [False]; EN_MODE = [False]
def build(sid, variant):
    pre = variant in ('d2', 'd3'); en = variant == 'd3'; name = P['names'][sid]; PRE_MODE[0] = pre; EN_MODE[0] = en
    prof = (PRE_EN[sid] if en else PRE[sid]) if pre else P['profiles'][sid]; dg = DPRE[sid] if pre else S1.D[sid]
    period = ('2019–2022, English-speaking authors (before AI writing assistants)' if en else '2019–2022 (before AI writing assistants)') if pre else '2024–2025'
    L = [f'# {name}: research-article prose style, {period}', '',
         f'Use this to rewrite Introduction or Discussion prose so that it reads like a {name} article of {period}. '
         'Change style only: never change numbers, statistics, citations, abbreviations, technical terms, claims or the subject matter.', '',
         f'Evidence: open-access {name} articles ({period}) compared with 90 life-science fields. Targets are this field\'s averages; "all fields" gives the cross-field average.', '',
         '## General rules (learned from earlier rewriting runs)',
         '- Change only the features listed below, in the direction and by the amount shown. Leave everything else as in the original.',
         '- For features marked "Apply in several places", earlier rewrites changed too little: count the feature in the original and change it throughout the excerpt, not just once.',
         '- Do not shorten sentences, split sentences, or turn passive clauses into active ones unless a target below asks for it; otherwise keep the original sentence length and voice.',
         '- Do not change who or what the sentences are about (patients, animals, plants, methods): that follows from the subject matter.',
         '- Do not add aims, limitations, novelty claims or future-work statements that the original does not contain.']
    if en:
        L += ['- Targets are the averages of papers in this field whose last author worked in an English-speaking country (US, UK, Canada, Australia, New Zealand, Ireland); "all fields" is the average of all 2019–2022 papers.',
              '- Never add a word of contrast or cause (whereas, while, although, but, however, because, since, thus, therefore, hence, so, consequently) that the original does not have: it changes the argument.',
              '- Keep every hedge (may, might, could, likely, suggest, appear, potential) and every negation (not, no, without): their number must not change.',
              '- When joining sentences, use "and", "which" or a semicolon, and only when the second sentence refers back to the first (It, They, This …).']
    L += ['']
    for sec in SECS:
        L += [f'## {sec.capitalize()}: what to change (most important first)', '']
        for k, mode in choose(sid, sec, prof): L.append(line(k, prof[sec][k], mode))
        ctx = [k for k in sorted(UNMOVABLE, key=lambda k: -abs(prof[sec][k]['d'])) if abs(prof[sec][k]['d']) >= 0.25][:3]
        if ctx:
            L.append('- Context only (do not force): ' + '; '.join(f'{S1.NAME[k].lower()} is {"more" if prof[sec][k]["d"] > 0 else "less"} common in {name}' for k in ctx) +
                     '. Where the original already contains such content, phrase it in the field\'s way.')
        L.append('')
        op = [o[0] for o in dg['openers'][sec] if S1.rhetorical(o[0])][:6]; bu = [b[0] for b in dg['bundles'][sec] if S1.rhetorical(b[0])][:6]
        if op or bu:
            L += [f'Typical {sec} phrasing in {name} (use where it fits): ' + '; '.join(f'"{x[:1].upper() + x[1:]} …"' for x in op) + ('; ' if op and bu else '') + '; '.join(f'"…{x}…"' for x in bu), '']
    m = dg['llm_markers']
    if pre:
        ref = json.load(open('llm_index_ref.json'))
        L += ['## Remove AI-polishing style', f'Recent text often carries vocabulary and habits that became common after 2023. In {name} articles of 2019–2022:',
              f'- Words such as ' + ', '.join(sorted(RE.WORDMAP)[:0]) + 'additionally, notably, crucial, pivotal, robust, comprehensive, insights, landscape, interplay, enhance, elucidate, underscore, showcase, foster, harness, delve, intricate, multifaceted '
              f'occurred about {m["field_per10k"]*0.03:.1f} times per 300 words in total. Replace them with plain wording, for example: ' +
              '; '.join(f'{a} → {b}' for a, b in [('additionally', 'in addition / also'), ('notably', '(delete) / in particular'), ('crucial / pivotal', 'important / key, or state the role'),
                                                  ('robust', 'strong / consistent'), ('insights', 'information / understanding'), ('enhance', 'increase / improve'),
                                                  ('elucidate', 'determine / define'), ('underscore / highlight', 'indicate / show'), ('landscape', 'profile / range'), ('interplay', 'interaction')]) + '.',
              ('- Do not add "therefore", "thus" or "because": English-speaking authors used fewer causal connectives than other authors; keep only those already in the original.' if en else
               '- Restore explicit causal links where the reasoning is causal: "therefore", "thus", "because" (these were about one third more frequent before 2023).'),
              '- Prefer verbs to abstract nouns and plain words to long Latinate ones ("X increases upon inhibition of Y" → "X increases when Y is inhibited").',
              '- Use "we" for what the authors did and found, rather than "This study/These findings" as subjects.',
              ('- English-speaking authors used the passive less than other authors: keep existing passives, but write what the authors did with "we" ("We measured X", not "X was measured by us").' if en else
               '- Keep established methods and findings in the passive where the field used it ("X was measured", "Y has been reported").'),
              '- Avoid stacking importance words (crucial, key, essential, pivotal) and "highlight/underscore/reveal".']
        for sec in SECS:
            x = prof[sec]
            L.append(f'- 2019–2022 {name} {sec} targets{" (English-speaking authors)" if en else ""} for these habits: causal connectives {S1.qty("conn_causal", x["conn_causal"]["mean"])}; '
                     f'importance words {S1.qty("importance", x["importance"]["mean"])}; nominalisations {S1.qty("nominal", x["nominal"]["mean"])}; '
                     f'"we" as subject {S1.qty("subj_we", x["subj_we"]["mean"])}; findings/data/study as subject {S1.qty("subj_evidence", x["subj_evidence"]["mean"])}; '
                     f'passive {S1.qty("passive_pct", x["passive_pct"]["mean"])}; word length {S1.qty("word_len", x["word_len"]["mean"])}.')
        L.append('')
    else:
        top = ', '.join(w for w, r in m['top'][:10])
        L += ['## Vocabulary', f'- Words often added by AI polishing ({top}) occur about {m["field_per10k"]*0.03:.1f} times per 300 words in {name}; do not exceed that, and do not add them where the original has none.', '']
    ex = [(s_, e) for s_ in SECS for e in dg['exemplars'].get(s_, [])[:1]]
    if ex:
        L += [f'## Style illustration ({name}, {period}; verbatim, CC BY; do not copy content)']
        for s_, e in ex:
            t = ''
            for x in S1.SC.SPLIT.split(e['text']):
                if len((t + ' ' + x).split()) > 90 and t: break
                t = (t + ' ' + x).strip()
            L.append(f'- {s_.capitalize()} ({e["pmcid"]}, {e["journal"]}, {e["year"]}): "{t}"')
        L.append('')
    L += ['## Procedure', '1. For each feature listed for this section, note how the original compares with the target.',
          '2. Rewrite sentence by sentence, applying only the listed changes; keep sentence length and voice unless listed.',
          '3. Check: every number, [REF] marker, abbreviation and technical term is still present; no claim added or removed; listed features moved toward (not beyond) their targets.']
    return '\n'.join(L) + '\n'

if __name__ == '__main__':
    v = sys.argv[1]; od = f'skills_{v}'; os.makedirs(od, exist_ok=True)
    T = {}
    for sid in P['names']:
        open(f'{od}/{sid}.md', 'w').write(build(sid, v))
        prof = (PRE_EN[sid] if v == 'd3' else PRE[sid]) if v in ('d2', 'd3') else P['profiles'][sid]
        T[sid] = {sec: choose(sid, sec, prof) for sec in SECS}
    json.dump(T, open(f'targets_{v}.json', 'w'))
    print(v, len(P['names']), 'skills; overshoot-capped:', sorted(OVERSHOOT), '; wrong-prone:', sorted(WRONGPRONE))
