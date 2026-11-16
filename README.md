# genomicswa — field-style SKILL files and tools for life-science prose

This repository holds **SKILL.md files** that describe how research articles in 90 life- and health-science fields are written. It also holds the **tools** used to build and test them.

The SKILL files are instructions for a large language model (LLM). They say how to rewrite an Introduction or Discussion so that its style is typical of a target field, without changing its content. They were derived from a corpus study of 93,760 open-access articles in PubMed Central (2019–2025). The study asked three questions:

1. Is disciplinary prose style measurable, beyond topic and journal formatting? How does it compare with differences between journals, laboratories and countries?
2. How did LLMs change scientific writing from 2023 onwards? Did they homogenise fields?
3. Can a corpus-derived SKILL.md, used with a local or frontier LLM, move a text toward a field's style, or remove typical "LLM-ness", while preserving content?

> Status: research prototype accompanying a manuscript in preparation (2026). Numbers below are from the working draft and may change.

---

## Contents

```
skills/
  fields_2024-25_r2/          90 SKILL.md files: current (2024–25) style of each field  ← recommended
  fields_2024-25_r1/          round-1 versions (kept for comparison; tend to overshoot)
  fields_2019-22_de-llm_d2/   90 SKILL.md files: 2019–22 (pre-LLM) style + "remove AI-polishing" rules
  pilot_immunology/           hand-written pilot SKILLs for Immunology (pre- and post-LLM)
  FIELDS.csv                  OpenAlex subfield id, name, file stem, number of English-speaking-author papers
tools/
  fieldstyle.py               build digests, sample excerpts, rewrite with a SKILL via LM Studio (local LLM)
  fieldstyle_struct.py        meaning-preserving structural editor (arm s4; earlier arms s3a/s3b)
  features_wide.py            36 syntactic/rhetorical features (spaCy en_core_web_sm)
  rewrite_eval.py             preservation checks (numbers, citations, abbreviations), LLM-marker counts
  llm_probe.py                LM Studio helper (server detection; default port 1235)
  skill_corpus.py, generate_skill.py, fs_skill.py, fs_skill2.py   SKILL generation
  fs_build_en.py, fs_eval2.py, fs_s4analysis.py                   targets and evaluation
data/
  profiles.json               per-field 2024–25 feature means (introduction/discussion)
  profiles_pre.json           per-field 2019–22 means (all authors)
  profiles_pre_en.json        per-field 2019–22 means of papers with an English-speaking last author (shrunk, k = 50)
  classifier.json             90-field style classifier (28 features)
  period_classifier.json      2019–22 vs 2024–25 classifier
  en_classifier.json          field-adjusted English-speaking-author classifier
  llm_index_ref.json          reference means/SDs for the LLM-style index
results/                      small summary tables (see "Findings")
```

The corpus itself (full texts) is **not** redistributed. The analysis scripts in `tools/` expect a local corpus at `../PubMedCorpus/`; they are included for transparency.

---

## Using a SKILL.md

Each field file (for example `skills/fields_2024-25_r2/2403_immunology.md`) has these parts:

- general rules: change style only, never numbers, citations, claims or subject matter
- for the Introduction and the Discussion, the 4–7 features where the field differs most from other fields, each with a direction, a target quantity per 300 words, a concrete operation and an example
- typical non-topical openers
- a ceiling for vocabulary typical of AI polishing
- one short verbatim CC BY exemplar per section, with its PMCID
- a check procedure

**With Claude or another chat LLM:** attach or paste the SKILL.md, then paste one section (150–450 words, with citations replaced by `[REF]`) and ask:

> Rewrite this Discussion excerpt following the attached SKILL. Change style only. Keep every number, [REF], abbreviation and claim.

**With a local model (LM Studio):**

```bash
lms server start --port 1235          # tools default to http://localhost:1235/v1 (override with LMSTUDIO_BASE)
python3 tools/fieldstyle.py rewrite --tag r2 --model qwen3.8-27b-mlx
```

`fieldstyle.py` reproduces the experiment: it expects `fieldstyle/sample.json` and `fieldstyle/skills_<tag>/`, built from the corpus. For your own text, the simplest route is to send the SKILL.md plus your excerpt to any OpenAI-compatible endpoint. For example, LM Studio's `/v1/chat/completions` with the SKILL as the first part of the user message, temperature 0, and (for Qwen3) an assistant prefill of `<think>\n\n</think>\n\n` to disable thinking.

**Structural editor (`fieldstyle_struct.py`, arm `s4`).** The editor changes only the sentences that a measured plan selects, using one of six operations:

- merging a sentence with an anaphoric follower (*It/They/This…*), using *and*, *which* or a semicolon
- *This study* → *We* subjects
- passivising "We + verb + object" main clauses
- plain wording
- toning down importance words
- past tense for reporting verbs whose subject is prior work

Every edit is reverted if it adds a contrastive or causal connective, changes the number of hedges or negations, or changes too many words. Candidates (n = 2, T = 0.7) are selected by distance to the target profile.

```bash
python3 tools/fieldstyle_struct.py demo --arm s4 --fields 2403   # show plan and prompt, no LLM call
python3 tools/fieldstyle_struct.py run  --arm s4 --n 2 --temperature 0.7
```

**Recommended use:** SKILL.md for the lexical layer and for agency ("we"), then structural edits offered as *suggestions* that the author accepts or rejects. Do not apply any automatic rewrite to a manuscript without reading it.

---

## What the study found (working draft)

**Corpus and features**

- 93,760 PMC open-access research articles from 90 OpenAlex subfields, 2019–2025, balanced by year and capped per journal.
- Every section is described by 36 features: clause-subject types, passive voice, hedges and boosters, tense, statistics, rhetorical moves, connectives, nominalisation, lexical diversity.

**1. Disciplinary style is real but small per article**

- Style features identify the subfield at 0.10–0.11 accuracy every year (chance 0.011).
- Variance shares:
  - field 3.9%
  - journal within field 4.8%
  - laboratory (last author) within field 17.7%
  - first author 23.3%
- Laboratories differ about twice as much as fields.
- The last author's country explains about 28% of laboratory differences and about 35% of between-field differences in LLM-era change.
- English-speaking authorship can be predicted from field-adjusted style with AUC 0.70–0.76.

**2. LLM-era change, but no homogenisation**

- From 2023 an LLM-style index rose in every field: +0.05 SD (2023), +0.20 (2024), +0.53 (2025).
- The changes are longer words, more lexical diversity, more nominalisation and importance words, less passive voice, about one third fewer causal connectives, fewer "we" subjects and more "this study" subjects.
- Field identifiability did not fall.

**3. Who adopted it**

- The excess share of LLM-like papers in 2025, over each region's own 2019–22 baseline, was:
  - English-speaking countries +20 percentage points
  - continental Europe +29
  - Japan and Korea +34
  - Middle East and South Asia +39
  - China and Taiwan +51
- Across countries the excess correlates with English proficiency (EF EPI; r = −0.66). Within Europe it follows proficiency rather than grammatical distance from English.
- The rise was larger for less productive non-English-speaking authors. We read this as LLMs lowering a language barrier.
- Country output did not rise beyond trend.
- Japan is a clear outlier, 20 pp below prediction. Acknowledgements show why:
  - 14.7% of Japanese-led papers thanked an English-editing service in 2019–22, five times any other country.
  - This share did not fall after 2023, whereas it fell in Spain, Germany, Poland and Italy.
  - Across non-English-speaking countries, papers that acknowledged editing rose 0.11 SD less on the LLM index.
- Self-disclosed generative-AI use was rare (2.5% of 2025 papers) but validated the index: 64% of disclosing papers were LLM-like, against 33% of the rest.

**4. Rewriting with SKILL files: what worked and what did not**

| Round | Method | Result | Problem |
|---|---|---|---|
| r1 | field SKILL, full rewrite by a local 27B model | target-field rank 47.5 → 23 (native excerpts 18.5); numbers and citations ≥ 99.8% kept | some gains came from reframing content; LLM-ness increased |
| r2 | revised SKILL (caps, content-bound targets removed) | overshoot halved; no LLM-ness increase | typicality slightly lower (rank 25); variation between samples exceeded the effect of revising the skill |
| d2 | 2019–22 SKILL + de-LLM rules | LLM marker words −88% | structural layer barely moved (10–14% of the gap); text moved away from English-speaking style |
| s3a | sentence-level edits + selection | period classifier gap closed about 29% | merges added unsupported *whereas*; causal insertion added unsupported *therefore* |
| s4 | English-speaking-author target, meaning-preserving operations + guards | content 100% kept; no drift from English-speaking style; LLM index −0.10 | structural change limited to targeted features; about 8% of sampled edits still shifted meaning |

"LLM-ness" has two layers:

- a **lexical layer** (marker words, inflated adjectives, "this study" subjects), which a SKILL file or simple rules remove reliably
- a **structural layer** (sentence length, voice, nominal density), which an LLM tends to re-impose when it regenerates text, and which can be restored without changing meaning only to a limited extent

Small results tables are in `results/`. Rewriting runs used Qwen3.8-27B (MLX, LM Studio) with thinking disabled. The immunology pilot also compared Claude.

**Limitations**

- Style indicators are proxies, not evidence of LLM use.
- Classifiers are weak at excerpt level.
- Human ratings of naturalness and fidelity have not yet been collected.
- One local model was used for the large runs.

---

## Data sources and licences

- Full texts: PMC Article Datasets (AWS Open Data). Field labels, authorships and countries: OpenAlex. English proficiency: EF EPI 2025.
- Exemplar sentences quoted in SKILL files come only from **CC BY** articles and carry their PMCIDs. This was verified for all 546 quotations.
- **SKILL.md files and documentation:** Creative Commons Attribution 4.0 (CC BY 4.0).
- **Code:** MIT License (see `LICENSE`).

## Citation

Endo T. *Disciplinary prose styles in the life sciences: persistence through the LLM era, and partial transfer with corpus-derived skill files.* Manuscript in preparation, 2026. (Citation to be updated.)

---

### 日本語の概要

生命科学 90 分野の論文の文体を、PMC のオープンアクセス論文 9.4万本から数値化しました。それを LLM 用の指示書（SKILL.md）にまとめ、書き換えへの効果を検証しています。

- **分野差**：分野ごとの文体の差は測定できますが、1本の論文に占める割合は小さいものです（ばらつきの約 4%）。研究室による差はその約 2倍、国による差も大きくあります。
- **LLM 以後の変化**：2023年以降、全分野で同じ方向に文体が変わりました。上昇幅は非英語圏で大きく、英語力と負に相関します。
- **日本**：英文校正サービスへの謝辞が他国の 5倍あり、LLM 以後も減っていません。このため、LLM らしさが英語力から予想されるより低くなっています。
- **SKILL.md での書き換え**：語彙の層（AI らしい単語、「this study」主語）は確実に変えられます。構文の層は、意味を変えずに戻せる範囲が限られます。
- **推奨する使い方**：SKILL.md で語彙と主語を整え、構文の修正は提案として著者が判断する、という組み合わせです。
