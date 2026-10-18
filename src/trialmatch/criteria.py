"""Eligibility criteria: split, parse into structured predicates, evaluate.

Free-text criteria are the hard part of trial matching. Two parsers produce the
same `Criterion` structure:

* `parse_rules` - regex patterns for the most common structured criteria
  (lab thresholds, ECOG, pregnancy) and keyword extraction for conditions.
* `parse_llm` - asks a model to classify each criterion and extract thresholds.
  The model must return the criterion index it is describing, and numeric values
  must literally appear in that criterion's text; otherwise the criterion stays
  "unparsed" and is routed to human review instead of being guessed.

Evaluation against a patient is deterministic and three-valued (met, not_met,
unknown). Unknown never silently becomes met or not_met.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

from .llm import parse_json
from .models import Criterion, CriterionResult, Patient

# Canonical lab names, patient units, and synonyms seen in criteria text.
LAB_UNITS: Dict[str, str] = {
    "hba1c": "%", "egfr": "mL/min/1.73m2", "creatinine": "mg/dL", "anc": "x10^9/L",
    "platelets": "x10^9/L", "hemoglobin": "g/dL", "alt": "U/L", "ast": "U/L", "bilirubin": "mg/dL",
    "bmi": "kg/m2", "ldl": "mg/dL", "lvef": "%",
}
LAB_SYNONYMS: List[Tuple[str, str]] = [
    (r"hb ?a1c|hemoglobin a1c|glycated hemoglobin|a1c", "hba1c"),
    (r"egfr|estimated glomerular filtration rate|creatinine clearance|crcl", "egfr"),
    (r"absolute neutrophil count|\banc\b", "anc"),
    (r"platelets?(?: count)?", "platelets"),
    (r"(?<!glycated )hemoglobin(?! a1c)|\bhgb\b", "hemoglobin"),
    (r"\balt\b|alanine aminotransferase", "alt"),
    (r"\bast\b|aspartate aminotransferase", "ast"),
    (r"total bilirubin|bilirubin", "bilirubin"),
    (r"serum creatinine|creatinine", "creatinine"),
    (r"body mass index|\bbmi\b", "bmi"),
    (r"ldl(?:-c| cholesterol)?", "ldl"),
    (r"lvef|left ventricular ejection fraction|ejection fraction", "lvef"),
]
NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
GE = r"(?:>=|≥|greater than or equal to|at least|of at least|no less than|>)"
LE = r"(?:<=|≤|less than or equal to|at most|no more than|not exceeding|<)"
UNPARSED_HINTS = re.compile(r"consent|life expectancy|investigator|judge?ment|willing|comply|compliance|"
                            r"blood pressure|heart rate|participat")
STOPWORDS = {"currently", "history", "diagnosis", "patients", "patient", "with", "known", "active", "prior", "current",
             "documented", "confirmed", "of", "or", "and", "the", "a", "an", "any", "who", "have", "has",
             "must", "be", "is", "are", "within", "years", "months", "disease", "participants", "subjects"}


def split_criteria(text: str) -> List[Criterion]:
    """Split ClinicalTrials.gov eligibility text into inclusion and exclusion items."""
    kind = "inclusion"
    out: List[Criterion] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower().rstrip(":")
        if low.startswith("inclusion criteria"):
            kind = "inclusion"
            continue
        if low.startswith("exclusion criteria"):
            kind = "exclusion"
            continue
        item = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if item:
            out.append(Criterion(text=item, kind=kind))
    return out


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _normalize(lab: str, value: float) -> float:
    """Convert criteria units to patient units (cells/mm3 -> x10^9/L)."""
    if lab in ("platelets", "anc") and value > 1000:
        return value / 1000.0
    if lab == "anc" and value >= 100:  # e.g. 1500/uL
        return value / 1000.0
    return value


def _lab_name(text: str) -> Optional[str]:
    low = text.lower()
    for pat, name in LAB_SYNONYMS:
        if re.search(pat, low):
            return name
    return None


def keyword_terms(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())
            if w not in STOPWORDS and (len(w) > 2 or w.isdigit())]


def parse_rules(c: Criterion) -> Criterion:
    t = c.text
    low = t.lower()
    if re.search(r"\becog\b|performance status", low):
        rng = re.search(r"(\d)\s*(?:-|to|–)\s*(\d)", low)
        le = re.search(rf"{LE}\s*(\d)", low)
        if rng:
            c.type, c.low, c.high = "ecog", float(rng.group(1)), float(rng.group(2))
        elif le:
            c.type, c.low, c.high = "ecog", 0.0, float(le.group(1))
        return c
    if UNPARSED_HINTS.search(low):
        return c
    if re.search(r"pregnan|breast[- ]?feeding|lactating|childbearing|contracepti", low):
        c.type = "pregnancy"
        return c
    lab = _lab_name(low)
    if lab:
        between = re.search(rf"between\s+{NUM}\s*%?\s*(?:and|-|to)\s*{NUM}", low)
        ge = re.search(rf"{GE}\s*{NUM}", low)
        le = re.search(rf"{LE}\s*{NUM}", low)
        if between:
            c.low, c.high = _to_float(between.group(1)), _to_float(between.group(2))
        else:
            if ge:
                c.low = _to_float(ge.group(1))
            if le:
                c.high = _to_float(le.group(1))
        if re.search(r"(?:x|×|times)\s*(?:the\s*)?(?:upper limit of normal|uln)\b", low):
            # Relative to ULN: cannot evaluate without the lab's own reference range.
            c.low = c.high = None
            return c
        if c.low is not None or c.high is not None:
            c.type, c.lab = "lab", lab
            if c.low is not None:
                c.low = _normalize(lab, c.low)
            if c.high is not None:
                c.high = _normalize(lab, c.high)
            return c
    # Condition criteria: keep salient words for matching against the patient's diagnoses.
    terms = keyword_terms(low)
    if terms:
        c.type, c.condition_terms = "condition", terms
    return c


LLM_SYSTEM = """You convert clinical trial eligibility criteria into structured predicates.
You get a numbered list. Return ONLY a JSON array with one object per criterion:
{"index": int, "type": "lab"|"ecog"|"pregnancy"|"condition"|"unparsed",
 "lab": one of [""" + ", ".join(LAB_UNITS) + """] or null,
 "low": number|null, "high": number|null,   // inclusive bounds, numbers exactly as written in the criterion
 "condition_terms": [str]}                   // for type=condition: 1-4 key clinical terms, e.g. ["type 2 diabetes"]
Use "unparsed" for anything else (procedures, consent, time windows, ULN-relative labs, investigator judgment)."""


def parse_llm(criteria: List[Criterion], client) -> List[Criterion]:
    listing = "\n".join(f"{i}. [{c.kind}] {c.text}" for i, c in enumerate(criteria))
    items = parse_json(client.complete(LLM_SYSTEM, listing), list)
    by_index = {it.get("index"): it for it in items if isinstance(it, dict)}
    out = []
    for i, c in enumerate(criteria):
        it = by_index.get(i)
        nc = Criterion(text=c.text, kind=c.kind)
        if it and it.get("type") in ("lab", "ecog", "pregnancy", "condition"):
            nums_in_text = {_to_float(n) for n in re.findall(NUM, c.text)}
            bounds = [b for b in (it.get("low"), it.get("high")) if b is not None]
            grounded = all(isinstance(b, (int, float)) and float(b) in nums_in_text for b in bounds)
            if it["type"] == "lab" and (it.get("lab") not in LAB_UNITS or not bounds):
                grounded = False
            if grounded:
                nc.type = it["type"]
                nc.lab = it.get("lab")
                nc.low = None if it.get("low") is None else float(it["low"])
                nc.high = None if it.get("high") is None else float(it["high"])
                if nc.lab:
                    nc.low = None if nc.low is None else _normalize(nc.lab, nc.low)
                    nc.high = None if nc.high is None else _normalize(nc.lab, nc.high)
                if nc.type == "ecog" and nc.low is None and nc.high is not None:
                    nc.low = 0.0
                nc.condition_terms = [str(x).lower() for x in it.get("condition_terms") or []]
        out.append(nc)
    return out


def condition_present(terms: List[str], patient: Patient) -> Optional[bool]:
    """True if a patient diagnosis matches the criterion's terms; None when we cannot tell.

    Multi-word terms (from the LLM) must appear as phrases in one diagnosis. Keyword terms
    (from the regex parser) must match every number (so "type 1" never matches "type 2")
    and at least two thirds of the words, within a single diagnosis.
    """
    if not terms:
        return None
    for dx in (d.lower() for d in patient.conditions):
        phrases = [t for t in terms if " " in t]
        if phrases:
            if any(ph in dx for ph in phrases):
                return True
            continue
        nums = [t for t in terms if t.isdigit()]
        words = [t for t in terms if not t.isdigit()]
        if any(not re.search(rf"\b{n}\b", dx) for n in nums):
            continue
        hits = [w for w in words if re.search(rf"\b{re.escape(w)}", dx)]
        if words and len(hits) >= max(1, math.ceil(len(words) * 2 / 3)):
            return True
    return None


def evaluate(c: Criterion, p: Patient) -> CriterionResult:
    if c.type == "lab":
        v = p.labs.get(c.lab)
        if v is None:
            return CriterionResult(c, "unknown", f"{c.lab} not available")
        ok = (c.low is None or v >= c.low) and (c.high is None or v <= c.high)
        rng = f"[{'' if c.low is None else f'{c.low:g}'}, {'' if c.high is None else f'{c.high:g}'}]"
        ok_inclusion = ok if c.kind == "inclusion" else not ok
        # For exclusion criteria the stated range describes who is EXCLUDED.
        return CriterionResult(c, "met" if ok_inclusion else "not_met", f"{c.lab} {v:g} vs {rng}")
    if c.type == "ecog":
        if p.ecog is None:
            return CriterionResult(c, "unknown", "ECOG not documented")
        ok = c.low <= p.ecog <= c.high
        ok_inclusion = ok if c.kind == "inclusion" else not ok
        return CriterionResult(c, "met" if ok_inclusion else "not_met", f"ECOG {p.ecog}")
    if c.type == "pregnancy":
        if p.sex == "male":
            return CriterionResult(c, "met", "not applicable (male)")
        if p.pregnant is None:
            return CriterionResult(c, "unknown", "pregnancy status not documented")
        if c.kind == "exclusion":
            return CriterionResult(c, "not_met" if p.pregnant else "met", f"pregnant={p.pregnant}")
        return CriterionResult(c, "met" if p.pregnant else "not_met", f"pregnant={p.pregnant}")
    if c.type == "condition":
        present = condition_present(c.condition_terms, p)
        if present is None:
            if c.kind == "exclusion":
                return CriterionResult(c, "met", "no matching diagnosis in the record (verify)")
            return CriterionResult(c, "unknown", "could not confirm from diagnoses")
        if c.kind == "inclusion":
            return CriterionResult(c, "met", "matching diagnosis")
        return CriterionResult(c, "not_met", "patient has an excluding diagnosis")
    return CriterionResult(c, "unknown", "requires human review")
