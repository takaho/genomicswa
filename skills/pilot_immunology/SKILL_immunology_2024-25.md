---
name: immunology-post-llm-style
description: Rewrite a draft immunology research article so its prose matches how immunology papers are written now (2024–2025), within current field norms and without changing any scientific content.
---

# Immunology prose style, current (2024–2025)

Evidence base: 300 open-access immunology research articles (OpenAlex subfield 2403, 150 per year, ≤10% from any one journal), compared with 90 life-science subfields in the same years and with the field's own 2019–2022 profile. First authors: China 26%, US 18%, Japan 5%, UK 5%.

## Purpose and scope
- Change **style only**: subjects, voice, tense, openers, hedging/boosting, connectives, word choice.
- Never change data, numbers, statistics, claims, figure/table references, citations or technical terms. Never add results, mechanisms or references.
- Flag over- or under-stated claims for the author instead of altering them.
- Methods are out of scope.

## Field profile at a glance
What still distinguishes immunology from life science overall (unchanged since 2019–2022):
- **"We" narrates the experiments**: Results median 9% of clause subjects vs 1.5% across fields (d = +0.82, stronger than before); Discussion and Abstract d ≈ +0.42.
- **Cells and molecules are the main subjects**; patients rarely are.
- **Qualitative reporting**: few statistics in Results (d = −0.57) and few numbers (d = −0.74); dense abbreviations.
- **Booster verbs above average** (demonstrate, reveal, show; d +0.2 to +0.3); **purpose clauses** still open experiments ("To further…", "Next, we…").

What changed since 2019–2022 (in SD units of the field's pre-LLM spread):
- **Longer words**: +0.4 to +0.6 SD in every section (Discussion median 5.63 characters per word).
- **Higher lexical diversity**: MATTR +0.3 to +0.6 SD.
- **Less passive voice**: Introduction −0.44, Results and Discussion −0.21.
- **More "evidence" subjects** ("These findings…", "This study…"): +0.2 to +0.35.
- **Fewer causal connectives** (thus/therefore): Results −0.29, Discussion −0.24.
- **More limitation and future-work statements** in the Discussion: +0.34 each.
- **More importance words** (crucial, key, essential): +0.2.
- **More nominalisations**: +0.2.
- LLM-marker vocabulary rose from 12.9 to 31.1 per 10k words (all fields now ≈ 30.6).

## Quantitative targets (field interquartile range, 2024–2025)
Units: % = share of clause subjects or finite verbs; /1k = per 1,000 words. Check with `features_wide.py --text`.

**Abstract**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 20–25.5 | 22 |
| characters per word | 5.6–6.1 | 5.8 |
| subject = we | 0–15% | 0% |
| subject = data/results/study | 7–18% | 12.5% |
| passive clauses | 11–32% | 26% |
| booster verbs | 3.4–11 /1k | 4.5 |
| numbers | 5–30 /1k | 32 |

**Introduction**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 22–27 | 24 |
| characters per word | 5.6–6.0 | 5.8 |
| subject = we | 1.6–8% | 2.7% |
| subject = data/results/study | 3.4–10% | 7.3% |
| subject = it/there | 0–4.5% | 3.2% |
| passive clauses | 16–27% | 21% |
| past tense | 9–24% | 17% |
| booster verbs | 2–7 /1k | 3.3 |
| importance words | 1.9–7 /1k | 3 |
| nominalisations | 56–78 /1k | 66 |

**Results**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 21.5–27 | 24 |
| characters per word | 5.2–5.6 | 5.4 |
| subject = we | 2.7–17% | 1.5% |
| subject = data/results/study | 5–12% | 7.6% |
| passive clauses | 18.5–34% | 25% |
| hedging verbs | 1.7–5.2 /1k | 2.4 |
| booster verbs | 4.8–10.3 /1k | 6.1 |
| causal connectives | 0–1.9 /1k | 0 |
| statistical expressions | 1–15 /1k | 23 |

**Discussion**
| feature | target band | all-field median |
|---|---|---|
| words per sentence | 23–27.5 | 24.4 |
| characters per word | 5.4–5.8 | 5.7 |
| subject = we | 3–11% | 3.7% |
| subject = data/results/study | 8.4–16% | 12.7% |
| passive clauses | 15–25% | 19% |
| past tense | 23.5–46% | 41% |
| modal hedges | 3.4–8.4 /1k | 6 |
| booster verbs | 4.8–9.6 /1k | 5.8 |
| causal connectives | 0.9–3.4 /1k | 1.9 |
| importance words | 1.8–4.9 /1k | 2.4 |
| limitation statements | 0–1.2 /1k | 0.8 |

## Section-by-section rewriting rules
**Abstract**
1. Keep "Here, we…" for the main claim; "Our study/Our findings…" is now also common as a closing subject.
2. Present tense for conclusions; keep sentences around 20–25 words.
3. Use structured-abstract labels only if the target journal requires them (labelled "Results:/Conclusions:" openers appear in this period).

**Introduction**
1. Entities as subjects for background mechanisms; replace expletives ("It is well known that…") with the entity.
2. Prefer active voice (passive 16–27% of clauses).
3. Signal the gap and significance explicitly but briefly ("The role of X in Y remains unclear"); 2–7 importance words per 1k words, no more.
4. Turn to the study with "Here, we…", "We previously showed…", "In this study, we…".

**Results**
1. Open experiments with "To further…", "Next, we…", "To investigate…"; keep "we" + past tense for actions.
2. Interpret with "These results/data indicate…", "Collectively, these…"; use "Consistent with…" for confirmations.
3. Limit thus/therefore to genuine inferences (≤ 2 per 1k words); join steps with "Next," or a new purpose clause instead.
4. Keep statistics as in the draft; do not add them.

**Discussion**
1. Open with "Here, we…" or "Our data…" summarising the main finding.
2. Use "These observations/findings…" or "Our data…" as subjects when interpreting; alternate with "Previous studies…".
3. Hedge mechanisms with modals (3–8 per 1k words); boost the central finding once or twice per paragraph.
4. Include a short, specific limitations paragraph (current norm: about one limitation sentence per 1,000 words), followed by one concrete next step.
5. Close with "In summary, …" or "Taken together, …" and the immunological implication.

## Phrase bank (2024–2025 immunology)
- **Introducing the study:** Here, we / In this study, we / We previously showed / We further
- **Starting an experiment:** To further / To investigate / Next, we / We next / Therefore, we
- **Reporting:** We found that / We observed / In contrast, / Consistent with
- **Interpreting:** These results indicate / These data / These observations / Our data / Collectively, these
- **Flagging a point:** Of note, / Specifically, we
- **Concluding:** Taken together, / In summary, / In conclusion, / Based on these findings

## Vocabulary: keep within the current field norm
Current rates in immunology (per 10k words; all fields ≈ 30.6 in total): additionally 5.0, notably 4.2, crucial 3.7, enhance 3.0, enhancing 1.8, robust 1.8, insights 1.7, enhances 1.5, comprehensive 1.2, elucidate 1.1, pivotal 1.1, landscape 0.7, interplay 0.6, underscoring 0.5, underscore 0.4.
- Do not exceed these rates; a draft above them reads as machine-polished even by current standards.
- Avoid stacking two marker words in one sentence ("Notably, this crucial pathway…").
- Rare markers (delve, intricate, tapestry, realm, showcase, multifaceted) remain uncommon in the field; replace them.

## Procedure
1. **Diagnose.** Run `python3 features_wide.py --text <section>.txt` per section; mark features outside the bands and count marker words.
2. **Rewrite section by section** using the rules; change only what moves a feature toward its band.
3. **Self-check** (below).
4. **Report** changes by type and list flagged claims.

## Self-check
- Re-run `features_wide.py --text`; targeted features within or closer to the bands.
- Numbers, units, statistics, figure references and citations unchanged (diff the versions).
- No new claims or references.
- Marker words at or below the current field rates; no sentence with two markers.
- Discussion contains a brief, specific limitations statement.

## Short exemplars (verbatim, CC BY)
- Introduction — PMC11588638 (Frontiers in Immunology, 2024, CC BY): "These hallmark residues are considered to play important roles in stabilizing VHHs in the absence of light chains ( )."
- Results — PMC12281370 (Cell Reports Medicine, 2025, CC BY): "To investigate the CD4+ Th1 polarization induced by UCPVax, we performed a longitudinal ex vivo assessment of IFNγ, TNF-α, and IL-2 production by intracellular cytokine staining (ICS) assay."
- Discussion — PMC12256444 (Frontiers in Cell and Developmental Biology, 2025, CC BY): "Our model is the first, to address direct interactions between NK cells and senescent kidney cells."
