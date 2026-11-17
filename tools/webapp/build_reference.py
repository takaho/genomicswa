"""Build docs/data/reference.json for the Style map web app from features computed with src/extractor.js.
   python3 build_reference.py js_features150.csv authorship_countries.csv subfield_map.csv targets_d3.json names.json out.json
"""
import json, sys, numpy as np, pandas as pd
from sklearn.decomposition import PCA

feat_csv, ctry_csv, map_csv, tgt_json, names_json, out = sys.argv[1:7]
J = pd.read_csv(feat_csv, dtype={'subfield_id': str})
C = pd.read_csv(ctry_csv, dtype=str)[['pmcid', 'last_country']]
J = J.merge(C, on='pmcid', how='left')
J['period'] = np.where(J.year <= 2022, 'pre', 'post')
EN = {'US', 'GB', 'CA', 'AU', 'NZ', 'IE'}
REGIONS = {
    'English-speaking': EN,
    'Continental Europe': {'DE', 'FR', 'IT', 'ES', 'NL', 'SE', 'CH', 'PL', 'BE', 'AT', 'DK', 'NO', 'FI', 'PT', 'CZ', 'GR', 'HU', 'IE_'},
    'Japan & Korea': {'JP', 'KR'},
    'China & Taiwan': {'CN', 'TW', 'HK'},
    'Middle East & South Asia': {'IR', 'TR', 'SA', 'EG', 'IN', 'PK', 'BD', 'IQ', 'JO', 'AE', 'QA', 'LB', 'KW'},
}
J['region'] = None
for r, s in REGIONS.items(): J.loc[J.last_country.isin(s), 'region'] = r
J['en'] = J.last_country.isin(EN)

ALL = ['sent_len', 'word_len', 'mattr', 'subj_we', 'subj_evidence', 'subj_method', 'subj_human', 'subj_organism', 'subj_pronoun',
       'subj_expletive', 'subj_entity', 'passive_pct', 'hedge_modal', 'hedge_verb', 'hedge_adv', 'booster', 'booster_verb', 'past_pct',
       'aim', 'novelty', 'importance', 'limitation', 'future', 'conn_contrast', 'conn_additive', 'conn_causal', 'conn_summary', 'nominal']
APPROX = ['subj_expletive', 'subj_pronoun']                       # r < 0.7 with the spaCy version: not used on the map axes
MAP = [k for k in ALL if k not in APPROX]
LLM = {'word_len': 1, 'mattr': 1, 'nominal': 1, 'importance': 1, 'booster_verb': 1, 'conn_causal': -1, 'passive_pct': -1}
names = json.load(open(names_json)); M = pd.read_csv(map_csv, dtype={'subfield_id': str}).set_index('subfield_id')
CLUSTERS = {1: 'Mechanistic bioscience', 2: 'Applied bio / pharma', 3: 'Organismal & lab biology', 4: 'Clinical medicine',
            5: 'Computational / structural', 6: 'Behavioural & health services'}
T = json.load(open(tgt_json)); Q = [5, 25, 50, 75, 95]
ref = {'features': ALL, 'map_features': MAP, 'approximate': APPROX, 'quantiles': Q,
       'fields': {sid: {'name': names.get(sid, sid), 'cluster': int(M.loc[sid, 'cluster']) if sid in M.index else None} for sid in sorted(J.subfield_id.unique())},
       'clusters': CLUSTERS, 'regions': list(REGIONS), 'sections': {}}
r3 = lambda a: [round(float(x), 4) for x in a]

for sec in ['introduction', 'discussion']:
    S = J[J.section == sec].copy()
    for k in ALL: S[k] = S[k].astype(float).fillna(S[k].median())
    pre = S[S.period == 'pre']; mu = pre[ALL].mean(); sd = pre[ALL].std().replace(0, 1)
    Z = (S[ALL] - mu) / sd; Z.columns = ALL
    S = pd.concat([S.drop(columns=ALL), Z.add_prefix('z_')], axis=1); zc = ['z_' + k for k in MAP]
    P = S[S.period == 'pre']
    # PCA on field medians (pre-LLM)
    med = P.groupby('subfield_id')[zc].median()
    pca = PCA(2).fit(med.values); xy = pca.transform(med.values)
    load = pd.DataFrame(pca.components_.T, index=MAP, columns=['pc1', 'pc2'])
    def ends(c):
        s = load[c].sort_values(); return {'neg': list(s.index[:4]), 'pos': list(s.index[::-1][:4])}
    # field-adjusted directions
    fm = P.groupby('subfield_id')[zc].mean()
    def within(df):
        return df[zc] - fm.reindex(df.subfield_id).values
    Wpre = within(P); Wpost = within(S[S.period == 'post'])
    d_period = Wpost.mean() - Wpre.mean(); u_p = (d_period / np.linalg.norm(d_period)).values
    d_en = Wpre[P.en.values].mean() - Wpre[~P.en.values].mean(); u_e = (d_en / np.linalg.norm(d_en)).values
    proj = lambda W, u: W.values @ u
    pre_p, post_p = proj(Wpre, u_p).mean(), proj(Wpost, u_p).mean()
    non_e, en_e = proj(Wpre[~P.en.values], u_e).mean(), proj(Wpre[P.en.values], u_e).mean()
    sc_p = lambda v: (v - pre_p) / (post_p - pre_p); sc_e = lambda v: (v - non_e) / (en_e - non_e)
    regions = {}
    for rname in REGIONS:
        m = P.region.values == rname
        if m.sum() >= 50: regions[rname] = [round(float(sc_p(proj(Wpre[m], u_p).mean())), 3), round(float(sc_e(proj(Wpre[m], u_e).mean())), 3), int(m.sum())]
    # quantiles per field x group (raw feature scale)
    quant = {'pre': {}, 'pre_en': {}, 'post': {}}; ns = {'pre': {}, 'pre_en': {}, 'post': {}}
    raw = J[J.section == sec]
    for g, mask in [('pre', raw.period == 'pre'), ('pre_en', (raw.period == 'pre') & raw.en), ('post', raw.period == 'post')]:
        G = raw[mask]
        for sid, d in list(G.groupby('subfield_id')) + [('ALL', G)]:
            if len(d) < 15: continue
            q = np.nanpercentile(d[ALL].astype(float).values, Q, axis=0)
            quant[g][sid] = {k: r3(q[:, i]) for i, k in enumerate(ALL)}; ns[g][sid] = int(len(d))
    # SKILL d3 targets: English-speaking-author field means (shrunk toward field mean + global EN offset), JS scale
    rp = raw[raw.period == 'pre']; glob_off = (rp[rp.en][ALL].mean() - rp[ALL].mean())
    targets = {}
    for sid, d in rp.groupby('subfield_id'):
        e = d[d.en]; n = len(e); m_all = d[ALL].mean()
        m_en = e[ALL].mean() if n else m_all + glob_off
        shr = m_all + (n * (m_en - m_all) + 50 * glob_off) / (n + 50)
        sel = [k for k, _ in T.get(sid, {}).get(sec, [])]
        targets[sid] = {'selected': sel, 'values': {k: round(float(shr[k]), 4) for k in ALL}}
    llm_ref = {k: {'mean': round(float(mu[k]), 4), 'sd': round(float(sd[k]), 4), 'sign': s} for k, s in LLM.items()}
    ref['sections'][sec] = {
        'z_mean': r3(mu[MAP].values), 'z_sd': r3(sd[MAP].values),
        'pca': {'center': r3(pca.mean_), 'components': [r3(c) for c in pca.components_], 'explained': r3(pca.explained_variance_ratio_),
                'fields': {sid: r3(xy[i]) for i, sid in enumerate(med.index)}, 'pc1': ends('pc1'), 'pc2': ends('pc2')},
        'axes': {'field_mean_z': {sid: r3(fm.loc[sid].values) for sid in fm.index}, 'u_period': r3(u_p), 'u_en': r3(u_e),
                 'period_ref': [round(float(pre_p), 4), round(float(post_p), 4)], 'en_ref': [round(float(non_e), 4), round(float(en_e), 4)],
                 'regions': regions, 'post_point': [1.0, round(float(sc_e(proj(Wpost, u_e).mean())), 3)]},
        'quantiles': quant, 'n': ns, 'targets': targets, 'llm_ref': llm_ref,
        'n_texts': {'pre': int((raw.period == 'pre').sum()), 'post': int((raw.period == 'post').sum()), 'pre_en': int(((raw.period == 'pre') & raw.en).sum())},
    }
    print(sec, 'PCA explained', pca.explained_variance_ratio_.round(3), 'regions', regions)
    print('  PC1 ends', ends('pc1')); print('  PC2 ends', ends('pc2'))
    print('  period dir top', d_period.abs().sort_values(ascending=False).index[:6].tolist(), ' EN dir top', d_en.abs().sort_values(ascending=False).index[:6].tolist())
json.dump(ref, open(out, 'w'), separators=(',', ':'))
import os; print(out, os.path.getsize(out) / 1e6, 'MB')
