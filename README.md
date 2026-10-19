# trial-match-agent

[![CI](https://github.com/ai-summer2025/trial-match-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ai-summer2025/trial-match-agent/actions/workflows/ci.yml)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Clinical trial pre-screening. Pulls recruiting trials from the ClinicalTrials.gov API v2, turns each free-text eligibility criterion into a structured predicate, and checks it against a patient record with three-valued logic: **met**, **not met**, or **unknown**. Each trial gets a verdict with the criterion-by-criterion reasoning behind it.

> **Screening aid only.** Final eligibility is determined by the study team. All bundled patients and trials are synthetic.

## How it works

```
 ClinicalTrials.gov v2 ──► hard filters ──► split criteria ──► parse each criterion ──► evaluate vs patient ──► verdict
 (or a JSON file)          status, age,     inclusion /       regex baseline, or       met / not_met /        + reasons,
                           sex, condition   exclusion         LLM with checks          unknown                 ranked
```

**Verdicts**

| Verdict | Meaning |
|---|---|
| `likely_eligible` | Nothing blocks. Criteria the tool cannot evaluate (consent, investigator judgment) are listed for the coordinator. |
| `needs_review` | An inclusion criterion could not be checked because the patient record lacks the data (e.g. no HbA1c). |
| `ineligible` | A hard filter failed or a criterion is clearly not met, with the reason. |

**Design choices**

- **Unknown is a first-class answer.** A missing lab never silently passes or fails; it produces `needs_review` and names the missing value.
- **The LLM parses criteria; it does not decide eligibility.** Its output is checked: every threshold it returns must literally appear in that criterion's text, and lab names must be from a fixed vocabulary. Anything that fails the check stays `unparsed` and goes to human review.
- **Exclusion logic is explicit.** For an exclusion like "Hemoglobin < 8 g/dL" the range describes who is excluded; for exclusion diagnoses, absence from the record is reported as "verify", not as a confirmed negative.
- **Units are normalized** (e.g. "≥ 100,000/mm³" platelets → 100 x10⁹/L), and ULN-relative thresholds ("> 3 x ULN") are left for review rather than guessed.
- **API errors propagate.** A failed ClinicalTrials.gov request is an error, never an empty result or placeholder data.

## Quickstart

```bash
pip install -e .
trialmatch match data/patients/P2.json --trials data/trials/synthetic_trials.json
trialmatch match data/patients/P2.json --search "heart failure" --max 20        # live ClinicalTrials.gov
trialmatch match data/patients/P2.json --search "heart failure" --llm           # LLM criteria parsing
docker build -t trialmatch . && docker run --rm trialmatch
```

Example (abridged):

```
## Likely eligible: SYNTH0002 Synthetic outcomes study in heart failure with reduced ejection fraction
| [x] | (inc) LVEF ≤ 40%                                         | lvef 30 vs [, 40]     |
| [x] | (inc) eGFR ≥ 30 mL/min/1.73m2                            | egfr 38 vs [30, ]     |
| [?] | (exc) Systolic blood pressure < 90 mmHg at screening     | requires human review |
```

LLM configuration: `ANTHROPIC_API_KEY=...`, or `LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=llama3.1` for a local model. No SDK dependencies.

## Evaluation

`python eval/run_eval.py` regenerates [`eval/RESULTS.md`](eval/RESULTS.md); CI fails on regression, including any **unsafe** error (calling an ineligible patient eligible, or eligible when data is missing).

| Criteria parser | Verdict accuracy (30 pairs) | Unsafe errors | Parse accuracy, dev set (24) | Parse accuracy, held-out (16) |
|---|---|---|---|---|
| Regex baseline | 1.00 | 0 | 1.00 | **0.75** |
| LLM + checks | run `python eval/run_eval.py --llm` | | | |

The held-out number is the honest one. The development criteria and the 5 x 6 patient-trial matrix were used while writing the regex parser, so they measure regressions, not generalization. The held-out criteria were written afterwards and never tuned on; the regex parser misses phrasings like "6.5% to 9.0%", "35% or less" and "ECOG 0, 1 or 2". Those are the cases the LLM parser is for. The LLM row is left for you to run with your own credentials.

The live API client is tested against fixtures in the API's record format; `TRIALMATCH_LIVE=1 pytest tests/test_live_api.py` runs a smoke test against the real service.

## Limitations

- Patient data is a flat record (diagnoses, a fixed set of labs, ECOG, pregnancy). Medications, procedures, biomarkers and time windows ("within 6 months") are routed to review.
- Condition matching uses keywords or LLM-extracted phrases, not a terminology (SNOMED CT / ICD-10).
- Synthetic evaluation only; no comparison with coordinator screening decisions.

## Roadmap

- FHIR R4 patient input (`Condition`, `Observation`, `MedicationStatement`) and SNOMED/ICD-10 condition matching
- Time-window criteria and medication-based criteria
- Evaluation against real trial criteria with coordinator-labeled eligibility (e.g. public TREC Clinical Trials track topics)

## Project history

Consolidates five earlier prototypes (`clinical-trial-match-agent`, `clinical-trial-matcher-agent`, `clinical-trial-screener`, `clinical-trial-scout`, `multiagent-trial-screener`). One notable fix: the earlier `clinical-trial-match-agent` silently replaced a failed API call with built-in mock trials whose IDs looked like real NCT numbers, so a network error could show patients trials that do not exist. See [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
