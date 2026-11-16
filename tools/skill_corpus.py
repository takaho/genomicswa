#!/usr/bin/env python3
"""
Build the evidence package ("digest") from which a field-specific writing SKILL.md is generated,
separately for the pre-LLM period (2019-2022) and the post-LLM period (2024-2025).

Subcommands (run from this directory; standard library only except `features`, which needs spaCy):
  python3 skill_corpus.py list                                   # subfield ids and names in corpus_wide/
  python3 skill_corpus.py collect  --subfield 2403 --per-year 300   # OPTIONAL: larger dedicated corpus
  python3 skill_corpus.py features --subfield 2403                  # OPTIONAL: features for that corpus
  python3 skill_corpus.py digest   --subfield 2403 [--source wide|skill]
      -> skills/<sid>_<slug>/digest_pre.md / digest_post.md (+ .json)

The digest contains, per period:
  1. corpus summary (articles, journals, author countries)
  2. section proportions (share of body words)
  3. feature profile per section: field median and IQR, all-field median, standardised difference (d)
  4. post only: change from the field's own pre-LLM profile
  5. distinctive sentence openers and 3/4-word lexical bundles (log-odds vs all fields, same period)
  6. LLM-marker vocabulary rate (per 10k words) vs all fields
  7. exemplar paragraphs from typical articles (CC BY / CC0 only, with PMCID for attribution)
`--source wide` uses corpus_wide/ + features_wide/ (default); `--source skill` uses corpus_skill/<sid>/.
"""
import argparse, collections, csv, glob, gzip, json, math, os, random, re, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
PERIODS = {"pre": (2019, 2022), "post": (2024, 2025)}
SECTIONS = ["abstract", "introduction", "results", "discussion"]
FEATURES = [  # (column, label) - interpretable subset of features_wide.py
    ("sent_len", "words per sentence"), ("word_len", "characters per word"), ("mattr", "lexical diversity (MATTR)"),
    ("nominal", "nominalisations /1k words"), ("passive_pct", "passive clauses (% of subjects)"),
    ("past_pct", "past tense (% of finite verbs)"),
    ("subj_we", "subject = we (%)"), ("subj_evidence", "subject = data/results/study (%)"),
    ("subj_method", "subject = method/model/tool (%)"), ("subj_human", "subject = patients/participants (%)"),
    ("subj_organism", "subject = mice/animals/plants (%)"), ("subj_entity", "subject = cells/genes/other entities (%)"),
    ("subj_pronoun", "subject = this/these/they (%)"), ("subj_expletive", "subject = it/there (expletive) (%)"),
    ("hedge_modal", "modal hedges (may/might/could) /1k"), ("hedge_verb", "hedging verbs (suggest/indicate) /1k"),
    ("hedge_adv", "hedging adverbs (likely/possibly) /1k"), ("booster", "booster adverbs (clearly/strongly) /1k"),
    ("booster_verb", "booster verbs (demonstrate/reveal/highlight) /1k"),
    ("st_any", "statistical expressions /1k"), ("st_p", "p-values /1k"), ("st_ci", "confidence intervals /1k"),
    ("numbers", "numbers /1k"), ("abbrev", "abbreviations /1k"), ("ref", "citations /1k"),
    ("aim", "aim statements /1k"), ("novelty", "novelty claims /1k"), ("importance", "importance words /1k"),
    ("limitation", "limitation statements /1k"), ("future", "future-work statements /1k"),
    ("conn_contrast", "contrast connectives /1k"), ("conn_additive", "additive connectives /1k"),
    ("conn_causal", "causal connectives (thus/therefore) /1k"), ("conn_summary", "summary connectives /1k"),
]
LLM_MARKERS = """delve delves delving underscore underscores underscoring showcase showcases showcasing
intricate intricacies pivotal crucial notably comprehensive enhancing enhance enhances meticulous meticulously
realm landscape tapestry multifaceted nuanced commendable noteworthy invaluable unwavering seamless seamlessly
foster fosters fostering bolster bolsters garner garnered elucidate elucidates elucidating harness harnessing
navigate navigating paramount additionally insights robust holistic interplay groundbreaking transformative""".split()
OK_LICENSES = {"CC BY", "CC0", "CC BY-SA"}
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
WORD = re.compile(r"[a-z][a-z\-']*")
FUNC = set("""a an the of in on at to for from by with as and or but nor not no that this these those it its we our
is are was were be been being has have had do does did can could may might will would should which who whom whose
than then there their they them here also both each between within into through after before during while when where
however although whereas thus therefore hence because since if whether such more most less least further""".split())

def slug(s): return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]

def sources(a):
    if a.source == "skill":
        base = os.path.join(HERE, "corpus_skill", a.subfield)
        return (sorted(glob.glob(os.path.join(base, "corpus_wide", "*.jsonl.gz"))),
                sorted(glob.glob(os.path.join(base, "features_wide", "*.csv.gz"))))
    return ([os.path.join(HERE, "corpus_wide", f"{a.subfield}.jsonl.gz")],
            [os.path.join(HERE, "features_wide", f"{a.subfield}.csv.gz")])

def period_of(y):
    y = int(y)
    for p, (lo, hi) in PERIODS.items():
        if lo <= y <= hi: return p
    return None

def clean(t):
    t = t.replace("[REF]", " ").replace("[EQ]", " X ")
    return re.sub(r"\s+", " ", t).strip()

def section_texts(r):
    out = {"abstract": r.get("abstract") or ""}
    for s in r["sections"]:
        k = "discussion" if s["section"] == "conclusion" else s["section"]
        if k in SECTIONS and k != "abstract":
            t = s["text"]; ttl = (s.get("title") or "").strip()
            if ttl and t.startswith(ttl): t = t[len(ttl):]
            out[k] = (out.get(k, "") + "\n" + t).strip()
    return out

def iter_articles(paths):
    for fn in paths:
        try:
            with gzip.open(fn, "rt") as f:
                for line in f: yield json.loads(line)
        except (EOFError, OSError): pass

# ------------------------------------------------------------------ features
def load_feature_rows(paths):
    rows = []
    for fn in paths:
        with gzip.open(fn, "rt") as f:
            for r in csv.DictReader(f):
                if int(float(r["n_words"] or 0)) >= 100: rows.append(r)
    return rows

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def profile(rows, period, section):
    out = {}
    sel = [r for r in rows if r["section"] == section and period_of(r["year"]) == period]
    for col, _ in FEATURES:
        v = [num(r.get(col)) for r in sel]; v = [x for x in v if x is not None]
        if len(v) < 20: continue
        q = statistics.quantiles(v, n=4)
        out[col] = {"n": len(v), "mean": statistics.fmean(v), "sd": statistics.pstdev(v), "p25": q[0], "median": q[1], "p75": q[2]}
    return out

def baseline_profile(period):
    """all-field profile (cached)"""
    fn = os.path.join(HERE, "data_wide", f"skill_baseline_features_{period}.json")
    if os.path.exists(fn): return json.load(open(fn))
    rows = load_feature_rows(sorted(glob.glob(os.path.join(HERE, "features_wide", "*.csv.gz"))))
    prof = {s: profile(rows, period, s) for s in SECTIONS}
    os.makedirs(os.path.dirname(fn), exist_ok=True); json.dump(prof, open(fn, "w")); return prof

# ------------------------------------------------------------------ n-grams
def ngram_counts(articles, period, max_articles=None, seed=0):
    rnd = random.Random(seed); arts = [r for r in articles if period_of(r.get("year", 0)) == period]
    if max_articles and len(arts) > max_articles: arts = rnd.sample(arts, max_articles)
    opener = {s: collections.Counter() for s in SECTIONS}; bundle = {s: collections.Counter() for s in SECTIONS}
    markers = collections.Counter(); nwords = 0
    for r in arts:
        for sec, t in section_texts(r).items():
            t = clean(t)
            for sent in SPLIT.split(t):
                w = WORD.findall(sent.lower())
                if len(w) < 4: continue
                opener[sec][" ".join(w[:2])] += 1
                for n in (3, 4):
                    for i in range(len(w) - n + 1):
                        g = w[i:i + n]
                        if sum(x in FUNC for x in g) >= n - 2 and sum(x in FUNC for x in g) < n:
                            bundle[sec][" ".join(g)] += 1
                nwords += len(w); markers.update(x for x in w if x in LLM_MARKERS)
    return {"n_articles": len(arts), "opener": opener, "bundle": bundle, "markers": markers, "nwords": nwords}

def baseline_ngrams(period, per_file=15):
    fn = os.path.join(HERE, "data_wide", f"skill_baseline_ngrams_{period}.json")
    if os.path.exists(fn):
        d = json.load(open(fn))
        return {"n_articles": d["n_articles"], "nwords": d["nwords"], "markers": collections.Counter(d["markers"]),
                "opener": {s: collections.Counter(v) for s, v in d["opener"].items()},
                "bundle": {s: collections.Counter(v) for s, v in d["bundle"].items()}}
    arts = []; yr = re.compile(r'"year": (\d{4})')
    for f in sorted(glob.glob(os.path.join(HERE, "corpus_wide", "*.jsonl.gz"))):
        lines = []
        try:
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    m = yr.search(line)
                    if m and period_of(m.group(1)) == period: lines.append(line)
        except (EOFError, OSError): pass
        random.Random(1).shuffle(lines); arts += [json.loads(l) for l in lines[:per_file]]
    d = ngram_counts(arts, period)
    keep = lambda c, k: dict(c.most_common(k))
    json.dump({"n_articles": d["n_articles"], "nwords": d["nwords"], "markers": dict(d["markers"]),
               "opener": {s: keep(c, 20000) for s, c in d["opener"].items()},
               "bundle": {s: keep(c, 60000) for s, c in d["bundle"].items()}}, open(fn, "w"))
    return d

def log_odds(fc, bc, top, min_count):
    """Monroe et al. log-odds with informative Dirichlet prior; returns over-represented items in field"""
    nf, nb = sum(fc.values()), sum(bc.values()); a0 = 0.01
    keys = set(fc) | set(bc); A = len(keys) * a0
    out = []
    for k in keys:
        yf, yb = fc.get(k, 0), bc.get(k, 0)
        if yf < min_count: continue
        d = math.log((yf + a0) / (nf + A - yf - a0)) - math.log((yb + a0) / (nb + A - yb - a0))
        z = d / math.sqrt(1 / (yf + a0) + 1 / (yb + a0))
        out.append((k, z, yf / nf * 1e4 if nf else 0, yb / nb * 1e4 if nb else 0))
    return sorted(out, key=lambda x: -x[1])[:top]

# ------------------------------------------------------------------ exemplars
KEY = ["passive_pct", "subj_we", "subj_evidence", "hedge_modal", "hedge_verb", "booster_verb", "st_any", "nominal", "importance", "conn_causal"]

def exemplars(articles, feat_rows, period, prof, k=3, seed=0):
    by = collections.defaultdict(dict)
    for r in feat_rows:
        if period_of(r["year"]) == period: by[r["pmcid"]][r["section"]] = r
    out = {}
    arts = {r["pmcid"]: r for r in articles if period_of(r.get("year", 0)) == period and (r.get("license") or "") in OK_LICENSES}
    for sec in ["introduction", "results", "discussion"]:
        p = prof.get(sec, {}); scored = []
        for pm, secs in by.items():
            if pm not in arts or sec not in secs: continue
            d = 0; ok = 0
            for c in KEY:
                v = num(secs[sec].get(c))
                if v is None or c not in p or p[c]["sd"] == 0: continue
                d += ((v - p[c]["median"]) / p[c]["sd"]) ** 2; ok += 1
            if ok >= 6: scored.append((d / ok, pm))
        scored.sort()
        picks = []
        for _, pm in scored[:60]:
            t = section_texts(arts[pm]).get(sec, "")
            paras = [clean(x) for x in t.split("\n") if 90 <= len(x.split()) <= 220]
            if not paras: continue
            para = paras[min(1, len(paras) - 1)] if sec == "introduction" else paras[0]
            a = arts[pm]
            picks.append({"pmcid": pm, "year": a.get("year"), "journal": a.get("source"), "license": a.get("license"), "text": para})
            if len(picks) >= k: break
        out[sec] = picks
    return out

# ------------------------------------------------------------------ digest
def section_shares(articles, period):
    v = collections.defaultdict(list)
    for r in articles:
        if period_of(r.get("year", 0)) != period: continue
        w = {"introduction": 0, "methods": 0, "results": 0, "discussion": 0}
        for s in r["sections"]:
            k = "discussion" if s["section"] == "conclusion" else s["section"]
            if k in w: w[k] += len(s["text"].split())
        tot = sum(w.values())
        if tot < 1500 or not w["methods"] or not w["discussion"]: continue
        for k, x in w.items(): v[k].append(x / tot)
        v["body_words"].append(tot)
    return {k: (statistics.median(x) if k == "body_words" else statistics.fmean(x)) for k, x in v.items() if x}

def countries(pmcids):
    fn = os.path.join(HERE, "data_wide", "authorship_countries.csv")
    if not os.path.exists(fn): return {}
    c = collections.Counter()
    for r in csv.DictReader(open(fn)):
        if r["pmcid"] in pmcids: c[r["first_country"] or "unknown"] += 1
    n = sum(c.values()) or 1
    return {k: round(v / n, 3) for k, v in c.most_common(10)}

def build_digest(a, period):
    cpaths, fpaths = sources(a)
    arts = list(iter_articles(cpaths))
    if not arts: sys.exit(f"no articles for {a.subfield} ({cpaths})")
    name, field = arts[0].get("subfield"), arts[0].get("field")
    frows = load_feature_rows(fpaths)
    prof = {s: profile(frows, period, s) for s in SECTIONS}
    base = baseline_profile(period)
    pre = {s: profile(frows, "pre", s) for s in SECTIONS} if period == "post" else None
    ng = ngram_counts(arts, period); bng = baseline_ngrams(period)
    per_arts = [r for r in arts if period_of(r.get("year", 0)) == period]
    jr = collections.Counter(r.get("source") for r in per_arts)
    d = {"subfield_id": a.subfield, "subfield": name, "field": field, "period": period, "years": PERIODS[period],
         "n_articles": len(per_arts), "top_journals": jr.most_common(10),
         "first_author_countries": countries({r["pmcid"] for r in per_arts}),
         "section_shares": section_shares(arts, period), "features": {}, "openers": {}, "bundles": {},
         "llm_markers": {}, "exemplars": exemplars(arts, frows, period, prof)}
    for s in SECTIONS:
        d["features"][s] = []
        for col, lab in FEATURES:
            if col not in prof[s] or col not in base.get(s, {}): continue
            f, b = prof[s][col], base[s][col]
            row = {"feature": col, "label": lab, "p25": f["p25"], "median": f["median"], "p75": f["p75"],
                   "all_median": b["median"], "d_vs_all": (f["mean"] - b["mean"]) / b["sd"] if b["sd"] else 0}
            if pre and col in pre[s] and pre[s][col]["sd"]:
                row["change_from_pre"] = (f["mean"] - pre[s][col]["mean"]) / pre[s][col]["sd"]
            d["features"][s].append(row)
        d["openers"][s] = log_odds(ng["opener"][s], bng["opener"][s], 25, 8)
        d["bundles"][s] = log_odds(ng["bundle"][s], bng["bundle"][s], 30, 10)
    nf, nb = ng["nwords"] or 1, bng["nwords"] or 1
    d["llm_markers"] = {"field_per10k": sum(ng["markers"].values()) / nf * 1e4, "all_per10k": sum(bng["markers"].values()) / nb * 1e4,
                        "top": [(w, c / nf * 1e4) for w, c in ng["markers"].most_common(15)]}
    return d

def to_md(d):
    L = [f"# Digest: {d['subfield']} ({d['field']}), {d['period']}-LLM period {d['years'][0]}–{d['years'][1]}", "",
         f"- articles: {d['n_articles']}",
         "- top journals: " + "; ".join(f"{j} ({n})" for j, n in d["top_journals"]),
         "- first-author countries: " + ", ".join(f"{k} {v:.0%}" for k, v in d["first_author_countries"].items()),
         "- section shares of body words: " + ", ".join(f"{k} {v:.0%}" if k != "body_words" else f"median body {v:.0f} words"
                                                        for k, v in d["section_shares"].items()), ""]
    for s in SECTIONS:
        L += [f"## {s.capitalize()}", "", "| feature | field p25 | median | p75 | all-field median | d vs all |" +
              (" change from pre |" if d["period"] == "post" else ""),
              "|---|---|---|---|---|---|" + ("---|" if d["period"] == "post" else "")]
        for r in d["features"][s]:
            L.append(f"| {r['label']} | {r['p25']:.2f} | {r['median']:.2f} | {r['p75']:.2f} | {r['all_median']:.2f} | {r['d_vs_all']:+.2f} |" +
                     (f" {r.get('change_from_pre', 0):+.2f} |" if d["period"] == "post" else ""))
        L += ["", "Distinctive sentence openers (z, field /10k sentences vs all): " +
              "; ".join(f"'{k}' ({z:.1f}, {f:.0f} vs {b:.0f})" for k, z, f, b in d["openers"][s][:15]),
              "", "Distinctive lexical bundles: " + "; ".join(f"'{k}' ({z:.1f})" for k, z, f, b in d["bundles"][s][:25]), ""]
    m = d["llm_markers"]
    L += ["## LLM-marker vocabulary", f"field {m['field_per10k']:.1f} vs all fields {m['all_per10k']:.1f} per 10k words; top: " +
          ", ".join(f"{w} {r:.1f}" for w, r in m["top"]), "", "## Exemplar paragraphs (typical articles; CC BY/CC0)"]
    for s, ex in d["exemplars"].items():
        for e in ex:
            L += ["", f"**{s}** — {e['pmcid']} ({e['journal']}, {e['year']}, {e['license']})", "", "> " + e["text"]]
    return "\n".join(L) + "\n"

# ------------------------------------------------------------------ collect / features
def cmd_collect(a):
    import collect_wide as W
    od = os.path.join(HERE, "corpus_skill", a.subfield); os.makedirs(os.path.join(od, "data_wide"), exist_ok=True)
    open(os.path.join(od, "data_wide", "subfields_selected.txt"), "w").write(a.subfield + "\n")
    for fn in ("filters.json",):
        src = os.path.join(HERE, "data_wide", fn)
        if os.path.exists(src) and not os.path.exists(os.path.join(od, "data_wide", fn)):
            open(os.path.join(od, "data_wide", fn), "w").write(open(src).read())
    try:
        W.step_sample(od, a.per_year, 2.5, 20261115)
    except W.BudgetExhausted as e:
        W.budget_stop(e)
    W.step_fetch(od, a.per_year, 0.1, 12, False)
    W.step_summary(od)

def cmd_features(a):
    import subprocess
    od = os.path.join(HERE, "corpus_skill", a.subfield)
    subprocess.run([sys.executable, os.path.join(HERE, "features_wide.py"), "--outdir", od, "--n-process", str(a.n_process)], check=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "collect", "features", "digest"])
    ap.add_argument("--subfield"); ap.add_argument("--per-year", type=int, default=300)
    ap.add_argument("--source", choices=["wide", "skill"], default="wide")
    ap.add_argument("--n-process", type=int, default=8)
    a = ap.parse_args()
    if a.cmd == "list":
        for fn in sorted(glob.glob(os.path.join(HERE, "corpus_wide", "*.jsonl.gz"))):
            with gzip.open(fn, "rt") as f: r = json.loads(f.readline())
            print(os.path.basename(fn).split(".")[0], r.get("subfield"), "|", r.get("field"))
        return
    if not a.subfield: sys.exit("--subfield is required")
    if a.cmd == "collect": cmd_collect(a); return
    if a.cmd == "features": cmd_features(a); return
    outs = []
    for period in ("pre", "post"):
        d = build_digest(a, period)
        od = os.path.join(HERE, "skills", f"{a.subfield}_{slug(d['subfield'])}"); os.makedirs(od, exist_ok=True)
        json.dump(d, open(os.path.join(od, f"digest_{period}.json"), "w"), ensure_ascii=False, indent=1)
        open(os.path.join(od, f"digest_{period}.md"), "w").write(to_md(d)); outs.append(od)
        print(f"{period}: {d['n_articles']} articles -> {od}/digest_{period}.md", flush=True)

if __name__ == "__main__":
    main()
