"""Match one patient against trials: hard filters, then criterion-by-criterion evaluation.

Verdicts
  ineligible       a hard filter or any criterion is not met
  needs_review     an inclusion criterion could not be checked because patient data is missing
  likely_eligible  nothing blocks; remaining unparsed criteria are listed for the coordinator
"""
from __future__ import annotations

from typing import List, Optional

from .criteria import condition_present, evaluate, keyword_terms, parse_llm, parse_rules, split_criteria
from .models import CriterionResult, MatchResult, Patient, Trial

ORDER = {"likely_eligible": 0, "needs_review": 1, "ineligible": 2}


def parse_trial(trial: Trial, client=None):
    crits = split_criteria(trial.eligibility_text)
    return parse_llm(crits, client) if client is not None else [parse_rules(c) for c in crits]


def match(patient: Patient, trial: Trial, client=None) -> MatchResult:
    reasons: List[str] = []
    if trial.status not in ("RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"):
        reasons.append(f"Trial status is {trial.status}")
    if trial.min_age is not None and patient.age < trial.min_age:
        reasons.append(f"Age {patient.age} below minimum {trial.min_age:g}")
    if trial.max_age is not None and patient.age > trial.max_age:
        reasons.append(f"Age {patient.age} above maximum {trial.max_age:g}")
    if trial.sex.upper() in ("FEMALE", "MALE") and patient.sex.upper() != trial.sex.upper():
        reasons.append(f"Trial enrolls {trial.sex.lower()} participants only")
    if trial.conditions and not any(condition_present(keyword_terms(c), patient) for c in trial.conditions):
        reasons.append(f"Trial condition ({'; '.join(trial.conditions)}) not among the patient's diagnoses")
    if reasons:
        return MatchResult(trial, "ineligible", reasons, [])

    results: List[CriterionResult] = [evaluate(c, patient) for c in parse_trial(trial, client)]
    blocking = [r for r in results if r.status == "not_met"]
    missing = [r for r in results if r.status == "unknown" and r.criterion.kind == "inclusion"
               and r.criterion.type != "unparsed"]
    if blocking:
        verdict = "ineligible"
        reasons = [f"{r.criterion.kind.capitalize()} not satisfied: {r.criterion.text} ({r.detail})" for r in blocking]
    elif missing:
        verdict = "needs_review"
        reasons = [f"Missing data for: {r.criterion.text} ({r.detail})" for r in missing]
    else:
        verdict = "likely_eligible"
        n = sum(r.status == "unknown" for r in results)
        reasons = [f"No blocking criteria; {n} criteria need coordinator review."]
    return MatchResult(trial, verdict, reasons, results)


def rank(patient: Patient, trials: List[Trial], client: Optional[object] = None) -> List[MatchResult]:
    res = [match(patient, t, client) for t in trials]
    return sorted(res, key=lambda r: (ORDER[r.verdict], r.unknown_count, r.trial.nct_id))
