# Style map web app — build scripts

The app itself is in `docs/` (served by GitHub Pages). It runs entirely in the browser.

- `src/extractor.js` — the feature extractor (wink-nlp + word lists). The same file is used in Node, to build the reference, and in the browser, to analyse user texts.
- `src/browser-entry.js` — bundled with esbuild into `docs/lib/stylemap-nlp.js`:
  `npm install && npx esbuild src/browser-entry.js --bundle --minify --format=iife --outfile=../../docs/lib/stylemap-nlp.js`
- `build_features.js` — `node build_features.js sample.jsonl.gz features.csv` (sample: introduction/discussion sections of the corpus, ~150 per field × period × section; made by `make_sample.py` in the corpus folder; not redistributed).
- `build_reference.py` — PCA of the 2019–22 field medians, the two directions (2019–22 → 2024–25; other → English-speaking authors, within fields), region landmarks, quantiles per field × section × reference group, and the SKILL d3 target values → `docs/data/reference.json`.
- `agreement_js_vs_spacy.csv` — per-feature Pearson r between this extractor and the spaCy features of the research corpus (14,400 sections).

Test locally: `cd docs && python3 -m http.server` and open http://localhost:8000.
