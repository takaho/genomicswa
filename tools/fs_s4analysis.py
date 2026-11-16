"""s4 evaluation: original vs d2 vs s3a vs s4 on the s4 excerpts.
P(EN) (field-adjusted English-speaking-author classifier), P(pre), LLM index, markers, field logp/rank,
distance to EN-pre target on selection features and on held-out features, operations, guard reasons, fidelity."""
import json, gzip, re, collections, sys, numpy as np, pandas as pd
from scipy import stats
ARM = sys.argv[1] if len(sys.argv) > 1 else 's4'
U = '../PubMedCorpus/fieldstyle'
R = pd.read_csv('eval2_rows.csv', dtype={'target': str, 'source': str})
EN = json.load(open('profiles_pre_en.json'))['profiles']; CL = json.load(open('en_classifier.json'))
S = {i['id']: i for i in json.load(open('sample.json'))['items']}
C = {json.loads(l)['id']: json.loads(l) for l in open(f'{U}/{ARM}_candidates.jsonl')}
IDS = sorted(set(C) & set(R[R.version == ARM].id))
VERS = list(dict.fromkeys([v for v in ['original', 'd2', 's3a', ARM] if (R.version == v).any()]))
V = {v: R[R.version == v].set_index('id').reindex(IDS) for v in VERS}
def p_en(row):
    c = CL[row['section']]; t = EN[row['target']][row['section']]
    x = np.array([((row['f_' + k] or 0) - t[k]['field_all_mean']) for k in c['features']])
    z = (x - np.array(c['mean'])) / np.array(c['scale'])
    return float(1 / (1 + np.exp(-(np.dot(c['coef'], z) + c['intercept']))))
for v in VERS: V[v]['p_en'] = [p_en(V[v].loc[i]) if not V[v].loc[i].isna().all() else np.nan for i in IDS]
SEL = ['sent_len', 'passive_pct', 'nominal', 'word_len', 'subj_we', 'past_pct', 'importance']
HELD = ['conn_causal', 'mattr', 'hedge_adv', 'booster_verb', 'subj_evidence']
def dist(v, keys):
    return np.array([np.mean([abs((V[v].loc[i]['f_' + k] or 0) - EN[V['original'].loc[i].target][V['original'].loc[i].section][k]['mean']) /
                              EN[V['original'].loc[i].target][V['original'].loc[i].section][k]['all_sd'] for k in keys]) for i in IDS])
for v in VERS: V[v]['dist_sel'] = dist(v, SEL); V[v]['dist_held'] = dist(v, HELD)
MET = ['p_en', 'p_pre', 'llm_index', 'markers', 'dist_sel', 'dist_held', 'logp', 'rank']
lvl = pd.DataFrame({v: V[v][MET].mean() for v in VERS}).T
nat = R[R.version == 'native'].copy(); nat['p_en'] = [p_en(r) for _, r in nat.iterrows()]
lvl.loc['native_post'] = [nat[m].mean() if m in nat else np.nan for m in MET]
print('n =', len(IDS)); print(lvl.round(3)); lvl.round(4).to_csv(f'report_{ARM}_levels.csv')
rows = []
for m in MET:
    for a, b in [(ARM, 'original'), (ARM, 'd2'), (ARM, 's3a')]:
        if b not in V or a == b: continue
        x = (V[a][m] - V[b][m]).dropna()
        rows.append(dict(metric=m, comparison=f'{a}-{b}', n=len(x), mean=x.mean(), se=x.std() / np.sqrt(len(x)), wilcoxon_p=stats.wilcoxon(x).pvalue if (x != 0).any() else np.nan))
T = pd.DataFrame(rows); print(T.round(4).to_string()); T.round(5).to_csv(f'report_{ARM}_tests.csv', index=False)
fr = []
for k in SEL + HELD:
    tg = np.array([EN[V['original'].loc[i].target][V['original'].loc[i].section][k]['mean'] for i in IDS]); sd = np.array([EN[V['original'].loc[i].target][V['original'].loc[i].section][k]['all_sd'] for i in IDS])
    x0 = V['original']['f_' + k].values
    for v in VERS[1:]:
        x1 = V[v]['f_' + k].values; ok = ~np.isnan(x1)
        fr.append(dict(feature=k, role='selection' if k in SEL else 'held-out', version=v, orig=np.nanmean(x0), new=np.nanmean(x1), en_target=tg.mean(),
                       frac_dist_closed=1 - np.mean(np.abs(x1[ok] - tg[ok]) / sd[ok]) / np.mean(np.abs(x0[ok] - tg[ok]) / sd[ok])))
FT = pd.DataFrame(fr); print(FT.pivot(index=['feature', 'role'], columns='version', values='frac_dist_closed').round(3)); FT.round(4).to_csv(f'report_{ARM}_features.csv', index=False)
def pick(r):
    if r['chosen'] == 'base': return None
    v = [c for c in r['candidates'] if c.get('valid')] or [c for c in r['candidates'] if 'text' in c]
    return min(v, key=lambda c: abs(c['dist'] - r['chosen_dist']))
op = collections.defaultdict(collections.Counter); guards = collections.Counter(); ch = collections.Counter()
for r in C.values():
    ch[r['chosen']] += 1
    for o, _ in r['ops']: op[o]['planned'] += 1
    for c in r['candidates']:
        for e in c.get('edits', {}).values():
            op[e['op']]['attempts'] += 1
            if e.get('reverted'): op[e['op']]['reverted'] += 1; guards[(e['op'], e.get('guard') or 'coverage/ref/lead')] += 1
    c = pick(r)
    if c:
        for e in c['edits'].values():
            if not e.get('reverted') and e['before'] != e['after']: op[e['op']]['changed_in_chosen'] += 1
OP = pd.DataFrame(op).T.fillna(0).astype(int); OP['revert_rate'] = OP.reverted / OP.attempts; print(OP); print(ch)
OP.to_csv(f'report_{ARM}_ops.csv'); pd.Series({f'{a}|{b}': n for (a, b), n in guards.items()}).to_csv(f'report_{ARM}_guards.csv')
print(sorted(guards.items(), key=lambda x: -x[1]))
print(V[ARM][['numbers_kept', 'abbrev_kept', 'refs_kept', 'len_ratio']].describe().round(3))
SPL = re.compile(r'(?<=[.!?])\s+(?=[A-Z(\[])'); WE = re.compile(r'\b(we|our|us)\b', re.I)
TX = {json.loads(l)['id']: json.loads(l)['text'] for l in gzip.open(f'{U}/{ARM}_outputs.jsonl.gz', 'rt')}
def cw(t): s = [x for x in SPL.split(t.replace('\n', ' ')) if '[REF]' in x]; return sum(bool(WE.search(x)) for x in s), len(s)
a0 = sum(cw(S[i]['text'])[0] for i in IDS); a1 = sum(cw(TX[i])[0] for i in IDS); n0 = sum(cw(S[i]['text'])[1] for i in IDS)
print(f'we in cited sentences: original {a0}, {ARM} {a1} (of {n0})')
