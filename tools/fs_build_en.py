"""English-speaking-author 2019-22 field profiles (shrunk toward field mean + global EN offset) and a field-adjusted
P(English-speaking last author) classifier for evaluating rewrites.
-> profiles_pre_en.json (same layout as profiles_pre.json, plus n_en, mean_raw), en_classifier.json"""
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import roc_auc_score
K = 50; EN = {'US', 'GB', 'CA', 'AU', 'NZ', 'IE'}
CTRL = json.load(open('classifier.json'))['introduction']['features']; SECS = ['introduction', 'discussion']
EXTRA = ['subj_we', 'hedge_adv', 'booster_verb', 'conn_causal', 'mattr']
FEATS = list(dict.fromkeys(CTRL + EXTRA))
F = pd.read_pickle('../PubMedCorpus/features_wide/F.pkl'); F = F[F.section.isin(SECS) & (F.n_words >= 200) & (F.year <= 2022)].copy()
F['subfield_id'] = F.subfield_id.astype(str)
C = pd.read_csv('../PubMedCorpus/data_wide/authorship_countries.csv', dtype=str)[['pmcid', 'last_country']]
F = F.merge(C, on='pmcid', how='left'); F = F[F.last_country.notna()]; F['en'] = F.last_country.isin(EN).astype(int)
PRE = json.load(open('profiles_pre.json'))['profiles']; out = {}; clf = {}; summ = []
for sec in SECS:
    G = F[F.section == sec].copy(); am = G[FEATS].mean(); asd = G[FEATS].std()
    fm = G.groupby('subfield_id')[FEATS].transform('mean'); D = G[FEATS] - fm          # field-demeaned
    delta = D[G.en == 1].mean()                                                         # global EN offset within field
    for sid, g in G.groupby('subfield_id'):
        e = g[g.en == 1]; n = len(e); m_all = g[FEATS].mean()
        raw = e[FEATS].mean() if n else m_all + delta
        shr = m_all + (n * (raw - m_all) + K * delta) / (n + K)
        out.setdefault(sid, {})[sec] = {k: {'mean': float(shr[k]), 'mean_raw': float(raw[k]) if n else None, 'field_all_mean': float(m_all[k]),
                                            'all_mean': float(am[k]), 'all_sd': float(asd[k]), 'n_en': int(n)} for k in FEATS}
        summ.append(dict(subfield=sid, section=sec, n_en=n, n_all=len(g)))
    X = D.dropna().values; y = G.loc[D.dropna().index, 'en'].values
    sc = StandardScaler().fit(X); lr = LogisticRegression(C=0.5, max_iter=3000)
    p = cross_val_predict(lr, sc.transform(X), y, cv=StratifiedKFold(5, shuffle=True, random_state=0), method='predict_proba')[:, 1]
    lr.fit(sc.transform(X), y)
    clf[sec] = {'features': FEATS, 'mean': sc.mean_.tolist(), 'scale': sc.scale_.tolist(), 'coef': lr.coef_[0].tolist(), 'intercept': float(lr.intercept_[0]),
                'cv_auc': roc_auc_score(y, p), 'base_rate': float(y.mean()), 'demean': 'target field all-author 2019-22 mean (field_all_mean)'}
    print(sec, 'EN AUC %.3f base %.3f' % (clf[sec]['cv_auc'], y.mean()), 'EN offset (SD):', {k: round(delta[k] / asd[k], 2) for k in ['sent_len', 'passive_pct', 'subj_we', 'conn_causal', 'hedge_adv', 'word_len', 'nominal', 'importance', 'past_pct', 'mattr', 'subj_evidence']})
S = pd.DataFrame(summ); print(S.groupby('section').n_en.describe().round(0))
json.dump({'profiles': out, 'shrinkage_k': K, 'en_countries': sorted(EN)}, open('profiles_pre_en.json', 'w')); json.dump(clf, open('en_classifier.json', 'w'))
S.to_csv('profiles_pre_en_counts.csv', index=False)
