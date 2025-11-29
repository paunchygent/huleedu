# BT SE and Anchor Inversion Analysis Report

**Date:** 2025-11-29
**Batch UUID:** `364d4746-b34e-4038-b825-0f6f9d7e2251`
**Internal Batch ID:** 108
**Related Task:** `TASKS/assessment/bt-se-zero-anomaly-and-anchor-inversions-investigation.md`

---

## Executive Summary

Two issues identified during ENG5 batch validation:
1. **SE = 0 Bug**: TUVA_KARLSSON (student) has SE = 0 due to being unintentionally selected as BT reference
2. **Anchor Inversions**: 3 anchor grade inversions indicate either prompt issues or anchor quality mismatch

---

## Batch Metadata

```
State: COMPLETED
Total Budget: 200
Completed Comparisons: 200
Failed Comparisons: 0
Iterations: 17
Total Essays: 24 (Students: 12, Anchors: 12)
```

### SE Summary
```json
{
  "mean_se": 1.1772451183974801,
  "max_se": 2.0,
  "min_se": 0.0,
  "item_count": 24,
  "comparison_count": 200,
  "items_at_cap": 2,
  "isolated_items": 0,
  "mean_comparisons_per_item": 16.666666666666668,
  "min_comparisons_per_item": 16,
  "max_comparisons_per_item": 17
}
```

---

## Full BT Ranking

| Rank | Essay ID | BT Score | BT SE | Wins | Losses | Total | Anchor | Grade |
|------|----------|----------|-------|------|--------|-------|--------|-------|
| 1 | INGER_ISFELDT_SA24_ENG5_NP__F61508AA | 4.6705 | 1.2350 | 16 | 0 | 16 | No | - |
| 2 | EDITH_STRANDLER_SA24_ENG5_N_00080674 | 4.3233 | 1.1928 | 15 | 1 | 16 | No | - |
| 3 | JULIA_AXELSSON_SA24_ENG5_NP_F4F3DB4B | 4.0387 | 1.0689 | 14 | 2 | 16 | No | - |
| 4 | ANCHOR_12_c4dd6d9e | 3.7212 | 1.0035 | 14 | 3 | 17 | Yes | A |
| 5 | ANCHOR_2_2d2a7021 | 2.9503 | 0.9488 | 12 | 5 | 17 | Yes | B |
| 6 | ANCHOR_5_33226de9 | 2.9353 | 0.9532 | 12 | 5 | 17 | Yes | B |
| 7 | ANCHOR_10_3e7b0acc | 2.3140 | 0.9343 | 12 | 5 | 17 | Yes | A |
| 8 | TUVA_KARLSSON_BF24_ENG5_NP__3D832736 | 2.2510 | **0.0000** | 11 | 6 | 17 | No | - |
| 9 | ELIAS_KUHLIN_BF24_ENG5_NP_W_EFC1C16D | 2.2504 | 0.9277 | 11 | 6 | 17 | No | - |
| 10 | SADEY_NILZ_N_SA24_ENG5_NP_W_3D2DC966 | 1.5259 | 0.9416 | 9 | 7 | 16 | No | - |
| 11 | JULIA_POST_SA24_ENG5_NP_WRI_BFC8E68F | 1.1351 | 0.9533 | 9 | 8 | 17 | No | - |
| 12 | ELIN_ROS_N_BF24_ENG5_NP_WRI_12A74A6E | 0.3722 | 1.0131 | 7 | 9 | 16 | No | - |
| 13 | LINNEA_WALFRIDSON_SA24_ENG5_2A0443AC | 0.3567 | 1.0269 | 8 | 9 | 17 | No | - |
| 14 | JOEL_FALK_BF24_ENG5_NP_WRIT_AC95BF46 | 0.0108 | 1.0734 | 9 | 8 | 17 | No | - |
| 15 | ANCHOR_6_239581c0 | -0.0322 | 1.0460 | 7 | 10 | 17 | Yes | C+ |
| 16 | SOFIA_ANDERSSON_SA24_ENG5_N_B89A1F08 | -0.9389 | 1.1344 | 7 | 10 | 17 | No | - |
| 17 | HUGO_JOHANSSON_BF24_ENG5_NP_27D0579E | -1.3769 | 1.2049 | 7 | 10 | 17 | No | - |
| 18 | ANCHOR_9_c63d675c | -1.8802 | 1.2828 | 6 | 10 | 16 | Yes | **D+** |
| 19 | ANCHOR_3_78552934 | -1.9957 | 1.2563 | 4 | 12 | 16 | Yes | **C-** |
| 20 | ANCHOR_11_497c210e | -3.2394 | 1.4857 | 4 | 12 | 16 | Yes | **E+** |
| 21 | ANCHOR_8_c875b810 | -4.0535 | 1.6680 | 3 | 14 | 17 | Yes | **D-** |
| 22 | ANCHOR_4_9a192186 | -5.0355 | 1.9033 | 2 | 15 | 17 | Yes | F+ |
| 23 | ANCHOR_1_8daeded7 | -6.3122 | 2.0000 | 1 | 16 | 17 | Yes | F+ |
| 24 | ANCHOR_7_d6319ec2 | -7.9908 | 2.0000 | 0 | 17 | 17 | Yes | **E-** |

**Bold grades indicate inversions**

---

## Anchor Inversions Detail

### Expected Anchor Order (by grade)
A > B > C+ > C- > D+ > D- > E+ > E- > F+

### Observed Inversions

#### Inversion 1: C- vs D+

| Anchor | Grade | Wins | Losses | Win Rate | BT Score | Rank |
|--------|-------|------|--------|----------|----------|------|
| ANCHOR_9 | D+ | 6 | 10 | 37.5% | -1.8802 | 18 |
| ANCHOR_3 | C- | 4 | 12 | 25.0% | -1.9957 | 19 |

**Expected:** C- > D+ (C- should rank higher)
**Observed:** D+ > C- (D+ ranks higher)

#### Inversion 2: D- vs E+

| Anchor | Grade | Wins | Losses | Win Rate | BT Score | Rank |
|--------|-------|------|--------|----------|----------|------|
| ANCHOR_11 | E+ | 4 | 12 | 25.0% | -3.2394 | 20 |
| ANCHOR_8 | D- | 3 | 14 | 17.6% | -4.0535 | 21 |

**Expected:** D- > E+ (D- should rank higher)
**Observed:** E+ > D- (E+ ranks higher)

#### Inversion 3: E- vs F+

| Anchor | Grade | Wins | Losses | Win Rate | BT Score | Rank |
|--------|-------|------|--------|----------|----------|------|
| ANCHOR_4 | F+ | 2 | 15 | 11.8% | -5.0355 | 22 |
| ANCHOR_1 | F+ | 1 | 16 | 5.9% | -6.3122 | 23 |
| ANCHOR_7 | E- | 0 | 17 | 0.0% | -7.9908 | 24 |

**Expected:** E- > F+ (E- should rank higher than both F+ anchors)
**Observed:** F+ > F+ > E- (E- ranks lowest)

---

## ANCHOR_3 (C-) Raw Comparison Data

| Opponent | Winner | Confidence | Justification |
|----------|--------|------------|---------------|
| ANCHOR_2 (B) | essay_b (ANCHOR_2) | 4.0 | Essay B has superior content structure, examples, and language accuracy despite minor errors. |
| ELIAS_KUHLIN | essay_b (ELIAS) | 4.0 | Essay B demonstrates superior content organization, language fluency, and engagement with assignment requirements despite minor errors. |
| SADEY_NILZ_N | essay_b (SADEY) | 4.0 | Essay B has better structure, more developed ideas, and superior language control despite both having errors. |
| ANCHOR_8 (D-) | essay_a (ANCHOR_3) | 3.5 | Essay A better addresses assignment requirements with clearer structure, specific role model examples, and more coherent discussion of influence. |
| JOEL_FALK | essay_a (JOEL) | 3.0 | Essay A better addresses assignment requirements with clearer personal role model introduction and greater coherence despite similar errors. |
| ANCHOR_11 (E+) | essay_b (ANCHOR_3) | 4.0 | Essay B better addresses assignment requirements with multiple role models, deeper analysis of societal impact, and more structured argument despite spelling errors. |
| SOFIA_ANDERSSON | essay_a (SOFIA) | 3.0 | Essay A addresses more assignment points comprehensively despite language errors. Better structure and personal reflection. |
| ANCHOR_9 (D+) | essay_a (ANCHOR_3) | 3.0 | Essay A has better structure, more concrete examples, and clearer coherence despite spelling errors in both. |
| HUGO_JOHANSSON | essay_b (HUGO) | 4.0 | Better organization, clearer structure, fewer errors. Addresses assignment comprehensively despite spelling issues. |
| ELIN_ROS_N | essay_a (ELIN) | 4.0 | Essay A: clearer structure, fewer errors, better coherence. Essay B: numerous spelling/grammar mistakes, weaker organization. |
| ANCHOR_6 (C+) | essay_b (ANCHOR_6) | 4.0 | Better structure, more comprehensive content coverage, stronger examples despite spelling errors. |
| LINNEA_WALFRIDSON | essay_a (LINNEA) | 3.5 | Better content coherence, richer discussion of role models' impact, and stronger thematic development despite similar spelling errors. |
| INGER_ISFELDT | essay_a (INGER) | 4.0 | Essay A better addresses assignment requirements with stronger examples, deeper analysis of role model influence, and more sophisticated argumentation despite both having spelling errors. |
| ANCHOR_1 (F+) | essay_b (ANCHOR_3) | 4.0 | Essay B better addresses assignment requirements with specific examples, clearer structure, and broader perspective despite similar error frequency. |
| JULIA_POST | essay_a (JULIA_POST) | 3.5 | Essay A better addresses assignment requirements despite spelling errors. Stronger content development, clearer structure, more comprehensive exploration of role model influence and responsibilities. |
| EDITH_STRANDLER | essay_a (EDITH) | 4.0 | Essay A demonstrates superior content coherence, richer examples, better language fluency, and fewer errors despite minor spelling mistakes. |

**Summary:** ANCHOR_3 (C-): 4 wins, 12 losses (25% win rate)

---

## ANCHOR_9 (D+) Raw Comparison Data

| Opponent | Winner | Confidence | Justification |
|----------|--------|------------|---------------|
| ANCHOR_7 (E-) | essay_b (ANCHOR_9) | 4.0 | Essay B better addresses assignment requirements: discusses multiple role model types, explores influence on values/attitudes, considers responsibilities, introduces specific role model with reasoning, and reflects on societal impact. Essay A lacks breadth and structure. |
| ANCHOR_2 (B) | essay_a (ANCHOR_2) | 4.0 | Essay A demonstrates superior coherence, richer examples, and better structure. Essay B has more errors and weaker development. |
| ANCHOR_4 (F+) | essay_b (ANCHOR_9) | 4.0 | Better structure, coherence, and language control despite errors. Addresses more assignment points systematically. |
| ANCHOR_10 (A) | essay_a (ANCHOR_10) | 4.0 | Better coherence, structure, and examples. Fewer errors. More polished expression. |
| ELIN_ROS_N | essay_b (ELIN) | 4.0 | Better structure, clarity, fewer errors, stronger language fluency, and more coherent organization. |
| HUGO_JOHANSSON | essay_b (HUGO) | 4.0 | Better structure, clearer organization, more comprehensive coverage of assignment prompts, superior vocabulary range despite spelling errors. |
| ANCHOR_11 (E+) | essay_a (ANCHOR_9) | 3.5 | Essay A better addresses assignment requirements with clearer structure, more developed discussion of role model responsibilities, and stronger coherence despite language errors. |
| ANCHOR_3 (C-) | essay_a (ANCHOR_3) | 3.0 | Essay A has better structure, more concrete examples, and clearer coherence despite spelling errors in both. |
| ANCHOR_8 (D-) | essay_b (ANCHOR_9) | 3.5 | Essay B addresses assignment requirements more systematically with clearer structure, better explores role model responsibilities, and demonstrates stronger argumentation despite similar spelling errors. |
| ANCHOR_1 (F+) | essay_b (ANCHOR_9) | 4.0 | Essay B better addresses assignment prompts with clearer structure, more diverse examples, and stronger language despite errors. |
| SOFIA_ANDERSSON | essay_a (ANCHOR_9) | 3.0 | Better coherence, clearer structure, more focused argument despite similar language errors. |
| JOEL_FALK | essay_a (JOEL) | 3.0 | Essay A better addresses assignment requirements with more detailed personal example and fuller exploration of role model types and responsibilities. |
| ANCHOR_6 (C+) | essay_a (ANCHOR_6) | 3.5 | Essay A addresses more assignment points with better examples and clearer personal reflection despite language errors. |
| ANCHOR_5 (B) | essay_a (ANCHOR_5) | 4.0 | Essay A demonstrates superior structure, coherence, and language accuracy with better vocabulary and fewer errors throughout. |
| ELIAS_KUHLIN | essay_a (ELIAS) | 4.0 | Better structure, more comprehensive coverage of assignment points, specific personal role model example, despite similar language errors. |
| ANCHOR_12 (A) | essay_b (ANCHOR_12) | 4.0 | Essay B demonstrates superior content coherence, richer vocabulary, better structure, and fewer grammatical errors despite minor mistakes. |

**Summary:** ANCHOR_9 (D+): 6 wins, 10 losses (37.5% win rate)

---

## ANCHOR_7 (E-) Raw Comparison Data

| Opponent | Winner | Confidence | Justification |
|----------|--------|------------|---------------|
| ANCHOR_9 (D+) | essay_b (ANCHOR_9) | 4.0 | Essay B better addresses assignment requirements... |
| HUGO_JOHANSSON | essay_a (HUGO) | 4.0 | Essay A better addresses assignment requirements with structured discussion of role models, examples, and personal reflection despite spelling errors. |
| ANCHOR_1 (F+) | essay_b (ANCHOR_1) | 3.5 | Better structure, addresses more rubric points, discusses role model influence despite language errors. |
| ANCHOR_2 (B) | essay_a (ANCHOR_2) | 4.0 | Essay A better addresses assignment requirements with broader scope, coherence, and fewer errors despite minor issues. |
| ANCHOR_11 (E+) | essay_a (ANCHOR_11) | 4.0 | Essay A addresses more assignment requirements, discusses role models' societal impact, provides specific examples, and offers coherent analysis despite language errors. |
| JULIA_AXELSSON | essay_b (JULIA_A) | 5.0 | Essay B demonstrates superior content depth, language accuracy, coherence, and sophisticated analysis of role models. |
| ANCHOR_4 (F+) | essay_a (ANCHOR_4) | 3.5 | Essay A better addresses assignment requirements: introduces specific role model (Leila), discusses influence on values, explores societal impact. Essay B lacks depth on role model influence and societal contribution. |
| INGER_ISFELDT | essay_a (INGER) | 4.5 | Essay A better addresses assignment requirements with structured analysis, diverse examples, and coherent argumentation despite spelling errors. |
| ANCHOR_8 (D-) | essay_a (ANCHOR_8) | 4.0 | Essay A better addresses assignment requirements with diverse role models, richer content, and more comprehensive exploration of influence and personal connection. |
| JOEL_FALK | essay_a (JOEL) | 4.0 | Essay A better addresses assignment requirements with broader scope on role models and specific personal example. |
| EDITH_STRANDLER | essay_a (EDITH) | 5.0 | Essay A meets word count, addresses all prompts with coherent structure, personal examples, and reflection. Essay B falls significantly short in length, language accuracy, and content depth. |
| ANCHOR_6 (C+) | essay_b (ANCHOR_6) | 4.0 | Essay B better addresses assignment requirements with broader scope, multiple role models, and stronger thematic development despite language errors. |
| JULIA_POST | essay_b (JULIA_POST) | 4.0 | Essay B better addresses assignment requirements with broader scope, more developed ideas, and stronger structure despite language errors. |
| SOFIA_ANDERSSON | essay_b (SOFIA) | 4.0 | Essay B meets word count (671 vs ~280), addresses more assignment points comprehensively, and demonstrates superior content depth despite language errors. |
| ANCHOR_5 (B) | essay_a (ANCHOR_5) | 4.0 | Essay A better addresses assignment requirements with coherent structure, specific examples, and minimal errors despite minor issues. |
| ELIAS_KUHLIN | essay_b (ELIAS) | 4.0 | Essay B demonstrates superior content organization, vocabulary range, and engagement with assignment prompts despite minor errors. |
| LINNEA_WALFRIDSON | essay_a (LINNEA) | 4.0 | Essay A better addresses assignment scope with personal and general role model analysis. |

**Summary:** ANCHOR_7 (E-): 0 wins, 17 losses (0% win rate)

**Critical observation:** ANCHOR_7 lost ALL 17 comparisons, including against both F+ anchors. This strongly suggests the anchor essay itself may be misgraded or has significant quality issues.

---

## TUVA_KARLSSON Comparison Data (Reference Item Anomaly)

| Opponent | Winner | Confidence |
|----------|--------|------------|
| SADEY_NILZ_N | TUVA | 3.5 |
| SOFIA_ANDERSSON | TUVA | 4.0 |
| INGER_ISFELDT | INGER | 4.0 |
| ANCHOR_5 (B) | ANCHOR_5 | 4.0 |
| ANCHOR_12 (A) | ANCHOR_12 | 4.0 |
| JULIA_POST | TUVA | 4.0 |
| ANCHOR_10 (A) | TUVA | 4.0 |
| ELIAS_KUHLIN | ELIAS | 3.5 |
| JULIA_AXELSSON | JULIA_A | 4.0 |
| LINNEA_WALFRIDSON | TUVA | 3.0 |
| ANCHOR_2 (B) | ANCHOR_2 | 4.0 |
| ANCHOR_6 (C+) | TUVA | 4.0 |
| ANCHOR_4 (F+) | TUVA | 4.5 |
| ELIN_ROS_N | TUVA | 4.0 |
| ANCHOR_8 (D-) | TUVA | 4.0 |
| ANCHOR_11 (E+) | TUVA | 4.0 |
| ANCHOR_1 (F+) | TUVA | 4.0 |

**Summary:** TUVA_KARLSSON: 11 wins, 6 losses (64.7% win rate)

**Issue:** SE = 0 because TUVA is used as BT reference (last item in sorted array).

---

## Anchor Grade Scale Reference

| Anchor Label | Grade | Els Essay ID |
|--------------|-------|--------------|
| anchor_essay_eng_5_17_vt_012_A | A | ANCHOR_12_c4dd6d9e |
| anchor_essay_eng_5_17_vt_011_A | A | ANCHOR_10_3e7b0acc |
| anchor_essay_eng_5_17_vt_010_B | B | ANCHOR_2_2d2a7021 |
| anchor_essay_eng_5_17_vt_009_B | B | ANCHOR_5_33226de9 |
| anchor_essay_eng_5_17_vt_008_C+ | C+ | ANCHOR_6_239581c0 |
| anchor_essay_eng_5_17_vt_007_C- | C- | ANCHOR_3_78552934 |
| anchor_essay_eng_5_17_vt_006_D+ | D+ | ANCHOR_9_c63d675c |
| anchor_essay_eng_5_17_vt_005_D- | D- | ANCHOR_8_c875b810 |
| anchor_essay_eng_5_17_vt_004_E+ | E+ | ANCHOR_11_497c210e |
| anchor_essay_eng_5_17_vt_003_E- | E- | ANCHOR_7_d6319ec2 |
| anchor_essay_eng_5_17_vt_002_F+ | F+ | ANCHOR_4_9a192186 |
| anchor_essay_eng_5_17_vt_001_F+ | F+ | ANCHOR_1_8daeded7 |

---

## Student Grade Projections

| Essay ID | Projected Grade | Confidence |
|----------|-----------------|------------|
| INGER_ISFELDT | A | HIGH |
| EDITH_STRANDLER | A | HIGH |
| JULIA_AXELSSON | A | HIGH |
| TUVA_KARLSSON | B | HIGH |
| ELIAS_KUHLIN | B | HIGH |
| SADEY_NILZ_N | B | HIGH |
| JULIA_POST | C+ | HIGH |
| ELIN_ROS_N | C+ | HIGH |
| LINNEA_WALFRIDSON | C+ | HIGH |
| JOEL_FALK | C- | HIGH |
| SOFIA_ANDERSSON | D- | HIGH |
| HUGO_JOHANSSON | E+ | HIGH |

---

## Recommendations

### Immediate Action Required
1. Fix SE = 0 bug by ensuring anchors are always selected as BT reference

### Investigation Required
1. Review ANCHOR_7 (E-) essay content - 0/17 wins is anomalous
2. Review comparison prompt for grade-relevant weighting
3. Consider whether lower grades (D, E, F) have distinguishing characteristics the LLM can identify

### Quality Monitoring
1. Add anchor monotonicity check to batch validation
2. Log inversions count in `bt_se_summary` metadata
