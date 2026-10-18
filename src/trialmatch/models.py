from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Patient:
    id: str
    age: int
    sex: str  # "female" | "male"
    conditions: List[str] = field(default_factory=list)  # active and past diagnoses, free text
    labs: Dict[str, float] = field(default_factory=dict)  # see criteria.LAB_UNITS for names and units
    ecog: Optional[int] = None
    pregnant: Optional[bool] = None
    medications: List[str] = field(default_factory=list)


@dataclass
class Trial:
    nct_id: str
    title: str
    conditions: List[str]
    eligibility_text: str
    min_age: Optional[float] = None  # years
    max_age: Optional[float] = None
    sex: str = "ALL"  # ALL | FEMALE | MALE
    status: str = "RECRUITING"
    locations: List[str] = field(default_factory=list)


@dataclass
class Criterion:
    text: str
    kind: str  # inclusion | exclusion
    type: str = "unparsed"  # lab | ecog | condition | pregnancy | unparsed
    lab: Optional[str] = None
    low: Optional[float] = None  # inclusive bounds
    high: Optional[float] = None
    condition_terms: List[str] = field(default_factory=list)


@dataclass
class CriterionResult:
    criterion: Criterion
    status: str  # met | not_met | unknown
    detail: str


@dataclass
class MatchResult:
    trial: Trial
    verdict: str  # eligible | needs_review | ineligible
    reasons: List[str]
    results: List[CriterionResult]

    @property
    def unknown_count(self) -> int:
        return sum(r.status == "unknown" for r in self.results)

    def to_dict(self) -> dict:
        return {"nct_id": self.trial.nct_id, "title": self.trial.title, "verdict": self.verdict,
                "reasons": self.reasons,
                "criteria": [{"kind": r.criterion.kind, "text": r.criterion.text, "type": r.criterion.type,
                              "status": r.status, "detail": r.detail} for r in self.results]}
