#!/usr/bin/env python3
"""
Generate a field-specific writing SKILL.md from a digest (skill_corpus.py digest) with the Claude API.

  python3 generate_skill.py skills/2403_immunology            # both periods (pre and post)
  python3 generate_skill.py skills/2403_immunology --period pre --model claude-opus-5-5

Needs ANTHROPIC_API_KEY (env or "ANTHROPIC_API_KEY" in .api.key). Writes
  <dir>/SKILL_pre_llm.md, <dir>/SKILL_post_llm.md and <dir>/generation_log.json (model, prompt hash, usage).
Standard library only. The digest text is sent to the API; it contains only aggregate statistics,
n-gram lists and short CC BY/CC0 excerpts from published articles.
"""
import argparse, hashlib, json, os, sys, time, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.anthropic.com/v1/messages"

INSTRUCTIONS = """You are writing a SKILL.md: a reusable instruction file that lets an AI assistant rewrite a draft
manuscript so that its PROSE STYLE matches a specific life-science subfield in a specific period.
You are given a digest computed from a balanced corpus of open-access research articles in that subfield
(feature distributions per section compared with all 90 life-science subfields, distinctive sentence openers
and lexical bundles, LLM-marker vocabulary rates, and exemplar paragraphs).

Write the SKILL.md for: {target}

Requirements
1. Start with YAML frontmatter: name (kebab-case, e.g. {name}), description (one sentence saying when to use it).
2. Sections, in this order:
   - Purpose and scope (style only; never change data, claims, numbers, citations, or technical content;
     never invent results or references; keep the author's meaning; flag rather than fix scientific issues).
   - Field profile at a glance: 5-8 bullet points describing what makes this subfield's prose distinctive
     relative to life science overall in this period. Use ONLY features whose |d vs all| >= 0.25 or that the
     post digest shows changed by >= 0.2 SD; say which direction and give the field's typical value.
   - Quantitative targets: one table per section (Abstract, Introduction, Results, Discussion) listing
     8-12 features with the field's interquartile range (p25-p75) as the target band. Prefer features that are
     distinctive or style-sensitive (subject types, passive %, tense, hedges, boosters, statistics, causal
     connectives, importance words, limitation statements, word length, sentence length).
   - Section-by-section rewriting rules: concrete, actionable instructions (who/what is the grammatical
     subject, voice, tense, how claims are hedged or boosted, how results are reported, how sections open and
     close), each tied to the evidence in the digest.
   - Phrase bank: field-typical sentence openers and lexical bundles from the digest, grouped by function
     (introducing aims, reporting results, linking experiments, interpreting, concluding). Exclude pure topic
     n-grams (e.g. 'cd t cells') unless they illustrate a construction.
   - Vocabulary to {vocab_rule}.
   - Procedure: step-by-step workflow (diagnose -> rewrite section by section -> self-check -> report changes).
   - Self-check: how to verify the rewrite with `python3 features_wide.py --text <file>` against the target
     bands, plus a qualitative checklist.
   - Short exemplars: 1 sentence-level excerpt per section copied verbatim from the digest's exemplar
     paragraphs, with PMCID and licence for attribution.
3. Be specific and quantitative; avoid generic writing advice that would apply to any field.
4. Keep it under about 1,800 words. Output ONLY the SKILL.md content.
"""

TARGETS = {
    "pre": ("{sub} research articles as written BEFORE large language models (2019-2022)",
            "avoid: list the LLM-marker words whose rate in this field rose after 2022 (from the post digest if "
            "provided, else the marker list), with the pre-LLM field rate per 10k words as the ceiling"),
    "post": ("{sub} research articles as currently written (2024-2025, LLM era)",
             "keep within the current field norm: list LLM-marker words with their current field rate per 10k words "
             "and advise not exceeding it; note which features changed most since 2019-2022"),
}

def api_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    fn = os.path.join(HERE, ".api.key")
    if not k and os.path.exists(fn):
        try: k = json.load(open(fn)).get("ANTHROPIC_API_KEY", "")
        except Exception: pass
    if not k: sys.exit("ANTHROPIC_API_KEY not found (env or .api.key)")
    return k

def call(prompt, model, max_tokens, key):
    body = json.dumps({"model": model, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    for attempt in range(5):
        req = urllib.request.Request(API, data=body, headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                                               "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                js = json.loads(r.read())
            text = "".join(b.get("text", "") for b in js.get("content", []) if b.get("type") == "text")
            return text, js.get("usage", {})
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                print(f"  HTTP {e.code}, retrying ({msg[:80]})", file=sys.stderr); time.sleep(10 * (attempt + 1)); continue
            sys.exit(f"API error {e.code}: {msg}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir"); ap.add_argument("--period", choices=["pre", "post", "both"], default="both")
    ap.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"))
    ap.add_argument("--max-tokens", type=int, default=8000)
    a = ap.parse_args(); key = api_key()
    d = os.path.abspath(a.dir); log = []
    meta = json.load(open(os.path.join(d, "digest_pre.json")))
    sub = meta["subfield"]; name_base = "-".join(sub.lower().replace(",", "").split())
    for period in (["pre", "post"] if a.period == "both" else [a.period]):
        target, vocab = TARGETS[period]
        prompt = INSTRUCTIONS.format(target=target.format(sub=sub), name=f"{name_base}-{period}-llm-style", vocab_rule=vocab)
        prompt += f"\n\n=== DIGEST ({period}) ===\n" + open(os.path.join(d, f"digest_{period}.md")).read()
        if period == "pre" and os.path.exists(os.path.join(d, "digest_post.md")):
            post = open(os.path.join(d, "digest_post.md")).read()
            i = post.find("## LLM-marker vocabulary"); j = post.find("## Exemplar")
            prompt += "\n\n=== POST-LLM MARKER RATES (for the avoid list) ===\n" + post[i:j]
        print(f"{period}: calling {a.model} ...", file=sys.stderr, flush=True)
        text, usage = call(prompt, a.model, a.max_tokens, key)
        out = os.path.join(d, f"SKILL_{period}_llm.md"); open(out, "w").write(text.strip() + "\n")
        log.append({"period": period, "model": a.model, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "usage": usage, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "output": os.path.basename(out)})
        print(f"  -> {out} ({usage})", file=sys.stderr)
    json.dump(log, open(os.path.join(d, "generation_log.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
