---
name: immunology-pre-llm-style
description: Rewrite a draft immunology research article so its prose matches how immunology papers were written before large language models (2019–2022), without changing any scientific content.
---

# Immunology prose style, pre-LLM (2019–2022)

Evidence base: 600 open-access immunology research articles (OpenAlex subfield 2403, 150 per year, ≤10% from any one journal), compared with 90 life-science subfields in the same years. Main journals: Frontiers in Immunology, Int J Mol Sci, Scientific Reports, Nature Communications, PLoS Pathogens, J Immunol, JEM. First authors: US 28%, China 20%.

## Purpose and scope
- Change **style only**: grammatical subjects, voice, tense, sentence openers, hedging/boosting, connectives, word choice.
- Never change data, numbers, statistics, claims, figure/table references, citations or technical terms. Never add results, mechanisms or references.
- If a sentence over- or under-states the evidence, keep the claim as written and **flag** it for the author; do not silently strengthen or weaken it.
- Methods sections are out of scope (they are formulaic and changed least after 2022).

## Field profile at a glance (vs all life-science subfields, 2019–2022)
- **The researchers are the narrators.** "We" is the grammatical subject far more often than in life science overall, especially in Results (median 9% of clause subjects vs 2%; d = +0.66) and also in Abstract, Introduction and Discussion (d ≈ +0.33).
- **Molecules and cells carry the story.** Cells, genes, cytokines and receptors are the subjects of most clauses (Discussion median 60% vs 57%); patients are rarely subjects (d ≈ −0.4).
- **Experiments are chained by purpose clauses.** Results paragraphs open with "To determine…", "To further…", "To confirm…", "We next…" and close with "These results/data…", "Taken together…".
- **Evidence is reported qualitatively, not statistically.** Few statistical expressions (Results median 4.8 per 1k words vs 21.6) and few numbers (33 vs 69 per 1k); abbreviations are dense (≈ 97 per 1k vs 53).
- **Confident framing with measured hedging.** Booster verbs (demonstrate, reveal, show) are above average in every section (d +0.33 to +0.37); in Results, interpretive hedges ("suggest", "indicate", "may") are also above average because results are interpreted step by step.
- **Few explicit limitation statements** in the Discussion (median 0 per 1k vs 0.6; d = −0.35).
- Present tense dominates Abstract and Discussion (past-tense share of finite verbs: Abstract median 55% vs 65%; Discussion 39% vs 44%).

## Quantitative targets (aim for the field's interquartile range)
Units: % = share of clause subjects or finite verbs; /1k = per 1,000 words. Check with `features_wide.py --text`.

**Abstract**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 21–27 | 23 |
| subject = we | 3–17% | 5% |
| passive clauses | 12–33% | 29% |
| past tense | 30–70% | 65% |
| booster verbs | 3–10 /1k | 4 |
| statistical expressions | 0–4 /1k | 5 |
| numbers | 4–24 /1k | 30 |

**Introduction**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 22.5–27.5 | 25 |
| characters per word | 5.5–5.8 | 5.65 |
| subject = we | 2.6–8.7% | 3.3% |
| subject = cells/genes/entities | 59–71% | 63% |
| subject = it/there | 0–5% | 3.8% |
| passive clauses | 19–32% | 25% |
| modal hedges | 0–4 /1k | 2.6 |
| booster verbs | 2–7 /1k | 3 |
| importance words | 1.6–5.6 /1k | 2.6 |
| aim statements | 1.2–3.4 /1k | 2.6 |

**Results**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 22.5–28.5 | 24 |
| subject = we | 3–15.5% | 1.9% |
| passive clauses | 21–37% | 27% |
| past tense | 66–87% | 82% |
| hedging verbs (suggest/indicate) | 1.6–5 /1k | 1.9 |
| booster verbs | 4–9 /1k | 5.5 |
| causal connectives (thus/therefore) | 0.3–2.6 /1k | 0.7 |
| aim statements ("to determine…") | 0.8–3 /1k | 0.6 |
| statistical expressions | 1–15 /1k | 22 |
| characters per word | 5.1–5.5 | 5.3 |

**Discussion**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 23–28.5 | 25 |
| characters per word | 5.3–5.7 | 5.5 |
| subject = we | 3.7–11.8% | 4.9% |
| subject = data/results/study | 6.7–14% | 10.9% |
| subject = it/there | 1.6–6% | 4.3% |
| passive clauses | 17–27% | 22% |
| past tense | 26–52% | 44% |
| modal hedges | 3.4–8.4 /1k | 6.2 |
| booster verbs | 4.5–9.2 /1k | 5.1 |
| causal connectives | 1.1–4 /1k | 2.6 |
| importance words | 1.2–4.4 /1k | 1.9 |
| limitation statements | 0–0.8 /1k | 0.6 |

## Section-by-section rewriting rules
**Abstract**
1. Open the claim of the paper with "Here, we show/demonstrate/identify…" (the most over-represented opener in the field, z = 8.4).
2. Prefer present tense for conclusions ("X is required for…", "these data reveal…"); past tense only for what was done.
3. Make "we" or the key molecule/cell the subject; avoid "This study/The present work" as subject.
4. Keep numbers minimal; do not add statistics that are not in the draft.
5. Close with "Taken together, …" or "Our data/findings suggest/reveal…".

**Introduction**
1. Build from immune mechanism to gap: cells/cytokines/receptors as subjects ("NK cells are…", "IL-17 promotes…").
2. Avoid expletive openings ("It is known that…", "There are…"); rewrite with the entity as subject.
3. State the gap compactly, then turn to the study in the last paragraph with "Here, we…" / "In this study, we…".
4. Use "In contrast, …" to set up opposing findings (over-represented, z = 4.6).

**Results**
1. Open each subsection or experiment with a purpose clause: "To determine whether…, we…", "To further examine…", "To confirm…", "We next asked/examined…".
2. Report with "we" + past tense ("We found that…", "We observed…"); molecules as subjects for outcomes ("CD8+ T cells from … produced less IFN-γ").
3. Interpret each step in one sentence with a light hedge: "These results suggest that…", "These data indicate…". Allow "thus/therefore we…" to link experiments.
4. Do not convert qualitative statements into statistics; keep "As expected, …" and "Consistent with…" for confirmations.
5. Close a block with "Taken together/Collectively, these data…".

**Discussion**
1. Open with a one-sentence summary: "Here, we show/demonstrate that…" or "Our data reveal…".
2. Alternate own findings ("Our data…", "We have shown…") with literature ("Previous studies…", "Consistent with…").
3. Hedge mechanisms with modals (may/might/could, 3–8 per 1k words); boost the core finding with demonstrate/reveal/show.
4. Keep limitation statements brief (one short paragraph at most) and avoid formulaic "future studies are needed" sentences.
5. End with "In summary, …" or "Taken together, …" and an immunological implication.

## Phrase bank (2019–2022 immunology)
- **Introducing the study:** Here, we show / Here, we describe / In this study, we / We hypothesized that
- **Starting an experiment:** To determine whether / To further investigate / To confirm / To assess / We next / We also
- **Reporting:** We found that / We observed / As expected, / In contrast, / Consistent with
- **Interpreting:** These results suggest that / These data indicate / Our data / Our findings / Therefore, we
- **Linking to literature:** Previous studies / Consistent with previous reports / In agreement with
- **Concluding:** Taken together, / Collectively, these / In summary, / Finally, we

## Vocabulary to avoid
These words rose sharply in immunology after 2022 (field rate 12.9 → 31.1 per 10k words). Keep each at or below the pre-LLM field rate; replace on sight:
additionally (2.2 per 10k pre) → "In addition," / "We also" · notably (1.8) → "Of note," or delete · crucial (1.4) / pivotal (0.4) → "important", "key", "required" · enhance/enhances/enhancing (3.0 combined) → "increase", "promote", "augment" · robust (1.2) → "strong", "consistent" · insights (0.6) → "evidence", "information" · comprehensive (0.4) → "detailed", "systematic" · elucidate (0.6) → "define", "determine" · interplay, landscape, underscore(s), delve, intricate, multifaceted, realm, showcase → rewrite plainly.

## Procedure
1. **Diagnose.** Run `python3 features_wide.py --text <section>.txt` for Abstract, Introduction, Results and Discussion. Mark features outside the target bands; count avoid-list words.
2. **Rewrite section by section** with the rules above, changing only sentences that move a feature toward its band or remove an avoid-list word. Preserve every number, citation marker and technical term.
3. **Self-check** (below).
4. **Report** to the author: a list of changes by type (subject, voice, opener, hedge/booster, vocabulary) and any flagged claims.

## Self-check
- Re-run `features_wide.py --text`; every targeted feature should be within or closer to its band.
- All numbers, units, p-values, figure references and citations are unchanged (diff the two versions).
- No new claims, mechanisms or references were introduced.
- Avoid-list words are at or below the pre-LLM rates.
- Results subsections open with a purpose clause and close with an interpretation; Discussion opens with "Here, we…" or an equivalent summary.

## Short exemplars (verbatim, CC BY)
- Introduction — PMC7872032 (Virulence, 2021, CC BY): "After viral RNA is recognized by RIG-I and MDA5, activated RIG-I and MDA5 are able to interact with mitochondrial antiviral signaling protein (MAVS) through 2CARD interaction."
- Results — PMC7179671 (Frontiers in Physiology, 2020, CC BY): "In this study, we employed qRT-PCR to investigate the tissue distribution of TmPGRP-LE transcripts (Figure 1)."
- Discussion — PMC8358051 (Scientific Reports, 2021, CC BY): "In this study we show that in human dendritic cells, the entry of Lm into the cytosol drives a change in gene expression and a metabolic shift towards cholesterol synthesis and export."
