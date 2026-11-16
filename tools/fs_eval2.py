"""Evaluate rewriting tags (r1, r2, d2, ...) on field style, LLM-ness and period.
   python3 fs_eval2.py --dir <folder with <tag>_outputs.jsonl.gz> --tags r1 r2 d2  -> eval2_rows.csv"""
import json, gzip, os, sys, argparse, numpy as np, pandas as pd
sys.argv_saved = sys.argv; sys.argv = [sys.argv[0]]
import fs_eval as E
sys.argv = sys.argv_saved
sys.path.insert(0, '../PubMedCorpus'); import rewrite_eval as RE
PC = json.load(open('period_classifier.json')); LR = json.load(open('llm_index_ref.json'))
def p_pre(sec, f):
    c = PC[sec]; x = (np.array([f[k] or 0 for k in c['features']]) - c['mean']) / np.array(c['scale'])
    return float(1 / (1 + np.exp(-(np.dot(c['coef'], x) + c['intercept']))))
def llm_index(sec, f):
    r = LR[sec]; return float(np.mean([r[k]['sign'] * ((f[k] or 0) - r[k]['mean']) / r[k]['sd'] for k in r]))
def row(it, ver, t):
    f = E.feats(t); sec = it['section']; lp = E.logp(sec, f); sid = it['target']
    others = [k for k in lp if k not in (sid, it['source'])]
    return {'id': it['id'], 'target': sid, 'name': it['target_name'], 'kind': it['kind'], 'source': it['source'], 'section': sec, 'version': ver,
            'logp': lp[sid], 'logp_src': lp.get(it['source'], np.nan), 'logp_other_med': float(np.median([lp[k] for k in others])),
            'rank': 1 + sum(v > lp[sid] for v in lp.values()), 'p_pre': p_pre(sec, f), 'llm_index': llm_index(sec, f),
            'markers': RE.markers(t), 'n_words': f['n_words'], **{'f_' + k: f[k] for k in E.CTRL},
            **(RE.preserve(it['text'], t) if ver not in ('original', 'native') else {})}
if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--dir', required=True); ap.add_argument('--tags', nargs='*', default=[]); a = ap.parse_args()
    rows = []
    for it in E.S: rows.append(row(it, 'native' if it['kind'] == 'native' else 'original', it['text']))
    for tag in a.tags:
        fn = os.path.join(a.dir, f'{tag}_outputs.jsonl.gz')
        if not os.path.exists(fn): print('missing', fn); continue
        out = {}
        for l in gzip.open(fn, 'rt'): j = json.loads(l); out[j['id']] = j['text']
        for it in E.S:
            if it['id'] in out: rows.append(row(it, tag, out[it['id']]))
        print(tag, len(out))
    json.dump(E.cache, open(E.CACHE, 'w'))
    R = pd.DataFrame(rows); R.to_csv('eval2_rows.csv', index=False)
    print(R.groupby('version')[['logp', 'rank', 'p_pre', 'llm_index', 'markers']].median().round(3))
