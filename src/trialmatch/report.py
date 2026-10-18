from __future__ import annotations

from typing import List

from .models import MatchResult, Patient

ICON = {"met": "[x]", "not_met": "[ ] NOT MET", "unknown": "[?]"}
LABEL = {"likely_eligible": "Likely eligible", "needs_review": "Needs review", "ineligible": "Ineligible"}


def to_markdown(patient: Patient, results: List[MatchResult]) -> str:
    out = [f"# Trial matches for {patient.id}", "",
           f"{len(results)} trials screened: " + ", ".join(
               f"{sum(r.verdict == v for r in results)} {LABEL[v].lower()}" for v in LABEL), ""]
    for r in results:
        out += [f"## {LABEL[r.verdict]}: {r.trial.nct_id} {r.trial.title}", ""]
        out += [f"- {x}" for x in r.reasons]
        if r.results:
            out += ["", "| | Criterion | Detail |", "|---|---|---|"]
            for c in r.results:
                out.append(f"| {ICON[c.status]} | ({c.criterion.kind[:3]}) {c.criterion.text} | {c.detail} |")
        out.append("")
    out.append("_Screening aid only. Final eligibility is determined by the study team._")
    return "\n".join(out)
