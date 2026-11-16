#!/usr/bin/env python3
"""
Field-style rewriting experiment across all life-science subfields (local LLM).

  python3 fieldstyle.py digest                       # per-field 2024-25 digests  -> fieldstyle/digests/<id>.json
  python3 fieldstyle.py sample                       # excerpts per plan.json     -> fieldstyle/sample.json
  python3 fieldstyle.py rewrite --round 1 --model qwen3.8-27b-mlx [--concurrency 2] [--fields 2403,1311]
  python3 fieldstyle.py pack --round 1               # -> fieldstyle/r1_outputs.jsonl.gz (for evaluation)
  python3 fieldstyle.py autorun --tags r1,r2,d2 --model qwen3.8-27b-mlx
        # unattended: for each tag, waits until fieldstyle/skills_<tag>/READY exists, rewrites, packs,
        # and writes fieldstyle/<tag>_DONE.  (r1 needs no READY flag: it only fills missing items.)
  Tags: r<N> = round N (current field style); d<N> = de-LLM variant (field style of 2019-2022 + removal of AI-polishing style)

Inputs prepared on the analysis side: fieldstyle/plan.json, fieldstyle/skills_r<N>/<subfield>.md
Each target field: 4 introduction + 4 discussion excerpts from stylistically distant fields (rewritten),
plus 2 + 2 native excerpts of the target field (not rewritten; reference for evaluation).
"""
import argparse, glob, gzip, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import skill_corpus as SC
FS = os.path.join(HERE, "fieldstyle")
SECS = ["introduction", "discussion"]
N_REWRITE, N_NATIVE = 4, 2

PROMPT_D = """Rewrite the following {section} excerpt so that its prose follows the writing style of {field} research
articles as they were written in 2019-2022, before AI writing assistants, as described in the SKILL below. The excerpt
comes from another field and was written recently: keep its subject matter, and remove AI-polishing style.
Change style only. Keep every number, unit, statistic, abbreviation, gene/protein name, figure reference and every
[REF] citation marker exactly; do not add or remove claims, results or references; keep paragraph breaks.
Output ONLY the rewritten excerpt.

=== SKILL ===
{skill}

=== EXCERPT ({section}) ===
{text}
"""

PROMPT = """Rewrite the following {section} excerpt so that its prose follows the writing style of {field} research
articles, as described in the SKILL below. The excerpt comes from another field: keep its subject matter.
Change style only. Keep every number, unit, statistic, abbreviation, gene/protein name, figure reference and every
[REF] citation marker exactly; do not add or remove claims, results or references; keep paragraph breaks.
Output ONLY the rewritten excerpt.

=== SKILL ===
{skill}

=== EXCERPT ({section}) ===
{text}
"""

def cmd_digest(a):
    od = os.path.join(FS, "digests"); os.makedirs(od, exist_ok=True)
    ids = a.fields.split(",") if a.fields else sorted(os.path.basename(f).split(".")[0] for f in glob.glob(os.path.join(HERE, "corpus_wide", "*.jsonl.gz")))
    for sid in ids:
        fn = os.path.join(od, f"{sid}.json")
        if os.path.exists(fn): continue
        t0 = time.time()
        d = SC.build_digest(argparse.Namespace(subfield=sid, source="wide"), "post")
        json.dump(d, open(fn, "w"), ensure_ascii=False)
        print(f"digest {sid} {d['subfield']} {time.time() - t0:.0f}s", flush=True)

def cmd_sample(a):
    import rewrite_eval as RE
    plan = json.load(open(os.path.join(FS, "plan.json")))
    fn = os.path.join(FS, "sample.json")
    S = json.load(open(fn)) if os.path.exists(fn) else {"items": []}
    done = {it["target"] for it in S["items"]}
    need = {}                                                     # pmcid -> list of (target, kind, section, srcfield)
    for sid, p in plan.items():
        if sid in done: continue
        for sec in SECS:
            for kind in ("rewrite", "native"):
                for f, pm in p["slots"][sec][kind]: need.setdefault(f, set()).add(pm)
    texts = {}
    for f, pms in sorted(need.items()):
        for r in SC.iter_articles([os.path.join(HERE, "corpus_wide", f"{f}.jsonl.gz")]):
            if r["pmcid"] in pms:
                st = SC.section_texts(r)
                texts[r["pmcid"]] = {s: RE.excerpt(st.get(s, ""), 450) for s in SECS} | {"journal": r.get("source"), "year": r.get("year")}
    for sid, p in plan.items():
        if sid in done: continue
        dg = os.path.join(FS, "digests", f"{sid}.json")
        excl = {e["pmcid"] for ex in json.load(open(dg))["exemplars"].values() for e in ex} if os.path.exists(dg) else set()
        for sec in SECS:
            for kind, n in (("rewrite", N_REWRITE), ("native", N_NATIVE)):
                got, used_f = 0, set()
                for f, pm in p["slots"][sec][kind]:
                    t = texts.get(pm, {}).get(sec, "")
                    if len(t.split()) < 150 or pm in excl or (kind == "rewrite" and f in used_f): continue
                    S["items"].append({"id": f"{sid}_{kind[0]}_{sec[:3]}_{pm}", "target": sid, "target_name": p["name"],
                                       "kind": kind, "source": f, "pmcid": pm, "section": sec, "journal": texts[pm]["journal"],
                                       "year": texts[pm]["year"], "text": t})
                    used_f.add(f); got += 1
                    if got >= n: break
                if got < n: print(f"warning: {sid} {sec} {kind}: only {got}", flush=True)
    json.dump(S, open(fn, "w"), ensure_ascii=False)
    print(f"{len(S['items'])} items, {len({i['target'] for i in S['items']})} targets -> {fn}")

def tag_of(a): return getattr(a, "tag", None) or f"r{a.round}"

def cmd_rewrite(a):
    import rewrite_eval as RE
    S = json.load(open(os.path.join(FS, "sample.json"))); tag = tag_of(a)
    sk = os.path.join(FS, f"skills_{tag}"); od = os.path.join(FS, tag); os.makedirs(od, exist_ok=True)
    tmpl = PROMPT_D if tag.startswith("d") else PROMPT
    fields = set(a.fields.split(",")) if a.fields else None
    todo = [it for it in S["items"] if it["kind"] == "rewrite" and (not fields or it["target"] in fields)
            and not os.path.exists(os.path.join(od, it["id"] + ".txt"))]
    print(f"{tag}: {len(todo)} excerpts to rewrite", flush=True)
    def run(it):
        skill = open(os.path.join(sk, f"{it['target']}.md")).read()
        prompt = tmpl.format(section=it["section"].capitalize(), field=it["target_name"], skill=skill, text=it["text"])
        t0 = time.time()
        for i in range(3):
            try: txt, usage = RE.lmstudio_engine(prompt, a); break
            except Exception as e:
                if i == 2: print("FAILED", it["id"], e, flush=True); return
                time.sleep(5)
        open(os.path.join(od, it["id"] + ".txt"), "w").write(txt.strip() + "\n")
        with open(os.path.join(FS, f"{tag}_log.jsonl"), "a") as f:
            f.write(json.dumps({"id": it["id"], "seconds": round(time.time() - t0, 1), "usage": usage}) + "\n")
        return it["id"]
    t0, k = time.time(), 0
    with ThreadPoolExecutor(a.concurrency) as ex:
        for r in ex.map(run, todo):
            k += 1
            if k % 10 == 0 or k == len(todo):
                el = time.time() - t0; print(f"{k}/{len(todo)}  {el/60:.0f} min, eta {el/k*(len(todo)-k)/60:.0f} min", flush=True)

def cmd_pack(a):
    tag = tag_of(a)
    S = json.load(open(os.path.join(FS, "sample.json"))); od = os.path.join(FS, tag)
    out = os.path.join(FS, f"{tag}_outputs.jsonl.gz"); n = 0
    with gzip.open(out, "wt") as f:
        for it in S["items"]:
            fn = os.path.join(od, it["id"] + ".txt")
            if it["kind"] == "rewrite" and os.path.exists(fn):
                f.write(json.dumps({"id": it["id"], "text": open(fn).read()}, ensure_ascii=False) + "\n"); n += 1
    print(f"{n} rewrites -> {out}")

def cmd_autorun(a):
    for tag in a.tags.split(","):
        if os.path.exists(os.path.join(FS, f"{tag}_DONE")): print(tag, "already done", flush=True); continue
        flag = os.path.join(FS, f"skills_{tag}", "READY")
        if tag == "r1":                       # let a separately running round-1 job finish first
            lg = os.path.join(FS, "r1_log.jsonl")
            while os.path.exists(lg) and time.time() - os.path.getmtime(lg) < 300: time.sleep(60)
        else:
            print(f"{tag}: waiting for {flag}", flush=True)
            while not os.path.exists(flag): time.sleep(60)
        b = argparse.Namespace(**vars(a)); b.tag = tag; b.fields = ""
        cmd_rewrite(b); cmd_pack(b)
        open(os.path.join(FS, f"{tag}_DONE"), "w").write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        print(f"{tag}: done", flush=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["digest", "sample", "rewrite", "pack", "autorun"])
    ap.add_argument("--round", type=int, default=1); ap.add_argument("--model", default="qwen3.8-27b-mlx")
    ap.add_argument("--concurrency", type=int, default=1); ap.add_argument("--fields", default="")
    ap.add_argument("--tag", default=None, help="r<N> or d<N>; overrides --round"); ap.add_argument("--tags", default="r1,r2,d2")
    a = ap.parse_args()
    {"digest": cmd_digest, "sample": cmd_sample, "rewrite": cmd_rewrite, "pack": cmd_pack, "autorun": cmd_autorun}[a.cmd](a)

if __name__ == "__main__": main()
