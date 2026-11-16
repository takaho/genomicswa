#!/usr/bin/env python3
"""
Compare rewriting engines that apply a field-style SKILL.md (e.g. skills/2403_immunology/SKILL_pre_llm.md).

Design (default for subfield 2403):
  task A  "de-LLM":  2024-25 Introduction/Discussion excerpts  -> rewrite with SKILL_pre_llm.md  (target = pre digest)
  task B  "control": 2019-22 excerpts                            -> rewrite with SKILL_post_llm.md (target = post digest)
Engines:
  rules      deterministic baseline (marker-word substitutions only)
  lmstudio   local LLM via LM Studio (e.g. qwen3.8-27b-mlx; thinking disabled by prefill)
  anthropic  Claude API (ANTHROPIC_API_KEY)
  manual     texts written elsewhere (e.g. by Claude in a chat session) placed in rewrite/<task>/manual/<id>.txt

  python3 rewrite_eval.py sample   --subfield 2403 --n 8
  python3 rewrite_eval.py rewrite  --engine rules
  python3 rewrite_eval.py rewrite  --engine lmstudio --model qwen3.8-27b-mlx
  python3 rewrite_eval.py rewrite  --engine anthropic --model claude-opus-5-5
  python3 rewrite_eval.py evaluate            # needs spaCy (features_wide.py)
  python3 rewrite_eval.py report

Metrics (per item, original vs rewritten):
  band_fit     share of the SKILL's target features inside the target IQR
  band_dist    mean distance outside the band, in IQR units (0 = inside)
  pre_like     mean over features of (|x - post median| - |x - pre median|) / IQR   (>0 = closer to 2019-22)
  markers      LLM-marker words per 10k words
  numbers_kept share of numeric tokens of the original still present
  refs_kept    [REF] markers kept (count ratio);  abbrev_kept  share of abbreviations kept
  len_ratio    rewritten / original word count
"""
import argparse, collections, csv, glob, gzip, json, os, random, re, statistics, sys, time, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skill_corpus as SC

RW = os.path.join(HERE, "rewrite")
TASKS = {"A": {"period": "pre_src_post", "years": (2024, 2025), "skill": "SKILL_pre_llm.md", "target": "pre"},
         "B": {"period": "pre", "years": (2019, 2022), "skill": "SKILL_post_llm.md", "target": "post"}}
EVAL_FEATS = ["sent_len", "word_len", "mattr", "nominal", "passive_pct", "past_pct", "subj_we", "subj_evidence",
              "subj_entity", "subj_expletive", "hedge_modal", "hedge_verb", "hedge_adv", "booster", "booster_verb",
              "importance", "limitation", "future", "conn_causal", "conn_additive", "conn_summary", "aim"]
NUM = re.compile(r"\d+(?:[.,]\d+)?")
ABBR = re.compile(r"\b[A-Za-z0-9\-+αβγκ]*[A-Z][A-Za-z0-9\-+αβγκ]*[A-Z0-9][A-Za-z0-9\-+αβγκ]*\b")
WORD = re.compile(r"[A-Za-z][A-Za-z\-']*")

# ---------------------------------------------------------------- sample
def excerpt(text, max_words=450):
    paras = [p.strip() for p in text.split("\n") if len(p.split()) >= 40]
    out, n = [], 0
    for p in paras:
        if n + len(p.split()) > max_words and out: break
        out.append(p); n += len(p.split())
    t = "\n\n".join(out)
    t = re.sub(r"\s*\[REF\](\s*\[REF\])*", " [REF]", t); t = t.replace("[EQ]", "X")
    return re.sub(r"[ \t]+", " ", t).strip()

def cmd_sample(a):
    sk = glob.glob(os.path.join(HERE, "skills", f"{a.subfield}_*"))
    if not sk: sys.exit("run skill_corpus.py digest first")
    skdir = sk[0]
    used = set()
    for p in ("pre", "post"):
        dj = json.load(open(os.path.join(skdir, f"digest_{p}.json")))
        used |= {e["pmcid"] for ex in dj["exemplars"].values() for e in ex}
    arts = list(SC.iter_articles([os.path.join(HERE, "corpus_wide", f"{a.subfield}.jsonl.gz")]))
    rnd = random.Random(a.seed); items = []
    for task, cfg in TASKS.items():
        lo, hi = cfg["years"]
        pool = [r for r in arts if lo <= int(r["year"]) <= hi and r["pmcid"] not in used]
        rnd.shuffle(pool); k = 0
        for r in pool:
            st = SC.section_texts(r)
            got = []
            for sec in a.sections:
                t = excerpt(st.get(sec, ""), a.max_words)
                if len(t.split()) >= 150: got.append((sec, t))
            if len(got) < len(a.sections): continue
            for sec, t in got:
                items.append({"id": f"{task}_{r['pmcid']}_{sec[:3]}", "task": task, "pmcid": r["pmcid"], "year": r["year"],
                              "section": sec, "journal": r.get("source"), "text": t})
            k += 1
            if k >= a.n: break
    os.makedirs(RW, exist_ok=True)
    json.dump({"subfield": a.subfield, "skill_dir": os.path.relpath(skdir, HERE), "items": items},
              open(os.path.join(RW, "sample.json"), "w"), ensure_ascii=False, indent=1)
    for it in items:
        d = os.path.join(RW, it["task"], "original"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, it["id"] + ".txt"), "w").write(it["text"])
    print(f"{len(items)} excerpts ({collections.Counter(i['task'] for i in items)}) -> {RW}/sample.json")

# ---------------------------------------------------------------- engines
WORDMAP = {"additionally": "also", "notably": "particularly", "crucial": "key", "pivotal": "key", "robust": "strong",
           "insights": "information", "comprehensive": "detailed", "intricate": "complex", "interplay": "interaction",
           "landscape": "profile", "multifaceted": "complex", "realm": "field", "meticulous": "careful",
           "enhance": "increase", "enhances": "increases", "enhanced": "increased", "enhancing": "increasing",
           "elucidate": "define", "elucidates": "defines", "elucidated": "defined", "elucidating": "defining",
           "underscore": "highlight", "underscores": "highlights", "underscored": "highlighted", "underscoring": "highlighting",
           "showcase": "show", "showcases": "shows", "showcased": "showed", "showcasing": "showing",
           "foster": "promote", "fosters": "promotes", "fostered": "promoted", "fostering": "promoting",
           "harness": "use", "harnesses": "uses", "harnessed": "used", "harnessing": "using",
           "delve": "examine", "delves": "examines", "delved": "examined", "delving": "examining"}
RULES = [(r"\bAdditionally,\s*", "In addition, "), (r"\bNotably,\s*", ""), (r"\b(delv\w*) into\b", None),
         (r"\b(" + "|".join(sorted(WORDMAP, key=len, reverse=True)) + r")\b", None)]

def rules_engine(text, task):
    if TASKS[task]["target"] != "pre": return text           # baseline only de-LLMs
    t = text
    def sub(m, rep):
        out = m.expand(rep)
        return out[:1].upper() + out[1:] if m.group(0)[:1].isupper() and out else out
    for pat, rep in RULES:
        if rep is None:
            def f(m):
                w = m.group(1).lower(); out = WORDMAP.get(w, w)
                return out[:1].upper() + out[1:] if m.group(1)[:1].isupper() else out
            t = re.sub(pat, f, t, flags=re.I)
        else:
            t = re.sub(pat, lambda m, rep=rep: sub(m, rep), t, flags=re.I)
    t = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)   # re-capitalise after deletions
    return t

PROMPT = """Rewrite the following {section} excerpt from an immunology research article so that its prose follows the
SKILL below. Change style only. Keep every number, unit, statistic, abbreviation, gene/protein name, figure reference
and every [REF] citation marker exactly; do not add or remove claims, results or references; keep paragraph breaks.
Output ONLY the rewritten excerpt.

=== SKILL ===
{skill}

=== EXCERPT ({section}) ===
{text}"""

def http_json(url, body, headers, timeout=900):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())

def anthropic_engine(prompt, a):
    key = os.environ.get("ANTHROPIC_API_KEY") or json.load(open(os.path.join(HERE, ".api.key"))).get("ANTHROPIC_API_KEY")
    if not key: sys.exit("ANTHROPIC_API_KEY not found")
    for i in range(5):
        try:
            js = http_json("https://api.anthropic.com/v1/messages", {"model": a.model, "max_tokens": 4000, "temperature": 0,
                           "messages": [{"role": "user", "content": prompt}]}, {"x-api-key": key, "anthropic-version": "2023-06-01"})
            return "".join(b.get("text", "") for b in js["content"] if b.get("type") == "text"), js.get("usage", {})
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 529) and i < 4: time.sleep(15 * (i + 1)); continue
            raise

def lmstudio_engine(prompt, a):
    import llm_probe as P
    base = P.detect_base(os.environ.get("LMSTUDIO_BASE", "http://localhost:1235/v1"))
    js = http_json(base + "/chat/completions", {"model": a.model, "temperature": 0, "max_tokens": 2500, "stream": False,
                   "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": "<think>\n\n</think>\n\n"}]}, {})
    t = js["choices"][0]["message"].get("content") or ""
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S), js.get("usage", {})

def cmd_rewrite(a):
    S = json.load(open(os.path.join(RW, "sample.json")))
    skdir = os.path.join(HERE, S["skill_dir"]); log = []
    for it in S["items"]:
        if a.task and it["task"] != a.task: continue
        tag = a.engine if a.engine in ("rules", "manual") else f"{a.engine}_{re.sub(r'[^A-Za-z0-9.-]', '_', a.model)}"
        od = os.path.join(RW, it["task"], tag); os.makedirs(od, exist_ok=True)
        out = os.path.join(od, it["id"] + ".txt")
        if os.path.exists(out) and not a.force: continue
        t0 = time.time()
        if a.engine == "rules":
            txt, usage = rules_engine(it["text"], it["task"]), {}
        else:
            skill = open(os.path.join(skdir, TASKS[it["task"]]["skill"])).read()
            prompt = PROMPT.format(section=it["section"].capitalize(), skill=skill, text=it["text"])
            txt, usage = (anthropic_engine if a.engine == "anthropic" else lmstudio_engine)(prompt, a)
        open(out, "w").write(txt.strip() + "\n")
        log.append({"id": it["id"], "engine": tag, "seconds": round(time.time() - t0, 1), "usage": usage})
        print(f"{tag} {it['id']} {log[-1]['seconds']}s", flush=True)
    if log:
        fn = os.path.join(RW, "rewrite_log.jsonl")
        with open(fn, "a") as f:
            for r in log: f.write(json.dumps(r) + "\n")

# ---------------------------------------------------------------- evaluate
def targets(skdir, period):
    d = json.load(open(os.path.join(skdir, f"digest_{period}.json")))
    return {s: {r["feature"]: r for r in rows} for s, rows in d["features"].items()}

def preserve(orig, new):
    no, nn = collections.Counter(NUM.findall(orig)), collections.Counter(NUM.findall(new))
    num_kept = sum(min(c, nn[k]) for k, c in no.items()) / sum(no.values()) if no else 1.0
    ao, an = set(ABBR.findall(orig)), set(ABBR.findall(new))
    return {"numbers_kept": num_kept, "abbrev_kept": len(ao & an) / max(1, len(ao)),
            "refs_kept": min(new.count("[REF]"), orig.count("[REF]")) / max(1, orig.count("[REF]")) if "[REF]" in orig else 1.0,
            "len_ratio": len(new.split()) / max(1, len(orig.split()))}

def markers(t):
    w = [x.lower() for x in WORD.findall(t)]
    return 1e4 * sum(1 for x in w if x in SC.LLM_MARKERS) / max(1, len(w))

def cmd_evaluate(a):
    import features_wide as FW
    nlp = FW.load_nlp(a.spacy_model)
    S = json.load(open(os.path.join(RW, "sample.json"))); skdir = os.path.join(HERE, S["skill_dir"])
    T = {"pre": targets(skdir, "pre"), "post": targets(skdir, "post")}
    rows = []
    for it in S["items"]:
        task = it["task"]; tgt = TASKS[task]["target"]; sec = it["section"]
        versions = {"original": it["text"]}
        for d in sorted(glob.glob(os.path.join(RW, task, "*"))):
            e = os.path.basename(d); fn = os.path.join(d, it["id"] + ".txt")
            if e != "original" and os.path.exists(fn): versions[e] = open(fn).read()
        for eng, txt in versions.items():
            t, n_ref = FW.prep(txt); f = FW.doc_features(nlp(t), t, n_ref, len(FW.SENT_SPLIT.split(t)))
            fit, dist, prel, n = 0, 0.0, 0.0, 0
            for k in EVAL_FEATS:
                x = f.get(k); g = T[tgt][sec].get(k)
                if x is None or g is None: continue
                iqr = max(g["p75"] - g["p25"], 1e-6); n += 1
                fit += g["p25"] <= x <= g["p75"]
                dist += max(g["p25"] - x, 0, x - g["p75"]) / iqr
                pre, post = T["pre"][sec].get(k), T["post"][sec].get(k)
                if pre and post: prel += (abs(x - post["median"]) - abs(x - pre["median"])) / iqr
            r = {"id": it["id"], "task": task, "section": sec, "engine": eng, "band_fit": fit / max(1, n),
                 "band_dist": dist / max(1, n), "pre_like": prel / max(1, n), "markers": markers(txt),
                 **(preserve(it["text"], txt) if eng != "original" else {"numbers_kept": 1, "abbrev_kept": 1, "refs_kept": 1, "len_ratio": 1}),
                 **{f"f_{k}": f.get(k) for k in EVAL_FEATS}}
            rows.append(r)
        print("evaluated", it["id"], list(versions), flush=True)
    with open(os.path.join(RW, "evaluation.csv"), "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    cmd_report(a)

# ---------------------------------------------------------------- shift
SHIFT_FEATS = ["word_len", "mattr", "nominal", "importance", "booster_verb", "conn_causal", "passive_pct", "subj_evidence"]

def cmd_shift(a):
    """Per-feature movement relative to the original, in pre-period IQR units.
    toward : signed change in the direction pre->post (task B) or post->pre (task A); expected field gap is 0.1-0.4
    d_dist : change in |x - target median| / IQR (negative = closer to target; large toward + positive d_dist = overshoot)"""
    S = json.load(open(os.path.join(RW, "sample.json"))); skdir = os.path.join(HERE, S["skill_dir"])
    T = {"pre": targets(skdir, "pre"), "post": targets(skdir, "post")}
    R = list(csv.DictReader(open(os.path.join(RW, "evaluation.csv"))))
    orig = {r["id"]: r for r in R if r["engine"] == "original"}
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in R:
        if r["engine"] == "original": continue
        o, sec, task = orig[r["id"]], r["section"], r["task"]; tgt = TASKS[task]["target"]
        for k in SHIFT_FEATS:
            pre, post, g = T["pre"][sec].get(k), T["post"][sec].get(k), T[tgt][sec].get(k)
            if not (pre and post and g) or r["f_" + k] in ("", None): continue
            x, x0 = float(r["f_" + k]), float(o["f_" + k]); iqr = max(pre["p75"] - pre["p25"], 1e-6)
            sgn = (1 if post["median"] >= pre["median"] else -1) * (1 if tgt == "post" else -1)
            acc[(task, r["engine"])][k + ":toward"].append((x - x0) / iqr * sgn)
            acc[(task, r["engine"])][k + ":d_dist"].append((abs(x - g["median"]) - abs(x0 - g["median"])) / iqr)
    for m in ("toward", "d_dist"):
        print(f"\n[{m}]  " + " ".join(f"{k[:12]:>12}" for k in SHIFT_FEATS) + "        mean")
        for key in sorted(acc):
            v = [statistics.mean(acc[key][f"{k}:{m}"]) if acc[key][f"{k}:{m}"] else float("nan") for k in SHIFT_FEATS]
            print(f"{key[0]} {key[1][:24]:<24} " + " ".join(f"{x:12.2f}" for x in v) + f"  {statistics.mean([x for x in v if x == x]):10.3f}")

def cmd_report(a):
    R = list(csv.DictReader(open(os.path.join(RW, "evaluation.csv"))))
    M = ["band_fit", "band_dist", "pre_like", "markers", "numbers_kept", "abbrev_kept", "refs_kept", "len_ratio"]
    g = collections.defaultdict(list)
    for r in R: g[(r["task"], r["engine"])].append(r)
    print(f"\n{'task':<5}{'engine':<34}{'n':>4}" + "".join(f"{m:>13}" for m in M))
    for (task, eng), rs in sorted(g.items()):
        print(f"{task:<5}{eng[:33]:<34}{len(rs):>4}" + "".join(f"{statistics.fmean(float(r[m]) for r in rs):>13.3f}" for m in M))
    print("\nA = 2024-25 text -> pre-LLM SKILL (want: band_fit up, band_dist down, pre_like up, markers down)")
    print("B = 2019-22 text -> post-LLM SKILL (want: band_fit up, pre_like down)")
    print("all engines: numbers/abbrev/refs kept ~1.0, len_ratio ~1.0")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sample", "rewrite", "evaluate", "report"])
    ap.add_argument("--subfield", default="2403"); ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--sections", nargs="+", default=["introduction", "discussion"])
    ap.add_argument("--max-words", type=int, default=450); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--engine", choices=["rules", "lmstudio", "anthropic", "manual"]); ap.add_argument("--model", default="")
    ap.add_argument("--task", choices=["A", "B"]); ap.add_argument("--force", action="store_true")
    ap.add_argument("--spacy-model", default="en_core_web_sm")
    a = ap.parse_args()
    {"sample": cmd_sample, "rewrite": cmd_rewrite, "evaluate": cmd_evaluate, "report": cmd_report}[a.cmd](a)

if __name__ == "__main__":
    main()
