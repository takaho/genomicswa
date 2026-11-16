#!/usr/bin/env python3
"""
Rhetorical / stylistic feature space for the wide corpus (one row per article x section).

  python3 -m pip install spacy && python3 -m spacy download en_core_web_sm
  python3 features_wide.py                       # all subfields in corpus_wide/
  python3 features_wide.py --n-process 8 --max-sents 120
  python3 features_wide.py --text my_draft.txt --section discussion   # single text (for testing)

Output: features_wide/<subfield>.csv.gz  (resumable: finished subfields are skipped)

Feature groups (rates are per 1,000 words unless the name says otherwise)
  size      n_words, n_sents, sent_len, word_len, mattr (moving-average type/token ratio, window 100)
  subject   subj_* : share (%) of clause subjects that are we / I / evidence (data, results...) /
            method / human (patients...) / organism (mice...) / pronoun (this, they...) /
            expletive (it, there) / entity (other nouns: cells, genes, proteins...)
            passive_pct : nsubjpass / (nsubj + nsubjpass)
  stance    hedge_modal, hedge_verb, hedge_adv, hedge (sum), booster, booster_verb,
            hedge_we / hedge_evid : hedges per sentence in sentences whose subject is we / evidence
  tense     past_pct : past-tense share of finite verbs
  stats     st_p, st_ci, st_ratio (OR/HR/RR), st_effect, st_n, st_dispersion (SD/SEM/+-),
            st_test (named tests), st_multiple (FDR/Bonferroni), st_bayes, st_percent, st_any
  moves     aim, novelty, importance, limitation, future
  cohesion  conn_contrast, conn_additive, conn_causal, conn_summary
  lexical   nominal (nominalisations), abbrev, numbers, ref (citations per 1,000 words), first_sg
"""
import argparse, csv, glob, gzip, json, os, random, re, sys, zlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SECTIONS = ["abstract", "introduction", "results", "discussion"]

# ---------------------------------------------------------------------------- lexicons
EVIDENCE = {"datum", "data", "result", "finding", "observation", "analysis", "study", "experiment", "evidence",
            "work", "figure", "fig", "table", "investigation", "survey", "trial", "measurement", "assessment",
            "comparison", "examination", "screen", "test", "evaluation", "paper", "report", "article", "review"}
METHOD = {"method", "approach", "model", "algorithm", "tool", "pipeline", "technique", "framework", "assay",
          "strategy", "platform", "protocol", "procedure", "software", "package", "workflow", "simulation", "system"}
HUMAN = {"patient", "participant", "subject", "individual", "people", "person", "woman", "man", "child", "adult",
         "volunteer", "respondent", "case", "control", "cohort", "infant", "adolescent", "student", "nurse",
         "physician", "clinician", "donor", "user", "worker", "mother", "parent", "student"}
ORGANISM = {"mouse", "mice", "rat", "animal", "fly", "worm", "zebrafish", "fish", "plant", "monkey", "macaque",
            "pig", "dog", "cat", "yeast", "strain", "bacterium", "bacteria", "larva", "embryo", "seedling",
            "cattle", "cow", "sheep", "chicken", "bird", "insect", "mosquito", "frog", "primate", "host"}
PRONOUN = {"this", "these", "that", "those", "they", "it", "he", "she", "which", "who", "both", "all", "each",
           "none", "one", "some", "many", "most", "other", "others"}

HEDGE_MODAL = {"may", "might", "could", "would"}
HEDGE_VERB = {"suggest", "indicate", "appear", "seem", "propose", "speculate", "assume", "estimate", "tend",
              "imply", "hypothesize", "hypothesise", "postulate", "believe", "presume", "suspect"}
HEDGE_ADV = {"possibly", "possible", "probably", "probable", "likely", "unlikely", "perhaps", "presumably",
             "potentially", "putative", "putatively", "apparently", "approximately", "roughly", "largely",
             "generally", "relatively", "partially", "partly", "somewhat", "plausible", "plausibly",
             "conceivably", "arguably", "tentatively", "seemingly", "essentially", "mostly", "usually", "often"}
BOOSTER = {"clearly", "clear", "definitely", "certainly", "undoubtedly", "indeed", "conclusively",
           "unequivocally", "strongly", "robustly", "obviously", "evidently", "evident", "undeniably",
           "always", "invariably", "decisively", "firmly", "markedly", "dramatically", "remarkably", "strikingly"}
BOOSTER_VERB = {"demonstrate", "prove", "establish", "reveal", "confirm", "show", "uncover", "unravel", "highlight"}

def rx(words, flags=re.I): return re.compile(r"\b(?:" + "|".join(words) + r")\b", flags)
STATS = {
    "st_p":          re.compile(r"\b[Pp]\s*(?:[<>=≤≥]|values?\b)|\bP\s*-\s*values?\b|\bp-?val", re.U),
    "st_ci":         re.compile(r"\b\d{2}\s?%\s?(?:CI|confidence interval|credible interval)|\bCIs?\b|confidence intervals?", re.I),
    "st_ratio":      re.compile(r"\b(?:a?OR|a?HR|RR|IRR|odds ratios?|hazard ratios?|risk ratios?|relative risks?)\b"),
    "st_effect":     re.compile(r"\beffect sizes?\b|Cohen'?s\s*[dκk]|\bη2|\bR\s?2\b|\bR²|\b[rρ]\s*=\s*-?0?\.\d|\bbeta\b|\bβ\s*=", re.I),
    "st_n":          re.compile(r"\b[nN]\s*=\s*\d"),
    "st_dispersion": re.compile(r"±|\bs\.?e\.?m\.?\b|\bSEM\b|\bSD\b|standard (?:deviation|error)|interquartile|\bIQR\b"),
    "st_test":       rx([r"t-?tests?", "ANOVA", "Wilcoxon", r"Mann[\s\-–]Whitney", r"chi-?squared?", "χ2", "χ²",
                         r"Fisher'?s exact", "Kruskal", r"log-?rank", "Cox", "regression", "mixed[- ]effects?",
                         "generalized linear", "permutation test", r"bootstrap\w*", "Spearman", "Pearson"]),
    "st_multiple":   rx(["FDR", "false discovery", r"q-?values?", "Bonferroni", r"Benjamini", "Holm", "multiple testing",
                         "multiple comparisons?"]),
    "st_bayes":      rx([r"Bayes\w*", "posterior", "credible intervals?", "prior distributions?", "MCMC"]),
    "st_percent":    re.compile(r"\d\s?%"),
}
MOVES = {
    "aim":        rx(["here,? we", "in this (?:study|work|paper|report)", "the (?:aim|goal|purpose|objective) of",
                      r"we (?:aimed|sought|set out) to", r"to (?:investigate|examine|test|address|determine|understand|"
                      r"explore|elucidate|characteri[sz]e|identify|assess|evaluate)"]),
    "novelty":    rx(["novel", "for the first time", "first (?:report|evidence|study|demonstration)", "unprecedented",
                      "previously (?:unknown|unrecognized|uncharacteri[sz]ed|undescribed)", "unexplored",
                      "poorly understood", r"remains? (?:unclear|unknown|elusive|poorly)", "little is known", "gap"]),
    "importance": rx(["critical", "crucial", "key", "essential", "important(?:ly)?", "pivotal", "fundamental",
                      "vital", "significant(?:ly)? (?:contribut|improv|advanc)", "major"]),
    "limitation": rx([r"limitations?", "caveats?", "beyond the scope", "should be interpreted with caution",
                      "cannot (?:rule out|exclude)", "may not (?:be|reflect|generali[sz]e)", "a weakness", "shortcomings?"]),
    "future":     rx([r"future (?:studies|work|research|investigations?)",
                      r"further (?:studies|work|research|investigations?|experiments) (?:are|is|will|would)"]),
}
CONN = {
    "conn_contrast": rx(["however", "although", "whereas", "nevertheless", "nonetheless", "in contrast", "conversely",
                         "despite", "on the other hand", "yet"]),
    "conn_additive": rx(["moreover", "furthermore", "additionally", "in addition", "also", "likewise", "similarly"]),
    "conn_causal":   rx(["therefore", "thus", "hence", "consequently", "accordingly", "as a result", "because"]),
    "conn_summary":  rx(["together", "collectively", "taken together", "overall", "in summary", "in conclusion",
                         "altogether", "in sum"]),
}
NOMINAL = re.compile(r"(?:tion|sion|ment|ness|ity|ance|ence|ism)s?$", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")

# ---------------------------------------------------------------------------- helpers
def prep(text):
    n_ref = text.count("[REF]")
    t = text.replace("[REF]", "").replace("[EQ]", " X ")
    t = re.sub(r"\s+([,.;:)])", r"\1", t); t = re.sub(r"[ \t]+", " ", t)
    return t, n_ref

def cap_sentences(text, max_sents, seed):
    """keep at most max_sents sentences (contiguous block at random offset keeps discourse context)"""
    sents = [s for s in SENT_SPLIT.split(text.replace("\n", " ")) if s.strip()]
    if len(sents) <= max_sents: return " ".join(sents), len(sents)
    start = random.Random(seed).randint(0, len(sents) - max_sents)
    return " ".join(sents[start:start + max_sents]), len(sents)

def mattr(words, w=100):
    if len(words) < w: return len(set(words)) / max(1, len(words))
    vals = [len(set(words[i:i + w])) / w for i in range(0, len(words) - w + 1, 25)]
    return sum(vals) / len(vals)

def subject_class(tok):
    lem = tok.lemma_.lower(); low = tok.text.lower()
    if tok.dep_ == "expl" or (low in ("it", "there") and any(c.dep_ in ("ccomp", "xcomp", "acomp") for c in tok.head.children)):
        return "expletive"
    if low == "we": return "we"
    if low == "i": return "i"
    if lem in EVIDENCE or low in EVIDENCE: return "evidence"
    if lem in METHOD: return "method"
    if lem in HUMAN: return "human"
    if lem in ORGANISM or low in ORGANISM: return "organism"
    if tok.pos_ == "PRON" or low in PRONOUN: return "pronoun"
    return "entity"

SUBJ_CLASSES = ["we", "i", "evidence", "method", "human", "organism", "pronoun", "expletive", "entity"]

def doc_features(doc, raw_text, n_ref, n_sents_total):
    words = [t for t in doc if not (t.is_punct or t.is_space)]
    nw = len(words)
    f = {"n_words": nw, "n_sents": n_sents_total}
    if nw == 0: return f
    per_k = 1000.0 / nw
    alpha = [t.text.lower() for t in doc if t.is_alpha]
    sents = list(doc.sents)
    f["sent_len"] = nw / max(1, len(sents))
    f["word_len"] = sum(len(w) for w in alpha) / max(1, len(alpha))
    f["mattr"] = mattr(alpha)

    # subjects & voice
    subj = Counter(); n_active = n_passive = 0
    hedge_by_subj = {"we": [0, 0], "evidence": [0, 0]}
    hm = hv = ha = bo = bv = 0
    for s in sents:
        s_hedge = 0; s_subj = set()
        for t in s:
            if t.dep_ in ("nsubj", "nsubjpass", "csubj", "expl") and t.head.pos_ in ("VERB", "AUX"):
                c = subject_class(t) if t.dep_ != "csubj" else "entity"
                subj[c] += 1; s_subj.add(c)
                if t.dep_ == "nsubjpass": n_passive += 1
                elif t.dep_ == "nsubj": n_active += 1
            lem = t.lemma_.lower()
            if t.tag_ == "MD" and lem in HEDGE_MODAL: hm += 1; s_hedge += 1
            elif t.pos_ == "VERB" and lem in HEDGE_VERB: hv += 1; s_hedge += 1
            elif t.pos_ in ("ADV", "ADJ") and lem in HEDGE_ADV: ha += 1; s_hedge += 1
            elif t.pos_ in ("ADV", "ADJ") and lem in BOOSTER: bo += 1
            elif t.pos_ == "VERB" and lem in BOOSTER_VERB: bv += 1
        for c in ("we", "evidence"):
            if c in s_subj: hedge_by_subj[c][0] += s_hedge; hedge_by_subj[c][1] += 1
    ns = sum(subj.values())
    for c in SUBJ_CLASSES: f[f"subj_{c}"] = 100.0 * subj[c] / ns if ns else None
    f["n_subjects"] = ns
    f["passive_pct"] = 100.0 * n_passive / (n_active + n_passive) if (n_active + n_passive) else None
    f["hedge_modal"], f["hedge_verb"], f["hedge_adv"] = hm * per_k, hv * per_k, ha * per_k
    f["hedge"] = (hm + hv + ha) * per_k
    f["booster"], f["booster_verb"] = bo * per_k, bv * per_k
    f["hedge_we"] = hedge_by_subj["we"][0] / hedge_by_subj["we"][1] if hedge_by_subj["we"][1] else None
    f["hedge_evid"] = hedge_by_subj["evidence"][0] / hedge_by_subj["evidence"][1] if hedge_by_subj["evidence"][1] else None

    # tense
    past = sum(1 for t in doc if t.tag_ == "VBD")
    pres = sum(1 for t in doc if t.tag_ in ("VBP", "VBZ"))
    f["past_pct"] = 100.0 * past / (past + pres) if (past + pres) else None

    # regex groups on the analysed text
    tx = doc.text
    any_stat = 0
    for k, r in STATS.items():
        n = len(r.findall(tx)); f[k] = n * per_k; any_stat += n
    f["st_any"] = any_stat * per_k
    for k, r in {**MOVES, **CONN}.items(): f[k] = len(r.findall(tx)) * per_k

    # lexical
    f["nominal"] = sum(1 for t in doc if t.pos_ == "NOUN" and len(t.text) > 6 and NOMINAL.search(t.text)) * per_k
    f["abbrev"] = sum(1 for t in words if len(t.text) >= 2 and sum(ch.isupper() for ch in t.text) >= 2
                      and any(ch.isalpha() for ch in t.text)) * per_k
    f["numbers"] = sum(1 for t in doc if t.like_num) * per_k
    f["first_sg"] = sum(1 for t in doc if t.text in ("I", "my", "me")) * per_k
    # citations: n_ref counted on the full section; scale to analysed words
    f["ref"] = 1000.0 * n_ref / max(1, nw * (n_sents_total / max(1, len(sents))))
    return f

# ---------------------------------------------------------------------------- driver
META = ["openalex", "pmcid", "pmid", "year", "source_id", "source", "subfield_id", "subfield", "field", "domain",
        "topic", "topic_score", "license", "is_manuscript"]

def section_texts(rec):
    out = {"abstract": rec.get("abstract") or ""}
    for s in rec["sections"]:
        k = "discussion" if s["section"] == "conclusion" else s["section"]
        if k in SECTIONS and k != "abstract":
            out[k] = (out.get(k, "") + "\n" + s["text"]).strip()
    return out

def iter_items(path, max_sents, min_words):
    with gzip.open(path, "rt") as f:
        for line in f:
            rec = json.loads(line)
            for sec, text in section_texts(rec).items():
                t, n_ref = prep(text)
                if len(t.split()) < min_words: continue
                t2, n_tot = cap_sentences(t, max_sents, zlib.crc32(f"{rec['pmcid']}|{sec}".encode()))
                yield t2, {"rec": {k: rec.get(k) for k in META}, "section": sec, "n_ref": n_ref, "n_tot": n_tot}

def load_nlp(model):
    import spacy
    try:
        return spacy.load(model, disable=["ner"])
    except OSError:
        sys.exit(f"spaCy model {model!r} not installed: python3 -m spacy download {model}")

def run_corpus(a):
    nlp = load_nlp(a.model); nlp.max_length = 2_000_000
    od = os.path.join(a.outdir, "features_wide"); os.makedirs(od, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.outdir, "corpus_wide", "*.jsonl.gz")))
    if a.subfields: files = [p for p in files if os.path.basename(p).split(".")[0] in a.subfields]
    for path in files:
        sid = os.path.basename(path).split(".")[0]
        out = os.path.join(od, f"{sid}.csv.gz")
        if os.path.exists(out) and not a.force: print(f"skip {sid} (done)"); continue
        tmp = out + ".tmp"; n = 0; writer = None
        with gzip.open(tmp, "wt", newline="") as fo:
            items = iter_items(path, a.max_sents, a.min_words)
            for doc, ctx in nlp.pipe(items, as_tuples=True, n_process=a.n_process, batch_size=a.batch_size):
                feats = doc_features(doc, doc.text, ctx["n_ref"], ctx["n_tot"])
                row = {**ctx["rec"], "section": ctx["section"], "spacy_model": a.model, **feats}
                if writer is None:
                    writer = csv.DictWriter(fo, fieldnames=list(row.keys()), extrasaction="ignore"); writer.writeheader()
                writer.writerow(row); n += 1
                if n % 2000 == 0: print(f"  {sid}: {n} sections", flush=True)
        os.replace(tmp, out)
        print(f"{sid}: {n} article-sections -> {out}", flush=True)

def run_text(a):
    nlp = load_nlp(a.model)
    t, n_ref = prep(open(a.text).read())
    t2, n_tot = cap_sentences(t, 10**6, 0)
    f = doc_features(nlp(t2), t2, n_ref, n_tot)
    for k, v in f.items(): print(f"{k:<16}{v if v is None else round(v, 3)}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", default=HERE)
    ap.add_argument("--model", default="en_core_web_sm", help="e.g. en_core_web_sm, en_core_web_md, en_core_sci_sm")
    ap.add_argument("--max-sents", type=int, default=120, help="cap per section (contiguous block)")
    ap.add_argument("--min-words", type=int, default=50)
    ap.add_argument("--n-process", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--subfields", nargs="*", help="only these subfield ids")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--text", help="analyse a single plain-text file instead of the corpus")
    ap.add_argument("--section", default="discussion")
    a = ap.parse_args(); a.outdir = os.path.expanduser(a.outdir)
    run_text(a) if a.text else run_corpus(a)

if __name__ == "__main__":
    main()
