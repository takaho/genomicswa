#!/usr/bin/env python3
"""
stylecheck.py — where does my text sit among published papers of my field?

Computes 28 syntactic/rhetorical style features of a text (spaCy en_core_web_sm) and places it within the
distribution of published PMC open-access papers of a chosen field and section:

  pre_en   2019-22, last author in an English-speaking country (US, UK, CA, AU, NZ, IE)   <- default target
  pre      2019-22, all authors (before LLM writing tools)
  post     2024-25, all authors

It reports each feature's percentile in the target distribution, flags features outside the 5-95% range,
and gives three summary scores (introduction/discussion only):
  LLM-style index   mean signed z of 7 features LLM polishing pushes (0 = 2019-22 average; 2024-25 average ≈ 0.3-0.4)
  P(pre)            2019-22 vs 2024-25 period classifier
  P(EN)             field-adjusted English-speaking-author classifier (base rate ≈ 0.3)
plus the five fields whose style the text most resembles, and the count of words typical of AI polishing.

Usage
  python3 stylecheck.py my_discussion.txt --field 1305 --section discussion
  python3 stylecheck.py draft.txt --field "biotech" --section introduction --target pre_en --plot draft.png
  python3 stylecheck.py before.txt --compare after.txt --field 2403 --section discussion --plot compare.png
  python3 stylecheck.py --list-fields

Notes
  - Use a whole section (≥ 300 words) where possible; reference distributions are of whole sections
    (≥ 150 words), so short excerpts look more extreme than they are.
  - Replace citation markers like [12] or (Smith et al., 2020) by [REF] if convenient; numbers in brackets are handled.
  - Requires: spacy + en_core_web_sm, numpy; matplotlib for --plot.
  - Data files are read from ../data/ (style_reference.json, classifier.json, period_classifier.json,
    en_classifier.json, llm_index_ref.json, profiles_pre_en.json).
"""
import argparse, json, os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
DATA = os.environ.get("STYLECHECK_DATA", os.path.join(HERE, "..", "data"))

LABEL = {
    "sent_len": "Sentence length (words)", "word_len": "Word length (characters)", "mattr": "Lexical diversity (MATTR)",
    "subj_we": "'We' as subject (% of subjects)", "subj_evidence": "Data/results/study as subject (%)", "subj_method": "Method/model as subject (%)",
    "subj_human": "Patients/participants as subject (%)", "subj_organism": "Organism as subject (%)", "subj_pronoun": "Pronoun subject (it/they/this) (%)",
    "subj_expletive": "'It is…/There are…' (%)", "subj_entity": "Gene/cell/molecule as subject (%)", "passive_pct": "Passive clauses (%)",
    "hedge_modal": "Modal hedges (may, might) /1k", "hedge_verb": "Hedging verbs (suggest) /1k", "hedge_adv": "Hedging adverbs (likely) /1k",
    "booster": "Boosters (clearly) /1k", "booster_verb": "Booster verbs (demonstrate) /1k", "past_pct": "Past tense (% of finite verbs)",
    "aim": "Aim statements /1k", "novelty": "Novelty/gap statements /1k", "importance": "Importance words (crucial, key) /1k",
    "limitation": "Limitation statements /1k", "future": "Future-work statements /1k", "conn_contrast": "Contrast connectives /1k",
    "conn_additive": "Additive connectives /1k", "conn_causal": "Causal connectives (thus, therefore) /1k", "conn_summary": "Summary connectives /1k",
    "nominal": "Nominalisations /1k",
}
MARKERS = set("""delve delves delving underscore underscores underscoring showcase showcases showcasing pivotal crucial intricate intricacies
notably additionally comprehensive enhance enhances enhancing enhanced robust multifaceted nuanced realm landscape tapestry meticulous meticulously
commendable invaluable seamless seamlessly leverage leverages leveraging foster fosters fostering paramount noteworthy groundbreaking holistic
elucidate elucidates elucidating insights garner garnered bolster bolsters""".split())

def load(name): return json.load(open(os.path.join(DATA, name)))

def features(text, nlp):
    import features_wide as FW
    x, n_ref = FW.prep(text)
    f = FW.doc_features(nlp(x), x, n_ref, len(FW.SENT_SPLIT.split(x)))
    words = re.findall(r"[A-Za-z][A-Za-z\-']*", text)
    f["_markers_per10k"] = 1e4 * sum(w.lower() in MARKERS for w in words) / max(1, len(words))
    f["_n_words"] = len(words)
    return f

def percentile(v, q, Q):
    """piecewise-linear percentile from the 5/25/50/75/95 quantiles"""
    if v is None or np.isnan(v): return np.nan
    xs, ps = list(q), list(Q)
    if v < xs[0]: return 2.5          # below the 5th percentile
    if v > xs[-1]: return 97.5        # above the 95th percentile
    for i in range(len(xs) - 1):
        if xs[i] <= v <= xs[i + 1]:
            return ps[i] + (ps[i + 1] - ps[i]) * ((v - xs[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] > xs[i] else 0.5)
    return np.nan

def scores(f, field, section):
    if section not in ("introduction", "discussion"): return {}
    out = {}
    LR = load("llm_index_ref.json")[section]
    out["llm_index"] = float(np.mean([LR[k]["sign"] * ((f.get(k) or 0) - LR[k]["mean"]) / LR[k]["sd"] for k in LR]))
    PC = load("period_classifier.json")[section]
    x = (np.array([f.get(k) or 0 for k in PC["features"]]) - PC["mean"]) / np.array(PC["scale"])
    out["p_pre"] = float(1 / (1 + np.exp(-(np.dot(PC["coef"], x) + PC["intercept"]))))
    EC = load("en_classifier.json")[section]; T = load("profiles_pre_en.json")["profiles"][field][section]
    x = (np.array([(f.get(k) or 0) - T[k]["field_all_mean"] for k in EC["features"]]) - EC["mean"]) / np.array(EC["scale"])
    out["p_en"] = float(1 / (1 + np.exp(-(np.dot(EC["coef"], x) + EC["intercept"]))))
    C = load("classifier.json")[section]
    x = (np.array([f.get(k) or 0 for k in C["features"]]) - C["mean"]) / np.array(C["scale"])
    z = np.array(C["coef"]) @ x + np.array(C["intercept"]); z = z - z.max(); lp = z - np.log(np.exp(z).sum())
    order = np.argsort(-lp); out["top_fields"] = [(C["classes"][i], float(np.exp(lp[i]))) for i in order[:5]]
    out["field_rank"] = int(1 + sum(lp > lp[C["classes"].index(field)])) if field in C["classes"] else None
    return out

def resolve_field(ref, s):
    names = ref["names"]
    if s in names: return s
    hits = [k for k, v in names.items() if s.lower() in v.lower()]
    if len(hits) == 1: return hits[0]
    sys.exit(f"field '{s}' matches {len(hits)} subfields: " + "; ".join(f"{k} {names[k]}" for k in hits[:15]) + ("" if hits else " (use --list-fields)"))

def report(name, f, ref, field, section, target, sc):
    q = ref["groups"][target][field][section]; Q = ref["quantiles"]; n = ref["n"][target][field][section]
    print(f"\n=== {name}: {f['_n_words']} words · target: {ref['names'][field]} ({field}), {section}, {target} (n = {n} sections)")
    if f["_n_words"] < 300: print("  note: short text — feature values are noisy; percentiles are indicative only")
    rows = []
    for k in ref["features"]:
        v = f.get(k); p = percentile(v, q[k], Q); flag = "  << low" if p < 5 else ("  >> high" if p > 95 else "")
        rows.append((k, v, p)); print(f"  {LABEL[k]:<42s} {v if v is not None else float('nan'):8.2f}   field median {q[k][2]:7.2f}   pct {p:5.0f}{flag}")
    out = [r for r in rows if not np.isnan(r[2]) and (r[2] < 5 or r[2] > 95)]
    print(f"  features outside the field's 5–95% range: {len(out)} of {len(rows)}"
          f"   ·   AI-polish marker words: {f['_markers_per10k']:.1f} per 10k words (2019–22 cross-field ≈ 10)")
    if sc:
        print(f"  LLM-style index {sc['llm_index']:+.2f} (0 = 2019–22 average)   P(pre) {sc['p_pre']:.2f}   P(EN author) {sc['p_en']:.2f} (base ≈ 0.3)")
        print("  most similar fields: " + "; ".join(f"{ref['names'].get(c, c)} {p:.2f}" for c, p in sc["top_fields"]) + f"   · target field rank {sc['field_rank']}/90")
    return rows

CORE = ["sent_len", "word_len", "mattr", "subj_we", "subj_evidence", "subj_entity", "passive_pct", "hedge_adv", "booster_verb", "past_pct", "importance", "conn_causal", "conn_additive", "nominal"]
def plot(path, ref, field, section, target, results, feats=None):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    q = ref["groups"][target][field][section]; feats = feats or ref["features"]; Q = ref["quantiles"]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(feats) + 1.6))
    cols = ["#C8553D", "#1B7F79", "#E0A100"]
    for i, k in enumerate(feats):
        y = len(feats) - i
        ax.plot([5, 95], [y, y], color="#C9D1D6", lw=1.2, zorder=1)
        ax.plot([25, 75], [y, y], color="#8FA3AE", lw=6, solid_capstyle="butt", zorder=2)
        ax.plot([50], [y], marker="|", color="#1F3A5F", ms=12, zorder=3)
        for j, (nm, f, rows) in enumerate(results):
            p = dict((r[0], r[2]) for r in rows)[k]
            ax.plot([p], [y + (j - (len(results) - 1) / 2) * 0.22], "o", color=cols[j % 3], ms=7, zorder=4, label=nm if i == 0 else None)
    ax.set_yticks(range(len(feats), 0, -1)); ax.set_yticklabels([LABEL[k] for k in feats], fontsize=8.5)
    ax.set_xlim(0, 100); ax.set_xlabel(f"percentile among {ref['names'][field]} {section}s ({target}; band = 25–75%, line = 5–95%)", fontsize=9)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.0 + 0.9 / len(feats)), ncol=len(results), frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=200); print("plot ->", path)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?"); ap.add_argument("--compare", help="second text (e.g. after rewriting)")
    ap.add_argument("--field", default="ALL", help="OpenAlex subfield id or part of its name (default: all fields)")
    ap.add_argument("--section", default="discussion", choices=["abstract", "introduction", "results", "discussion"])
    ap.add_argument("--target", default="pre_en", choices=["pre_en", "pre", "post"]); ap.add_argument("--plot")
    ap.add_argument("--core", action="store_true", help="plot 14 core features only"); ap.add_argument("--labels", help="comma-separated legend labels for the texts")
    ap.add_argument("--json", help="write features, percentiles and scores to this file"); ap.add_argument("--list-fields", action="store_true")
    a = ap.parse_args(); ref = load("style_reference.json")
    if a.list_fields:
        for k, v in sorted(ref["names"].items(), key=lambda x: x[1]): print(k, v)
        return
    if not a.text: ap.error("give a text file")
    field = a.field if a.field == "ALL" else resolve_field(ref, a.field)
    import features_wide as FW; nlp = FW.load_nlp("en_core_web_sm")
    results, dump = [], {}
    for nm, fn in [("text", a.text)] + ([("compare", a.compare)] if a.compare else []):
        t = open(fn, encoding="utf-8").read(); f = features(t, nlp)
        sc = scores(f, field, a.section) if field != "ALL" else {}
        rows = report(f"{nm} ({os.path.basename(fn)})", f, ref, field, a.section, a.target, sc)
        results.append((os.path.basename(fn), f, rows)); dump[nm] = {"file": fn, "features": {k: f.get(k) for k in ref["features"]},
                                                                      "percentiles": {r[0]: r[2] for r in rows}, "scores": sc, "markers_per10k": f["_markers_per10k"]}
    if a.labels:
        lab = a.labels.split(","); results = [(lab[i] if i < len(lab) else r[0], r[1], r[2]) for i, r in enumerate(results)]
    if a.plot: plot(a.plot, ref, field, a.section, a.target, results, CORE if a.core else None)
    if a.json: json.dump(dump, open(a.json, "w"), indent=1)

if __name__ == "__main__": main()
