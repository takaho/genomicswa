#!/usr/bin/env python3
"""
Structural de-LLM round (s3): edit, don't regenerate.

Idea: a full LLM rewrite re-imposes the model's own syntax (short sentences, active voice, nominal style),
whatever the instructions say. Here the LLM may change ONLY the sentences that a measured plan selects,
and ONLY by the operation assigned to each; every other sentence is copied from the base text by the
program. Several candidates are sampled (temperature > 0) and the one closest to the target field's
2019-22 profile is kept, after content checks.

Arms (base text the edits start from):
  s4   base = original + rule-based marker replacement; target = 2019-22 profile of ENGLISH-SPEAKING last authors
       (profiles_pre_en.json); no CAUSAL; MERGE may not add contrast/cause words; SUBJECT_WE turns "This study ..." into "We ...";
       every edit is reverted if it adds a contrast/causal connective, changes hedging or negation
  s3a  base = d2 output (LLM-regenerated, lexical de-LLM already done)
  s3b  base = original excerpt + rule-based replacement of LLM marker words (no LLM regeneration)

  python3 fieldstyle_struct.py run --arm s3b --model qwen3.8-27b-mlx [--n 2] [--temperature 0.7] [--per-field 4] [--fields 2403]
  python3 fieldstyle_struct.py run --arm s3a ...
  python3 fieldstyle_struct.py pack --arm s3b        # -> fieldstyle/s3b_outputs.jsonl.gz
  python3 fieldstyle_struct.py demo --arm s3b --fields 2403   # show plan + prompt for one excerpt, no LLM call
  python3 fieldstyle_struct.py report --arm s3b [--fields ...] [--show 3]   # operation success, gap closure, examples
Outputs: fieldstyle/<arm>/<id>.txt (selected), fieldstyle/<arm>_candidates.jsonl (all candidates, plans, scores)
"""
import argparse, json, os, re, sys, time, math, gzip, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
FS = os.path.join(HERE, "fieldstyle")
import features_wide as FW
import rewrite_eval as RE

STRUCT = ["sent_len", "passive_pct", "nominal", "word_len", "subj_evidence", "conn_causal", "past_pct", "importance", "mattr"]
STRUCT_S4 = ["sent_len", "passive_pct", "nominal", "word_len", "subj_we", "past_pct", "importance"]          # selection (s4)
HELDOUT_S4 = ["conn_causal", "mattr", "hedge_adv", "booster_verb", "subj_evidence"]                         # recorded, never used for selection
def struct_of(arm): return STRUCT_S4 if arm == "s4" else STRUCT
# ---------------------------------------------------------------- lexical de-LLM (rule-based, for arm s3b)
EXTRA = {"crucial": "important", "pivotal": "key", "remarkable": "notable", "unprecedented": "new", "profound": "strong",
         "multifaceted": "complex", "intricate": "complex", "meticulous": "careful", "meticulously": "carefully",
         "comprehensive": "detailed", "robust": "strong", "robustly": "strongly", "seamless": "smooth", "seamlessly": "smoothly",
         "paramount": "essential", "invaluable": "useful", "noteworthy": "notable", "groundbreaking": "new", "transformative": "major",
         "holistic": "overall", "nuanced": "detailed", "bolster": "support", "bolsters": "supports", "garner": "gain", "garnered": "gained",
         "navigate": "address", "navigating": "addressing", "tapestry": "range", "commendable": "good", "unwavering": "constant",
         "escalating": "increasing", "insights": "information"}
def lexical_dellm(text):
    MAP = {**RE.WORDMAP, **EXTRA}
    t = re.sub(r"\bAdditionally,\s*", "In addition, ", text)
    t = re.sub(r"\bNotably,\s*([a-z])", lambda m: m.group(1).upper(), t)
    t = re.sub(r"\bNotably,\s*", "", t)
    t = re.sub(r"\b(delv\w*) into\b", lambda m: MAP.get(m.group(1).lower(), "examine"), t, flags=re.I)
    def f(m):
        w = m.group(0); r = MAP[w.lower()]
        return r[:1].upper() + r[1:] if w[:1].isupper() else r
    t = re.sub(r"\b(" + "|".join(sorted(MAP, key=len, reverse=True)) + r")\b", f, t, flags=re.I)
    t = re.sub(r"\b(an?) (important|key|notable|new|strong|complex|careful|detailed|useful|overall|major|essential|good)\b",
               lambda m: ("An" if m.group(1)[0] == "A" else "an") + " " + m.group(2) if m.group(2)[0] in "aeiou" else
               ("A" if m.group(1)[0] == "A" else "a") + " " + m.group(2), t)
    return t

# ---------------------------------------------------------------- sentence analysis
LATINATE = {"utilize": "use", "utilise": "use", "utilized": "used", "utilization": "use", "demonstrate": "show", "demonstrated": "showed",
            "demonstrates": "shows", "facilitate": "help", "facilitates": "helps", "subsequently": "then", "approximately": "about",
            "numerous": "many", "commence": "begin", "initiate": "start", "prior to": "before", "in order to": "to", "a number of": "several",
            "exhibit": "show", "exhibits": "shows", "exhibited": "showed", "constitute": "form", "constitutes": "forms", "additionally": "also",
            "methodology": "method", "functionality": "function", "underlying": "basic", "elucidate": "define", "modulate": "change"}
REPORT_STUDY = re.compile(r"(?:\b(?:studies|study|research|reports?|authors|work|evidence|analyses|trials?|investigators|data)\b|\bet al\.)[^.;]{0,40}?\b(?:show|demonstrat|report|indicat|suggest|reveal|find)\w*", re.I)
REPORT_PRESENT = re.compile(r"\b(show|shows|demonstrate|demonstrates|report|reports|indicate|indicates|suggest|suggests|reveal|reveals|find|finds)\b")
STUDY_SUBJ = re.compile(r"(?:Here,?\s+|In (?:this|the present|the current) (?:study|work),?\s+)?(?:[Tt]his|[Tt]he present|[Tt]he current|[Oo]ur) (?:study|work|research|investigation|analysis|paper|report|article)\s+(?!is\b|was\b|has been\b|had\b|of\b|in\b|on\b|to\b)[a-z]+")
SPLIT = re.compile(r"(?<!\b[A-Z]\.)(?<!\bspp\.)(?<!\bsp\.)(?<!\bal\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bFig\.)(?<!\bvs\.)(?<!\bca\.)(?<=[.!?])\s+(?=[A-Z(\[])")

def split_excerpt(text):
    """-> list of (paragraph_index, sentence)"""
    out = []
    for pi, para in enumerate([p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]):
        para = re.sub(r"\s+", " ", para.strip())
        sents = [s for s in SPLIT.split(para) if s.strip()]
        # re-attach orphan citation fragments like "[REF] ." to the previous sentence
        for s in sents:
            if out and out[-1][0] == pi and (len(s.split()) < 3 or s.startswith("[REF]")): out[-1] = (pi, out[-1][1] + " " + s)
            else: out.append((pi, s))
    return out

def join_excerpt(sents):
    paras = {}
    for pi, s in sents:
        if s.strip(): paras.setdefault(pi, []).append(s.strip())
    return "\n\n".join(" ".join(v) for k, v in sorted(paras.items()))

def analyse(nlp, sents):
    A = []
    for i, (pi, s) in enumerate(sents):
        t, _ = FW.prep(s); doc = nlp(t)
        words = [w for w in doc if not (w.is_punct or w.is_space)]
        subj = [w for w in doc if w.dep_ in ("nsubj", "nsubjpass")]
        A.append(dict(i=i, para=pi, n=len(words), passive=any(w.dep_ == "nsubjpass" for w in doc),
                      active_trans=any(w.dep_ == "nsubj" and any(c.dep_ == "dobj" for c in w.head.children) for w in doc),
                      we=any(w.dep_ == "nsubj" and w.lower_ == "we" for w in doc),
                      evidence=any(FW.subject_class(w) == "evidence" for w in subj),
                      nominal=sum(1 for w in words if FW.NOMINAL.search(w.text) and len(w.text) > 6),
                      wlen=sum(len(w.text) for w in words) / max(1, len(words)),
                      latinate=sum(1 for k in LATINATE if re.search(r"\b" + k + r"\b", s, re.I)),
                      ref="[REF]" in s, report_present=bool(REPORT_PRESENT.search(s)),
                      importance=len(FW.MOVES["importance"].findall(s)), causal=bool(FW.CONN["conn_causal"].search(s)),
                      starts_this=bool(re.match(r"(This|These|Such)\b", s)),
                      report_study=bool(REPORT_STUDY.search(s)),
                      starts_anaphor=bool(re.match(r"(It|They|This|These|Its|Their|Such|Both|The latter)\b", s)),
                      starts_conn=bool(re.match(r"(However|Although|Though|In contrast|Conversely|Nevertheless|Nonetheless|Moreover|Furthermore|In addition|Additionally|Similarly|Likewise|Also|Therefore|Thus|Hence|Consequently|As a result|Accordingly|Finally|First|Second|Third|Next|Then|Overall|Together|Taken together|In summary|In conclusion)\b", s)),
                      ccomp=any(w.dep_ == "ccomp" for w in doc),
                      study_subj=bool(STUDY_SUBJ.match(s)) and "[REF]" not in s,
                      we_dobj=any(w.dep_ == "nsubj" and w.lower_ == "we" and w.head.dep_ == "ROOT" and w.head.pos_ == "VERB"
                                  and any(c.dep_ == "dobj" for c in w.head.children) for w in doc)))
    return A

def excerpt_features(nlp, text):
    t, n_ref = FW.prep(text); return FW.doc_features(nlp(t), t, n_ref, len(FW.SENT_SPLIT.split(t)))

# ---------------------------------------------------------------- plan
OPS = {
 "MERGE": "Join these two sentences into one sentence with a subordinate clause or coordination (which, whereas, because, although, and, but); use a semicolon only if no relation fits. Keep every piece of content of both sentences.",
 "PASSIVE": "Put the main clause in the passive voice by making its direct object the subject and dropping 'we' (e.g. 'We measured X in all samples' -> 'X was measured in all samples'). Keep the tense and the meaning; do not write 'by us'; do not use 'It was shown … that' or a clause as the subject.",
 "VERBALIZE": "Turn one or two abstract nouns (-tion, -ment, -ity, -ance) into verbs (e.g. 'the activation of X by Y' -> 'Y activates X').",
 "PLAIN": "Replace long or Latinate words with shorter common ones (e.g. utilize -> use, demonstrate -> show, facilitate -> help, subsequently -> then, exhibit -> have). Do not change technical terms, and do not introduce 'key', 'crucial', 'essential' or 'critical'.",
 "SUBJECT": "Do not use 'these findings', 'these results', 'this study' or 'the data' as the grammatical subject; make 'we' (for this study's own work) or the gene, cell, molecule or variable the subject.",
 "CAUSAL": "Only if this sentence states a consequence of the previous sentence, add 'therefore' or 'thus' (or join with 'because'). If the relation is not cause and effect, output the sentence unchanged.",
 "PAST": "This sentence reports earlier work: put the reporting verb in the past or present perfect tense (e.g. 'studies show' -> 'studies showed' / 'have shown').",
 "MERGE_S4": "Join these two sentences into one sentence using 'and', a relative clause ('which ...') or a semicolon. Do NOT add any word expressing contrast or cause (whereas, while, although, but, however, because, since, as, thus, therefore, hence, so, consequently) unless that word is already in one of the two sentences. Keep every piece of content of both sentences.",
 "SUBJECT_WE": "The subject of this sentence is this paper's own study ('This study', 'The present study', 'Our work' ...). Make 'we' the subject and keep the verb, its tense and its strength (e.g. 'This study investigated X' -> 'We investigated X'; 'The present study demonstrates that X' -> 'Here we demonstrate that X'; 'This study aimed to test X' -> 'We aimed to test X', keeping 'aimed to'). Do not add or remove hedging.",
 "TONE": "Remove or tone down importance words (crucial, critical, key, essential, pivotal, fundamental, vital, major) unless they carry information.",
}
def plan(A, feats, prof, max_ops=7):
    """choose sentence-level operations in the de-LLM direction, sized by the gap to the target field's 2019-22 mean"""
    gap = {k: (prof[k]["mean"] - (feats.get(k) or 0)) / prof[k]["all_sd"] for k in STRUCT}
    want = []          # (priority, op, sentences)
    used = set()
    def k_of(g, per=0.3, cap=3): return min(cap, max(1, math.ceil(abs(g) / per)))
    if gap["sent_len"] > 0.2:
        pairs = [(A[i]["n"] + A[i + 1]["n"], i) for i in range(len(A) - 1)
                 if A[i]["para"] == A[i + 1]["para"] and A[i]["n"] < prof["sent_len"]["mean"] and A[i + 1]["n"] < prof["sent_len"]["mean"]]
        for _, i in sorted(pairs)[:k_of(gap["sent_len"])]: want.append((gap["sent_len"], "MERGE", [i, i + 1]))
    if gap["passive_pct"] > 0.2:
        # only "We <verb> <object>" main clauses: converting other active clauses distorted meaning in the pilot
        c = [a["i"] for a in A if a["we_dobj"] and not a["passive"] and not a["ccomp"]]
        for i in c[:k_of(gap["passive_pct"])]: want.append((gap["passive_pct"], "PASSIVE", [i]))
    if gap["nominal"] < -0.2:
        for a in sorted(A, key=lambda a: -a["nominal"])[:k_of(gap["nominal"])]:
            if a["nominal"] >= 3: want.append((-gap["nominal"], "VERBALIZE", [a["i"]]))
    if gap["word_len"] < -0.2:
        for a in sorted(A, key=lambda a: -(a["latinate"] * 2 + a["wlen"]))[:k_of(gap["word_len"], cap=2)]: want.append((-gap["word_len"], "PLAIN", [a["i"]]))
    if gap["subj_evidence"] < -0.2:
        for a in [a for a in A if a["evidence"] and not a["ref"]][:k_of(gap["subj_evidence"], cap=2)]: want.append((-gap["subj_evidence"], "SUBJECT", [a["i"]]))
    if gap["conn_causal"] > 0.2:
        for a in [a for a in A if a["i"] > 0 and not a["causal"] and not a["starts_conn"] and (a["starts_this"] or a["report_present"])][:k_of(gap["conn_causal"], cap=2)]:
            want.append((gap["conn_causal"], "CAUSAL", [a["i"]]))
    if gap["past_pct"] > 0.2:
        for a in [a for a in A if a["ref"] and a["report_present"]][:k_of(gap["past_pct"], cap=2)]: want.append((gap["past_pct"], "PAST", [a["i"]]))
    if gap["importance"] < -0.2:
        for a in [a for a in A if a["importance"] > 0][:k_of(gap["importance"], cap=2)]: want.append((-gap["importance"], "TONE", [a["i"]]))
    ops = []
    for pr, op, ss in sorted(want, key=lambda x: -x[0]):
        if any(s in used for s in ss): continue
        ops.append((op, ss)); used |= set(ss)
        if len(ops) >= max_ops: break
    return ops, gap

def plan_s4(A, feats, prof, max_ops=7):
    """s4: target = English-speaking authors' 2019-22 profile; no CAUSAL; SUBJECT_WE for 'This study ...' subjects"""
    gap = {k: (prof[k]["mean"] - (feats.get(k) or 0)) / prof[k]["all_sd"] for k in STRUCT_S4}
    want, used = [], set()
    def k_of(g, per=0.3, cap=3): return min(cap, max(1, math.ceil(abs(g) / per)))
    if gap["sent_len"] > 0.2:
        pairs = [(A[i]["n"] + A[i + 1]["n"], i) for i in range(len(A) - 1)
                 if A[i]["para"] == A[i + 1]["para"] and A[i]["n"] < prof["sent_len"]["mean"] and A[i + 1]["n"] < prof["sent_len"]["mean"]
                 and A[i]["n"] >= 5 and A[i + 1]["n"] >= 5 and A[i + 1]["starts_anaphor"] and not A[i + 1]["starts_conn"]]   # only "X ... . It/They/This ..." pairs
        for _, i in sorted(pairs)[:k_of(gap["sent_len"])]: want.append((gap["sent_len"], "MERGE_S4", [i, i + 1]))
    if gap["subj_we"] > 0.2:
        for a in [a for a in A if a["study_subj"]][:k_of(gap["subj_we"], cap=2)]: want.append((gap["subj_we"] + 1, "SUBJECT_WE", [a["i"]]))
    if gap["passive_pct"] > 0.2:
        c = [a["i"] for a in A if a["we_dobj"] and not a["passive"] and not a["ccomp"]]
        for i in c[:k_of(gap["passive_pct"])]: want.append((gap["passive_pct"], "PASSIVE", [i]))
    # VERBALIZE dropped in s4: in the pilot it rewrote whole clauses (method -> finding, lost content, broke grammar) for ~0 gain
    if gap["word_len"] < -0.2:
        for a in sorted(A, key=lambda a: -(a["latinate"] * 2 + a["wlen"]))[:k_of(gap["word_len"], cap=2)]: want.append((-gap["word_len"], "PLAIN", [a["i"]]))
    if gap["past_pct"] > 0.2:
        for a in [a for a in A if a["ref"] and a["report_study"]][:k_of(gap["past_pct"], cap=2)]: want.append((gap["past_pct"], "PAST", [a["i"]]))
    if gap["importance"] < -0.2:
        for a in [a for a in A if a["importance"] > 0][:k_of(gap["importance"], cap=2)]: want.append((-gap["importance"], "TONE", [a["i"]]))
    ops = []
    for pr, op, ss in sorted(want, key=lambda x: -x[0]):
        if any(s in used for s in ss): continue
        ops.append((op, ss)); used |= set(ss)
        if len(ops) >= max_ops: break
    return ops, gap

PROMPT = """You will edit {article} {section} excerpt from a research article so that its sentence structure resembles {field} articles written {who}in 2019-2022.
The sentences are numbered. Apply ONLY the listed operations to ONLY the listed sentences. Do not change any other sentence.
Keep every number, unit, statistic, abbreviation, gene/protein name, figure reference and every [REF] marker exactly; do not add or remove claims.
Never make "we" the subject of a sentence that reports earlier work (sentences with [REF]).

Operations:
{ops}

Sentences:
{sents}

Output every listed sentence number on its own line as "S<number>: <edited sentence>", nothing else.
For MERGE, write the merged sentence after the first number and leave the second number empty (e.g. "S4:").
"""

def build_prompt(it, sents, ops, field, who=""):
    targets = sorted({i for _, ss in ops for i in ss})
    ol = []
    for op, ss in ops:
        ol.append(f"- {op} on " + "+".join(f"S{i+1}" for i in ss) + f": {OPS[op]}")
    show = sorted(set(targets) | {i - 1 for i in targets if i > 0} | {i + 1 for i in targets if i + 1 < len(sents)})
    sl = "\n".join(f"S{i+1}: {sents[i][1]}" + ("" if i in targets else "   [context only - do not output]") for i in show)
    return PROMPT.format(article="an" if it["section"][0] in "aeiou" else "a", section=it["section"], field=field, who=who, ops="\n".join(ol), sents=sl), targets

STOP = set("the a an of in on at to for from by with as and or but not no that this these those it its is are was were be been being has have had which who whom whose than then there their they them we our also both each between into through after before during while when where however although whereas thus therefore hence because since if whether such more most less very".split())
def content(t): return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", t) if w.lower() not in STOP]
def coverage(before, after):
    b = content(before); a = set(content(after))
    if not b: return 1.0
    stem = lambda w: w[:5]
    sa = {stem(w) for w in a}
    return sum(1 for w in b if w in a or stem(w) in sa) / len(b)
MIN_COV_S4 = {"VERBALIZE": 0.8, "PLAIN": 0.75, "SUBJECT_WE": 0.75}
STUDY_WORDS = re.compile(r"\b(this|the|present|current|our|study|work|research|investigation|analysis|paper|report|article|here)\b", re.I)
MIN_COV = {"MERGE_S4": 0.9, "SUBJECT_WE": 0.85, "MERGE": 0.9, "PASSIVE": 0.85, "CAUSAL": 0.9, "PAST": 0.9, "SUBJECT": 0.75, "PLAIN": 0.7, "VERBALIZE": 0.7, "TONE": 0.8}

LOGIC = re.compile(r"\b(whereas|while|although|though|but|however|nevertheless|nonetheless|yet|conversely|in contrast|unlike|because|since|thus|therefore|hence|so|consequently|as a result|accordingly|due to|owing to|leading to|resulting in|thereby)\b", re.I)
HEDGE = re.compile(r"\b(may|might|could|can|possibly|possible|likely|unlikely|probably|perhaps|suggest\w*|appear\w*|seem\w*|potential\w*|indicat\w*|presumabl\w*|implicat\w*|putative\w*|assum\w*)\b", re.I)
MAX_CHANGED = {"PAST": 2, "PLAIN": 5, "TONE": 4}      # word-level edits allowed (lexical ops must stay lexical)
def changed_words(before, after):
    import difflib
    b, a = before.split(), after.split()
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, b, a).get_opcodes() if tag != "equal")
NEG = re.compile(r"\b(not|no|neither|nor|without|never|cannot|n't|lack\w*|absence|fail\w*)\b", re.I)
def guard_s4(op, before, after):
    """-> reason string if the edit changes logic, hedging or negation; '' if acceptable"""
    nb = {m.lower() for m in LOGIC.findall(before)}; na = {m.lower() for m in LOGIC.findall(after)}
    if na - nb: return "new connective: " + ",".join(sorted(na - nb))
    if len(HEDGE.findall(after)) != len(HEDGE.findall(before)): return "hedging changed"
    if len(NEG.findall(after)) != len(NEG.findall(before)): return "negation changed"
    if op in MAX_CHANGED and changed_words(before, after) > MAX_CHANGED[op]: return "too many words changed"
    if op == "SUBJECT_WE" and not re.search(r"\b[Ww]e\b", after): return "no 'we' subject"
    return ""

def apply_output(sents, ops, targets, out, edits=None, strict=False):
    got = {}
    for line in out.splitlines():
        m = re.match(r"\s*S(\d+)\s*[:.]\s*(.*)$", line.strip())
        if m: got[int(m.group(1)) - 1] = m.group(2).strip()
    new = list(sents); reverted = []
    for op, ss in ops:
        if not all(i in got for i in ss[:1]): continue
        before = " ".join(sents[i][1] for i in ss)
        after = " ".join(x for x in [got.get(i, "") for i in ss] if x)
        lead = re.match(r"(However|Although|Though|In contrast|Conversely|Nevertheless|Nonetheless|Moreover|Furthermore|In addition|Similarly|Likewise|Finally|Overall|Taken together|In summary|In conclusion)\b", before)
        cov = coverage(STUDY_WORDS.sub(" ", before) if op == "SUBJECT_WE" else before, after)
        if not after or cov < (MIN_COV_S4.get(op, MIN_COV[op]) if strict else MIN_COV[op]) or after.count("[REF]") != before.count("[REF]") \
           or (lead and not after.startswith(lead.group(1))) or (strict and guard_s4(op, before, after)):
            reverted.append(ss[0]); continue
        if op in ("MERGE", "MERGE_S4"):
            new[ss[0]] = (sents[ss[0]][0], got[ss[0]]); new[ss[1]] = (sents[ss[1]][0], got.get(ss[1], ""))
        else:
            new[ss[0]] = (sents[ss[0]][0], got[ss[0]])
    if edits is not None:
        for op, ss in ops:
            edits[str(ss[0])] = {"op": op, "before": " ".join(sents[i][1] for i in ss), "after": " ".join(new[i][1] for i in ss if new[i][1]),
                                 "guard": guard_s4(op, " ".join(sents[i][1] for i in ss), " ".join(x for x in [got.get(i, "") for i in ss] if x)) if strict and ss[0] in got else "",
                                 "merged": op in ("MERGE", "MERGE_S4") and not new[ss[-1]][1].strip() and bool(new[ss[0]][1].strip()), "parsed": ss[0] in got,
                                 "reverted": ss[0] in reverted, "raw": " ".join(got.get(i, "") for i in ss)}
    return join_excerpt(new)

WE = re.compile(r"\b(we|our|us)\b", re.I)
def valid(base, cand, orig):
    p = RE.preserve(orig, cand)
    if p["refs_kept"] < 1 or p["numbers_kept"] < 0.98 or p["abbrev_kept"] < 0.95 or not (0.8 <= p["len_ratio"] <= 1.2): return False, p
    cw = lambda t: sum(bool(WE.search(s)) for s in SPLIT.split(t.replace("\n", " ")) if "[REF]" in s)
    if cw(cand) > cw(base): return False, p
    return True, p

def distance(f, prof, keys=None):
    keys = keys or STRUCT
    return sum(abs((f.get(k) or 0) - prof[k]["mean"]) / prof[k]["all_sd"] for k in keys) / len(keys)

# ---------------------------------------------------------------- run
def lm_call(prompt, a):
    import llm_probe as P, urllib.request
    base = P.detect_base(os.environ.get("LMSTUDIO_BASE", "http://localhost:1235/v1"))
    body = {"model": a.model, "temperature": a.temperature, "top_p": a.top_p, "max_tokens": 1500, "stream": False,
            "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": "<think>\n\n</think>\n\n"}]}
    js = RE.http_json(base + "/chat/completions", body, {})
    return re.sub(r"<think>.*?</think>", "", js["choices"][0]["message"].get("content") or "", flags=re.S)

def items(a):
    S = json.load(open(os.path.join(FS, "sample.json")))["items"]; fields = set(a.fields.split(",")) if a.fields else None
    out, cnt = [], {}
    for it in S:
        if it["kind"] != "rewrite" or (fields and it["target"] not in fields): continue
        k = (it["target"], it["section"]); cnt[k] = cnt.get(k, 0) + 1
        if cnt[k] <= a.per_field // 2: out.append(it)
    return out

def base_text(it, arm):
    if arm == "s3a": return open(os.path.join(FS, "d2", it["id"] + ".txt")).read().strip()
    # s3b and s4: original + rule-based marker replacement (no LLM regeneration, so d2's content errors are not inherited)
    return lexical_dellm(it["text"])

def cmd_run(a, demo=False):
    nlp = FW.load_nlp("en_core_web_sm")
    PRE = json.load(open(os.path.join(FS, "analysis", "profiles_pre_en.json" if a.arm == "s4" else "profiles_pre.json")))["profiles"]
    KEYS = struct_of(a.arm); s4 = a.arm == "s4"
    od = os.path.join(FS, a.arm); os.makedirs(od, exist_ok=True); log = os.path.join(FS, f"{a.arm}_candidates.jsonl")
    if a.force and not demo and os.path.exists(log): os.rename(log, log.replace(".jsonl", f"_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"))
    todo = [it for it in items(a) if demo or a.force or not os.path.exists(os.path.join(od, it["id"] + ".txt"))]
    print(f"{a.arm}: {len(todo)} excerpts, n={a.n}, T={a.temperature}", flush=True); t0 = time.time()
    for k, it in enumerate(todo):
        prof = PRE[it["target"]][it["section"]]; base = base_text(it, a.arm)
        sents = split_excerpt(base); A = analyse(nlp, sents); fb = excerpt_features(nlp, base)
        ops, gap = (plan_s4 if s4 else plan)(A, fb, prof)
        rec = {"id": it["id"], "arm": a.arm, "target": it["target"], "section": it["section"], "base_feats": {k_: fb.get(k_) for k_ in KEYS + (HELDOUT_S4 if s4 else [])}, "gap": {k_: round(v, 3) for k_, v in gap.items()}, "ops": ops,
               "base_dist": distance(fb, prof, KEYS), "candidates": []}
        best, best_d = base, rec["base_dist"]
        if ops:
            prompt, targets = build_prompt(it, sents, ops, it["target_name"], "by native English-speaking authors " if s4 else "")
            if demo:
                print("\n=== base ===\n" + base + "\n\n=== plan ===", ops, "\n\n=== prompt ===\n" + prompt); return
            for c in range(a.n):
                try: out = lm_call(prompt, a)
                except Exception as e: rec["candidates"].append({"error": str(e)}); continue
                ed = {}; cand = apply_output(sents, ops, targets, out, ed, strict=s4); ok, p = valid(base, cand, it["text"])
                fc = excerpt_features(nlp, cand); d = distance(fc, prof, KEYS)
                rec["candidates"].append({"valid": ok, "dist": d, "preserve": p, "text": cand, "edits": ed,
                                          "feats": {k_: fc.get(k_) for k_ in KEYS + (HELDOUT_S4 if s4 else [])}})
                if ok and d < best_d: best, best_d = cand, d
        elif demo:
            print("no operations planned for", it["id"]); return
        rec["chosen_dist"] = best_d; rec["chosen"] = "base" if best == base else "edited"
        open(os.path.join(od, it["id"] + ".txt"), "w").write(best + "\n")
        with open(log, "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if (k + 1) % 10 == 0 or k + 1 == len(todo):
            el = time.time() - t0; print(f"{k+1}/{len(todo)} {el/60:.0f} min, eta {el/(k+1)*(len(todo)-k-1)/60:.0f} min", flush=True)

OP_FEATURE = {"MERGE_S4": "sent_len", "SUBJECT_WE": "subj_we", "MERGE": "sent_len", "PASSIVE": "passive_pct", "VERBALIZE": "nominal", "PLAIN": "word_len", "SUBJECT": "subj_evidence",
              "CAUSAL": "conn_causal", "PAST": "past_pct", "TONE": "importance"}
def op_success(nlp, op, before, after, merged=False):
    """did the edited sentence change in the intended way?"""
    if not after.strip(): return False
    b = analyse(nlp, [(0, before)])[0] if op not in ("MERGE", "MERGE_S4") else None; x = analyse(nlp, [(0, after)])[0]
    if op in ("MERGE", "MERGE_S4"): return merged and len(SPLIT.split(after)) == 1
    if op == "SUBJECT_WE": return bool(STUDY_SUBJ.match(before)) and bool(re.search(r"\b[Ww]e\b", after)) and not STUDY_SUBJ.match(after)
    if op == "PASSIVE": return x["passive"] and not b["passive"]
    if op == "VERBALIZE": return x["nominal"] < b["nominal"]
    if op == "PLAIN": return x["wlen"] < b["wlen"] - 0.05
    if op == "SUBJECT": return b["evidence"] and not x["evidence"]
    if op == "CAUSAL": return x["causal"] and not b["causal"]
    if op == "PAST": return bool(re.search(r"\b(showed|demonstrated|reported|indicated|suggested|revealed|found|have shown|has shown|have been shown|have demonstrated|have reported)\b", after))
    if op == "TONE": return x["importance"] < b["importance"]
    return False

def cmd_report(a):
    """compare base -> chosen for the excerpts run so far: per-operation success and per-feature gap closure"""
    nlp = FW.load_nlp("en_core_web_sm"); PRE = json.load(open(os.path.join(FS, "analysis", "profiles_pre_en.json" if a.arm == "s4" else "profiles_pre.json")))["profiles"]
    KEYS = struct_of(a.arm)
    recs = [json.loads(l) for l in open(os.path.join(FS, f"{a.arm}_candidates.jsonl"))]
    if a.fields: recs = [r for r in recs if r["target"] in set(a.fields.split(","))]
    opst, cand_n, cand_ok, chosen, rev = {}, 0, 0, 0, {}
    fg = {k: [0.0, 0.0, 0] for k in KEYS}
    for r in recs:
        prof = PRE[r["target"]][r["section"]]; cs = [c for c in r["candidates"] if "text" in c]
        cand_n += len(cs); cand_ok += sum(c["valid"] for c in cs); chosen += r["chosen"] == "edited"
        for c in cs:
            for e in c["edits"].values():
                rv = rev.setdefault(e["op"], [0, 0]); rv[1] += 1; rv[0] += e.get("reverted", False)
                s_ = opst.setdefault(e["op"], [0, 0]); s_[1] += 1; s_[0] += op_success(nlp, e["op"], e["before"], e["after"], e.get("merged", False))
        best = min([c for c in cs if c["valid"]], key=lambda c: c["dist"], default=None)
        fa = best["feats"] if best and best["dist"] < r["base_dist"] else r["base_feats"]
        for k in KEYS:
            g0 = abs((r["base_feats"][k] or 0) - prof[k]["mean"]) / prof[k]["all_sd"]; g1 = abs((fa[k] or 0) - prof[k]["mean"]) / prof[k]["all_sd"]
            fg[k][0] += g0; fg[k][1] += g1; fg[k][2] += 1
    print(f"excerpts {len(recs)}, candidates {cand_n}, valid {cand_ok} ({cand_ok/max(1,cand_n):.0%}), edited version chosen {chosen}")
    print("\noperation success (edited sentence changed as intended):")
    for op, (ok, n) in sorted(opst.items()): print(f"  {op:10s} {ok:3d}/{n:3d}  {ok/max(1,n):.0%}   reverted by content check {rev[op][0]}")
    print("\nmean distance to target field 2019-22 mean (SD units): base -> chosen")
    for k, (g0, g1, n) in fg.items(): print(f"  {k:14s} {g0/n:.3f} -> {g1/n:.3f}  ({(g0-g1)/max(g0,1e-9):+.0%} closed)")
    print(f"  {'ALL':14s} {sum(r['base_dist'] for r in recs)/len(recs):.3f} -> {sum(r['chosen_dist'] for r in recs)/len(recs):.3f}")
    if a.show:
        for r in recs[:a.show]:
            print("\n====", r["id"], r["ops"])
            cs = [c for c in r["candidates"] if "text" in c and c["valid"]]
            if not cs: continue
            for e in min(cs, key=lambda c: c["dist"])["edits"].values():
                print(f"[{e['op']}] {e['before']}\n   -> {e['after']}")

def cmd_pack(a):
    od = os.path.join(FS, a.arm); out = os.path.join(FS, f"{a.arm}_outputs.jsonl.gz"); n = 0
    with gzip.open(out, "wt") as f:
        for fn in sorted(os.listdir(od)):
            if fn.endswith(".txt"): f.write(json.dumps({"id": fn[:-4], "text": open(os.path.join(od, fn)).read()}, ensure_ascii=False) + "\n"); n += 1
    print(n, "->", out)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "pack", "demo", "report"]); ap.add_argument("--show", type=int, default=0); ap.add_argument("--arm", choices=["s3a", "s3b", "s4"], default="s4")
    ap.add_argument("--model", default="qwen3.8-27b-mlx"); ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.7); ap.add_argument("--top-p", dest="top_p", type=float, default=0.9)
    ap.add_argument("--per-field", type=int, default=4); ap.add_argument("--fields", default="")
    ap.add_argument("--force", action="store_true", help="rerun even if outputs exist (old log is renamed)")
    a = ap.parse_args()
    if a.cmd == "pack": cmd_pack(a)
    elif a.cmd == "report": cmd_report(a)
    else: cmd_run(a, demo=a.cmd == "demo")

if __name__ == "__main__": main()
