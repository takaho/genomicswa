// node build_features.js sample.jsonl.gz out.csv
const winkNLP = require('wink-nlp'); const model = require('wink-eng-lite-web-model');
const { createExtractor, FEATURES } = require('./src/extractor');
const fs = require('fs'), zlib = require('zlib');
const ex = createExtractor(winkNLP(model));
const lines = zlib.gunzipSync(fs.readFileSync(process.argv[2])).toString().split('\n').filter(Boolean);
const cols = ['pmcid', 'year', 'subfield_id', 'section', 'n_words', ...FEATURES, 'markers_per10k'];
const out = [cols.join(',')]; const t0 = Date.now();
lines.forEach((l, i) => {
  const r = JSON.parse(l); const f = ex.features(r.text);
  out.push(cols.map(c => (r[c] !== undefined ? r[c] : (f[c] === null || f[c] === undefined ? '' : +f[c].toFixed(4)))).join(','));
  if (i % 2000 === 0) console.error(i, ((Date.now() - t0) / 1000).toFixed(0) + 's');
});
fs.writeFileSync(process.argv[3], out.join('\n'));
console.error('done', lines.length, ((Date.now() - t0) / 1000).toFixed(0) + 's');
