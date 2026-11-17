"""Sample introduction/discussion sections from the corpus for the web-app reference (run in the corpus folder)."""
import gzip, json, glob, random, os
random.seed(7); out = gzip.open('webapp/webapp_sample150.jsonl.gz', 'wt'); n = 0
for f in sorted(glob.glob('corpus_wide/*.jsonl.gz')):
    sid = os.path.basename(f).split('.')[0]; pools = {}
    for l in gzip.open(f, 'rt'):
        r = json.loads(l); y = r.get('year') or 0
        per = 'pre' if y <= 2022 else ('post' if y >= 2024 else None)
        if not per: continue
        for s in r['sections']:
            if s['section'] in ('introduction', 'discussion') and 200 <= len(s['text'].split()) <= 3000:
                pools.setdefault((per, s['section']), []).append({'pmcid': r['pmcid'], 'year': y, 'subfield_id': sid, 'section': s['section'], 'text': s['text']})
    for k, v in pools.items():
        for x in random.sample(v, min(150, len(v))): out.write(json.dumps(x) + '\n'); n += 1
out.close(); print(n)
