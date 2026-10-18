# Changelog

## 1.0.0

Consolidates five earlier prototypes into the `trialmatch` package.

- ClinicalTrials.gov API v2 client; request failures raise instead of falling back to mock trials
- Hard filters: recruitment status, age, sex, primary condition
- Criteria parsing into structured predicates (lab ranges with unit normalization, ECOG, pregnancy, conditions);
  ULN-relative thresholds left for review
- Optional LLM criteria parser whose thresholds must appear verbatim in the criterion text
- Three-valued evaluation (met / not met / unknown) and three verdicts (likely eligible / needs review / ineligible)
- Evaluation: 30 synthetic patient-trial pairs, 24 development and 16 held-out criteria; unsafe errors fail CI
- GitHub Actions on Python 3.9-3.13, ruff, Dockerfile; opt-in live API smoke test
