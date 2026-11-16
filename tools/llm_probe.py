#!/usr/bin/env python3
"""
Probe a local LM Studio model for sentence-level semantic annotation (claim strength etc.):
  1) which reasoning-control method actually works on this LM Studio + model build
  2) speed (sentences/min) and JSON reliability per method
  3) whether reducing reasoning changes the labels (agreement with the full-reasoning run)

  python3 llm_probe.py --list-models
  python3 llm_probe.py --model qwen3.8-27b                    # 40 sentences x all methods
  python3 llm_probe.py --model qwen3.8-27b --methods default effort_low_top no_think_kwarg --n 80 --batch 10
  python3 llm_probe.py --model qwen3.8-27b --methods prefill_nothink --format compact --batch 20 --concurrency 2

Methods tried (each is just a different request shape; ineffective ones simply show long reasoning):
  default             no control (model default, usually full thinking)
  effort_low_top      top-level "reasoning_effort": "low"          (OpenAI-style)
  effort_low_kwarg    chat_template_kwargs {"reasoning_effort": "low"}
  no_think_kwarg      chat_template_kwargs {"enable_thinking": false}
  no_think_prompt     "/no_think" appended to the user message     (Qwen3 legacy soft switch)
  prefill_nothink     trailing assistant message "<think></think>" (skips thinking if the server continues it)
Outputs: llm_probe/<model>_<timestamp>.jsonl (raw) and a summary table on stdout.
Standard library only. Sentences come from corpus_wide/ (or corpus/ if corpus_wide is empty).
"""
import argparse, glob, gzip, json, os, random, re, statistics, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEM = """You annotate sentences from biomedical research articles. For EACH input sentence return one JSON object.
Fields:
- id: copy the input id
- role: one of background | aim | method | result | interpretation | implication | limitation | other
- claim_type: the strongest relation the sentence ASSERTS
    none                 no claim about a relationship (e.g. pure method or background fact without relation)
    descriptive          observes / characterizes something exists or happened ("X was detected in Y")
    associative          correlation / association / difference without causal wording
    causal_conditional   causal relation stated with hedging or condition ("X may promote Y")
    causal_direct        causal relation stated as fact ("X drives Y", "X is required for Y")
- certainty: 1 (highly uncertain / speculative) .. 5 (stated as established fact)
- evidence: own_result | prior_work | speculation | none   (what the sentence's claim rests on)
- hedges: list of hedging cue words/phrases copied from the sentence ([] if none)
- boosters: list of boosting cue words/phrases copied from the sentence ([] if none)
Return ONLY a JSON object: {"items": [ ... one object per sentence, same order ... ]}"""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {"name": "annotations", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "role", "claim_type", "certainty", "evidence", "hedges", "boosters"],
            "properties": {
                "id": {"type": "string"},
                "role": {"type": "string", "enum": ["background", "aim", "method", "result", "interpretation",
                                                    "implication", "limitation", "other"]},
                "claim_type": {"type": "string", "enum": ["none", "descriptive", "associative", "prospect", "caveat",
                                                          "causal_conditional", "causal_direct"]},
                "certainty": {"type": "integer", "minimum": 1, "maximum": 5},
                "evidence": {"type": "string", "enum": ["own_result", "prior_work", "speculation", "none"]},
                "hedges": {"type": "array", "items": {"type": "string"}},
                "boosters": {"type": "array", "items": {"type": "string"}}}}}}}}}

PROMPT_VERSION = "v3.1-context"
SYSTEM_COMPACT = """You annotate sentences from biomedical research articles.
Each input line is: id<TAB>SECTION<TAB>sentence  (SECTION = ABSTRACT, INTRODUCTION, RESULTS or DISCUSSION),
or with context: id<TAB>SECTION para i/n<TAB>PREV: ... || TARGET: sentence || NEXT: ...
Annotate ONLY the TARGET sentence. Use PREV/NEXT and the paragraph position to decide whether the TARGET is
about THIS study (e.g. the closing paragraph of the INTRODUCTION often summarises this study: "Here, we ...")
or about prior work (e.g. "Previous research reported ..." just before it).
Output exactly ONE line per input sentence, in input order, with exactly 7 '|' separated fields and nothing else:
id|role|claim|certainty|evidence|h=hedge cues|b=booster cues

role (function of the sentence in THIS article):
  bg background: prior studies, established or general knowledge, known mechanisms - also inside the
     DISCUSSION, as long as it is not derived from this study's own data
  aim aim, hypothesis or question of THIS study
  me method: procedures, materials, participants and analyses actually performed in THIS study
     (NOT what a technique can do in general, NOT what a figure or table shows)
  re result: data, measurements, comparisons, figure/table contents of THIS study
  in interpretation: explanation of THIS study's results
  im implication: application, recommendation, value or significance of the work
  li limitation, caveat or future work
  ot other (headings, boilerplate, fragments)
claim - decide in this order:
  1. prospect 'pr': future potential, application, recommendation, need for further work, or the value /
     importance of the research ("could be used to", "may serve as a therapeutic option", "X is required to
     improve", "further studies are needed").
  2. caveat 'cv': questions the reliability, validity or generalizability of evidence (bias, confounding,
     small or selected sample, measurement error, over- or underestimation).
  3. otherwise it is a knowledge claim. Does it assert a RELATION between two things?
     NO  -> 'de' for an observation, finding, measurement, state of affairs or state of the literature
            ("X was detected", "little is known about X", "previous studies examined X");
            'no' only for procedures or aims of this study and text without any assertion.
     YES -> any comparison between groups, conditions, time points or with previous results (higher/lower,
            differed, similar to, traced, decreased after, correlated, predicted, not significant) -> 'as',
            unless the wording is causal.
  4. causal wording (cause, drive, induce, promote, regulate, mediate, lead to, result in, explain, be required
     for, increase/reduce the risk, inhibit, activate) -> 'cd' if stated as fact; 'cc' if hedged or conditional
     (may, might, could, likely, suggest, possibly, hypothesize, speculate, postulate).
certainty: 1 speculative ... 3 hedged ... 5 stated as established fact (rate pr/cv sentences the same way)
evidence (what the statement rests on): o = this study's own data; p = previous studies or general knowledge;
  s = speculation, hypothesis or recommendation; n = none (methods, aims)
h= / b= : hedging / boosting cue words copied verbatim from the sentence, separated by ';' (empty after '=')

Examples:
x01	RESULTS	We collected blood samples at baseline and 6 months.
x01|me|no|5|n|h=|b=
x02	INTRODUCTION	Previous studies have shown that obesity is associated with lower adiponectin levels.
x02|bg|as|5|p|h=|b=
x03	DISCUSSION	These findings suggest that IL-17 may promote neutrophil recruitment in the lung.
x03|in|cc|2|o|h=suggest;may|b=
x04	RESULTS	Loss of Tet2 drives clonal expansion of hematopoietic progenitors (Fig. 2).
x04|re|cd|5|o|h=|b=
x05	ABSTRACT	Twenty-three percent of patients reported moderate pain at discharge.
x05|re|de|5|o|h=|b=
x06	DISCUSSION	Clinicians could use this score to identify patients at high risk.
x06|im|pr|3|s|h=could|b=
x07	RESULTS	The difference between groups was not significant (p = 0.21).
x07|re|as|5|o|h=|b=
x08	DISCUSSION	Our small, single-centre sample may limit the generalizability of these findings.
x08|li|cv|3|o|h=may|b=
x09	DISCUSSION	Insulin resistance impairs endothelial nitric oxide production, leading to vascular dysfunction.
x09|bg|cd|5|p|h=|b=
x10	RESULTS	Fig. 4 shows the distribution of lesion volumes across the three cohorts.
x10|re|de|5|o|h=|b=
x11	RESULTS	Expression returned to baseline levels 48 h after withdrawal of the drug.
x11|re|as|5|o|h=|b=
x12	INTRODUCTION	Little is known about the long-term outcomes of this procedure.
x12|bg|de|4|p|h=|b=
x13	DISCUSSION	Further studies are needed to confirm these results in larger populations.
x13|li|pr|4|s|h=|b=
x14	RESULTS	This study clearly demonstrates, for the first time, that FOXP3 is required for this response.
x14|re|cd|5|o|h=|b=clearly;demonstrates;for the first time"""

ROLE = {"bg": "background", "aim": "aim", "me": "method", "re": "result", "in": "interpretation",
        "im": "implication", "li": "limitation", "ot": "other"}
CLAIM = {"no": "none", "de": "descriptive", "as": "associative", "cc": "causal_conditional", "cd": "causal_direct",
         "pr": "prospect", "cv": "caveat"}
SECTION_TAG = {"abstract": "ABSTRACT", "introduction": "INTRODUCTION", "results": "RESULTS", "discussion": "DISCUSSION"}

USE_CONTEXT = True

def _clip(t, n=300):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else ("..." + t[-n:])

def input_line(s):
    """id<TAB>SECTION[ para i/n]<TAB>sentence  - or, when the item has 'context' (prev/next sentences),
    id<TAB>SECTION para i/n<TAB>PREV: ... || TARGET: sentence || NEXT: ...
    Context lets the model tell this study's own work from prior work (e.g. last paragraph of the Introduction)."""
    sec = SECTION_TAG.get(str(s.get("section", "")).lower(), "UNKNOWN")
    text = " ".join(str(s["text"]).split())
    c = s.get("context") if USE_CONTEXT else None
    if c and (c.get("prev") or c.get("next")):
        pos = f' para {c["para"]}/{c["n_paras"]}' if c.get("para") else ""
        nxt = " ".join(str(c.get("next") or "").split())[:200]
        return f'{s["id"]}\t{sec}{pos}\tPREV: {_clip(c.get("prev"))} || TARGET: {text} || NEXT: {nxt}'
    return f'{s["id"]}\t{sec}\t{text}'
EVID = {"o": "own_result", "p": "prior_work", "s": "speculation", "n": "none"}

def parse_compact(text):
    out = {}
    for line in text.splitlines():
        p = [x.strip() for x in line.strip().strip("`").split("|")]
        if len(p) < 5 or not re.match(r"^[A-Za-z]{1,3}\d+$", p[0]): continue
        try: cert = int(re.sub(r"\D", "", p[3]) or 0)
        except ValueError: cert = 0
        ev = p[4]; extra = p[5:]
        if ";" in ev or ev not in EVID:            # model merged evidence and cue fields
            head, _, tail = ev.partition(";"); ev = head; extra = ["h=" + tail] + extra if tail else extra
        h, b = [], []
        for f in extra:
            if f.startswith("b="): b += [x for x in f[2:].split(";") if x.strip()]
            elif f.startswith("h="): h += [x for x in f[2:].split(";") if x.strip()]
            elif not h: h += [x for x in f.split(";") if x.strip()]
            else: b += [x for x in f.split(";") if x.strip()]
        out[p[0]] = {"id": p[0], "role": ROLE.get(p[1], p[1]), "claim_type": CLAIM.get(p[2], p[2]),
                     "certainty": cert, "evidence": EVID.get(ev, ev), "hedges": h, "boosters": b,
                     "valid": p[1] in ROLE and p[2] in CLAIM and ev in EVID and 1 <= cert <= 5}
    return out

METHODS = {
    "default":          {},
    "effort_low_top":   {"body": {"reasoning_effort": "low"}},
    "effort_low_kwarg": {"body": {"chat_template_kwargs": {"reasoning_effort": "low"}}},
    "no_think_kwarg":   {"body": {"chat_template_kwargs": {"enable_thinking": False}}},
    "no_think_prompt":  {"suffix": "\n/no_think"},
    # assistant prefill with an empty think block (works when the server continues a trailing assistant turn)
    "prefill_nothink":  {"prefill": "<think>\n\n</think>\n\n"},
}

# ---------------------------------------------------------------------------- sentences
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

def sample_sentences(n, seed):
    files = sorted(glob.glob(os.path.join(HERE, "corpus_wide", "*.jsonl.gz"))) or \
            [p for p in [os.path.join(HERE, "corpus", "corpus.jsonl.gz")] if os.path.exists(p)]
    if not files: sys.exit("no corpus found (corpus_wide/*.jsonl.gz or corpus/corpus.jsonl.gz)")
    rng = random.Random(seed); pool = []
    for fn in rng.sample(files, min(len(files), 12)):
        recs = []
        try:                                   # files may still be growing during fetch
            with gzip.open(fn, "rt") as f:
                for _, l in zip(range(60), f): recs.append(json.loads(l))
        except (EOFError, OSError, json.JSONDecodeError):
            pass
        if not recs: continue
        for r in rng.sample(recs, min(len(recs), 8)):
            for s in r["sections"]:
                sec = "discussion" if s["section"] == "conclusion" else s["section"]
                if sec not in ("introduction", "results", "discussion"): continue
                for t in SPLIT.split(s["text"].replace("\n", " ")):
                    t = re.sub(r"\s*\[REF\]", "", t)
                    t = re.sub(r"\s*[\(\[]\s*[,;–\-\s]*[\)\]]", "", t).strip()   # empty "( )" left by citations
                    if 8 <= len(t.split()) <= 60 and t[0].isupper():
                        pool.append({"text": t, "section": sec, "pmcid": r.get("pmcid"),
                                     "subfield": r.get("subfield") or r.get("field")})
    rng.shuffle(pool)
    # balance sections
    out, per = [], max(1, n // 3)
    for sec in ("introduction", "results", "discussion"):
        out += [p for p in pool if p["section"] == sec][:per]
    out += [p for p in pool if p not in out][: n - len(out)]
    for i, p in enumerate(out): p["id"] = f"s{i:03d}"
    return out

# ---------------------------------------------------------------------------- LM Studio
def post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def detect_base(base):
    """If the default port is closed, ask `lms server status` for the actual port."""
    import subprocess, socket
    from urllib.parse import urlparse
    u = urlparse(base)
    try:
        socket.create_connection((u.hostname, u.port or 80), timeout=2).close(); return base
    except OSError:
        pass
    print(f"port {u.port} is closed; looking for the LM Studio server...", file=sys.stderr)
    ports = []
    lms_paths = ["lms", os.path.expanduser("~/.lmstudio/bin/lms"), os.path.expanduser("~/.cache/lm-studio/bin/lms")]
    for exe in lms_paths:
        try:
            out = subprocess.run([exe, "server", "status"], capture_output=True, text=True, timeout=20)
            m = re.search(r"port (\d+)", out.stdout + out.stderr)
            if m: ports.append(int(m.group(1))); break
        except Exception as e:
            print(f"  {exe}: {type(e).__name__}", file=sys.stderr)
    ports += [p for p in [1235] + list(range(1234, 1245)) if p not in ports]     # fallback: scan nearby ports
    for p in ports:
        try:
            socket.create_connection((u.hostname, p), timeout=1).close()
        except OSError:
            continue
        nb = f"{u.scheme}://{u.hostname}:{p}{u.path}"
        try:
            with urllib.request.urlopen(nb + "/models", timeout=5) as r:
                json.loads(r.read())
            print(f"LM Studio server found on port {p} -> {nb}", file=sys.stderr)
            return nb
        except Exception:
            continue
    return base

def server_models(base):
    """Return model ids from the LM Studio server, or exit with a hint if it is not reachable."""
    try:
        with urllib.request.urlopen(base + "/models", timeout=10) as r:
            return [m.get("id") for m in json.loads(r.read()).get("data", [])]
    except Exception as e:
        sys.exit(f"Cannot reach LM Studio API at {base} ({type(e).__name__}: {getattr(e, 'reason', e)}).\n"
                 "  `lms ls` works without the API server; the server must be started separately:\n"
                 "    lms server start            # default port 1234\n"
                 "    lms server status           # shows the actual port\n"
                 "  If the port differs:  python3 llm_probe.py --base http://localhost:<port>/v1 ...")

def list_models(base):
    for m in server_models(base): print(m)

THINK = re.compile(r"<think>(.*?)</think>", re.S)

def run_batch(base, model, method, sents, a):
    m = METHODS[method]
    user = "\n".join(input_line(s) if a.format == "compact" else f'{s["id"]}\t{s["text"]}' for s in sents) + m.get("suffix", "")
    system = SYSTEM_COMPACT if a.format == "compact" else SYSTEM
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if m.get("prefill"): msgs.append({"role": "assistant", "content": m["prefill"]})
    max_tok = a.max_tokens
    if a.format == "compact" and m.get("prefill"):      # no thinking: ~15-25 tokens per output line
        max_tok = min(max_tok, 40 * len(sents) + 100)   # cap runaway repetition after the last line
    body = {"model": model, "messages": msgs,
            "temperature": a.temperature, "top_p": 0.8, "max_tokens": max_tok, "stream": False}
    if a.schema and a.format == "json": body["response_format"] = SCHEMA
    body.update(m.get("body", {}))
    t0 = time.time(); err = None; js = {}
    try:
        js = post(base + "/chat/completions", body, a.timeout)
    except urllib.error.HTTPError as e:
        err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    dt = time.time() - t0
    rec = {"method": method, "n": len(sents), "seconds": dt, "error": err}
    if err: return rec, {}
    msg = js["choices"][0]["message"]; content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    mt = THINK.search(content)
    if mt: reasoning += mt.group(1); content = THINK.sub("", content)
    u = js.get("usage", {}) or {}
    rec.update({"completion_tokens": u.get("completion_tokens"), "prompt_tokens": u.get("prompt_tokens"),
                "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "reasoning_chars": len(reasoning), "finish_reason": js["choices"][0].get("finish_reason")})
    if rec.get("completion_tokens") and dt: rec["tok_per_s"] = rec["completion_tokens"] / dt
    labels = {}
    if a.format == "compact":
        labels = parse_compact(content)
        rec["n_labeled"] = sum(1 for s in sents if s["id"] in labels)
        return rec, labels
    try:
        txt = content.strip()
        txt = txt[txt.find("{"): txt.rfind("}") + 1]
        for it in json.loads(txt).get("items", []): labels[str(it.get("id"))] = it
    except Exception as e:
        rec["parse_error"] = f"{type(e).__name__}"
    rec["n_labeled"] = sum(1 for s in sents if s["id"] in labels)
    return rec, labels

# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("LMSTUDIO_BASE", "http://localhost:1235/v1"),
                    help="API base; if the port is closed, the port from `lms server status` is used")
    ap.add_argument("--model", nargs="+", help="one or more model ids (e.g. LM Studio virtual models with different effort)")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--methods", nargs="*", default=list(METHODS))
    ap.add_argument("--n", type=int, default=None, help="sentences (default: 40 sampled, or all in --sentences-from)")
    ap.add_argument("--batch", type=int, default=10, help="sentences per request")
    ap.add_argument("--max-tokens", type=int, default=12000)
    ap.add_argument("--temperature", type=float, default=0.0, help="0 = reproducible labels (run-to-run noise was ~14%% at 0.3)")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--no-schema", dest="schema", action="store_false", help="disable response_format json_schema")
    ap.add_argument("--format", choices=["json", "compact"], default="json",
                    help="compact = one short pipe-separated line per sentence (~1/3 of the output tokens)")
    ap.add_argument("--concurrency", type=int, default=1, help="parallel requests (LM Studio must allow parallel predictions)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sentences-from", help="reuse sentences (and 'gold' rows, if any) from a previous probe/gold jsonl")
    ap.add_argument("--gold", help="take 'gold' rows from this file (e.g. when --sentences-from is a *_ctx file)")
    ap.add_argument("--no-context", action="store_true", help="ignore 'context' fields even if present")
    a = ap.parse_args()
    a.n_given = a.n
    global USE_CONTEXT
    USE_CONTEXT = not a.no_context
    if a.n is None: a.n = 40
    a.base = detect_base(a.base)
    if a.list_models: list_models(a.base); return
    if not a.model: sys.exit("--model is required (see --list-models)")
    avail = server_models(a.base)
    missing = [m for m in a.model if m not in avail]
    if missing:
        print(f"WARNING: not listed by the server: {missing}\n  available: {avail}\n"
              "  (LM Studio may still load them on demand if JIT loading is on; otherwise `lms load <model>`)",
              file=sys.stderr)

    gold = {}
    if a.sentences_from:
        sents = None
        for l in open(a.sentences_from):
            r = json.loads(l)
            if r.get("type") == "sentences" and sents is None:
                sents = r["items"] if a.n_given is None else r["items"][: a.n_given]
            if r.get("type") == "gold": gold[r["id"]] = r
        if a.gold:
            for l in open(a.gold):
                r = json.loads(l)
                if r.get("type") == "gold": gold[r["id"]] = r
    else:
        sents = sample_sentences(a.n, a.seed)
    od = os.path.join(HERE, "llm_probe"); os.makedirs(od, exist_ok=True)
    tag = re.sub(r'[^A-Za-z0-9._-]', '_', a.model[0])
    out = os.path.join(od, f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    print(f"{len(sents)} sentences, batch {a.batch}, models {a.model}, methods {a.methods}\n-> {out}", file=sys.stderr)
    stats, labels = {}, {}
    multi = len(a.model) > 1
    with open(out, "w") as fo:
        fo.write(json.dumps({"type": "sentences", "items": sents}, ensure_ascii=False) + "\n")
        for model in a.model:
          for meth in a.methods:
            method = f"{model}:{meth}" if multi else meth
            stats[method] = []; labels[method] = {}
            from concurrent.futures import ThreadPoolExecutor
            chunks = [sents[i:i + a.batch] for i in range(0, len(sents), a.batch)]
            t_wall = time.time()
            with ThreadPoolExecutor(a.concurrency) as ex:
                for bi, (rec, lab) in enumerate(ex.map(lambda c: run_batch(a.base, model, meth, c, a), chunks)):
                    rec["model"] = model; rec["method"] = method
                    stats[method].append(rec); labels[method].update(lab)
                    fo.write(json.dumps({"type": "batch", **rec, "labels": lab}, ensure_ascii=False) + "\n"); fo.flush()
                    print(f"  {method:<30} batch {bi + 1}: {rec['seconds']:.0f}s "
                          f"tok/s={rec.get('tok_per_s', 0):.1f} reasoning_chars={rec.get('reasoning_chars')} "
                          f"labeled={rec.get('n_labeled')}/{rec['n']}"
                          f"{' ERR ' + rec['error'] if rec['error'] else ''}", file=sys.stderr, flush=True)
            stats[method + "__wall"] = time.time() - t_wall

    ref = next(iter(labels))   # first model x first method is the reference
    print(f"\n{'model:method' if multi else 'method':<32}{'sent/min':>9}{'sec/batch':>10}{'reason_chr':>11}{'compl_tok':>10}"
          f"{'labeled':>9}{'tok/s':>7}{'agree_claim':>12}{'agree_role':>11}{'|Δcert|':>8}  note")
    for method, rs in stats.items():
        if method.endswith("__wall"): continue
        ok = [r for r in rs if not r["error"]]
        secs = stats.get(method + "__wall") or sum(r["seconds"] for r in ok); n_lab = sum(r.get("n_labeled", 0) for r in ok)
        rc = statistics.mean([r.get("reasoning_chars") or 0 for r in ok]) if ok else 0
        ct = statistics.mean([r.get("completion_tokens") or 0 for r in ok]) if ok else 0
        common = [k for k in labels[method] if k in labels[ref]]
        ac = sum(labels[method][k].get("claim_type") == labels[ref][k].get("claim_type") for k in common) / len(common) if common else float("nan")
        ar = sum(labels[method][k].get("role") == labels[ref][k].get("role") for k in common) / len(common) if common else float("nan")
        dc = statistics.mean([abs((labels[method][k].get("certainty") or 0) - (labels[ref][k].get("certainty") or 0)) for k in common]) if common else float("nan")
        note = "errors: " + rs[0]["error"][:40] if not ok and rs else ("truncated" if any(r.get("finish_reason") == "length" for r in ok) else "")
        print(f"{method[:31]:<32}{(n_lab / secs * 60 if secs else 0):>9.1f}{(sum(r["seconds"] for r in ok) / max(1, len(ok))):>10.0f}{rc:>11.0f}{ct:>10.0f}"
              f"{n_lab:>5}/{len(sents):<3}{statistics.mean([r.get('tok_per_s') or 0 for r in ok]) if ok else 0:>7.1f}{ac:>12.2f}{ar:>11.2f}{dc:>8.2f}  {note}")
    if gold:
        print(f"\nvs gold ({len(gold)} sentences){'':<14}{'role':>6}{'claim':>7}{'evid':>6}{'|Δcert|':>8}{'valid':>7}")
        for method, lab in labels.items():
            ks = [k for k in gold if k in lab]
            if not ks: continue
            acc = lambda f: sum(lab[k].get(f) == gold[k][f] for k in ks) / len(ks)
            dc = statistics.mean(abs((lab[k].get("certainty") or 0) - gold[k]["certainty"]) for k in ks)
            va = sum(lab[k].get("valid", True) for k in ks) / len(ks)
            print(f"{method[:39]:<40}{acc('role'):>6.2f}{acc('claim_type'):>7.2f}{acc('evidence'):>6.2f}{dc:>8.2f}{va:>7.2f}")
    print(f"\nagreement is vs '{ref}'. Extrapolation: sentences/min x 60 x 24 = sentences/day.")

if __name__ == "__main__":
    main()
