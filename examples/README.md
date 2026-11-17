# Worked examples: SKILL d3 + stylecheck

Three recently published paragraphs (all CC BY; citations replaced by [REF]) rewritten by Claude Opus following the
`skills/fields_2019-22_english-speaking_d3/` file of their field, then checked with `tools/stylecheck.py`.

| File stem | Source | SKILL | LLM-style index | P(pre-2023) | field rank /90 | AI-polish words /10k |
|---|---|---|---|---|---|---|
| 1305_n_int_PMC11263074 | Frontiers in Pharmacology 2024, PMC11263074, CC BY | 1305_biotechnology.md (introduction) | 0.51 → 0.36 | 0.32 → 0.36 | 71 → 44 | 30 → 0 |
| 2713_n_dis_PMC12695574 | Frontiers in Public Health 2025, PMC12695574, CC BY | 2713_epidemiology.md (discussion) | 2.25 → 1.08 | 0.14 → 0.44 | 67 → 58 | 0 → 0 |
| 1315_n_dis_PMC11164986 | Communications Biology 2024, PMC11164986, CC BY | 1315_structural-biology.md (discussion) | 0.64 → 0.40 | 0.26 → 0.51 | 6 → 2 | 199 → 0 |

All numbers, citations and abbreviations were kept; the number of hedges and negations is unchanged; no contrastive or causal
connective was added. P(English-speaking author) did not increase (0.49 → 0.46, 0.26 → 0.24, 0.66 → 0.62): the skill removes
habits LLMs introduced, it does not make a paragraph "native".

Reproduce a check:
```
python3 tools/stylecheck.py examples/1315_n_dis_PMC11164986_original.txt --compare examples/1315_n_dis_PMC11164986_rewritten_d3.txt \
        --field 1315 --section discussion --core --plot check.png
```
Original texts are © their authors, reused under CC BY 4.0 (see the PMCIDs above).
