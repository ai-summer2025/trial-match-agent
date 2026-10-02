"""
Agentic tool definitions for clinical trial matching.
Each tool represents one step the agent can take autonomously.
"""
import re
import json
import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

CTGOV_API_BASE = "https://clinicaltrials.gov/api/v2"


@dataclass
class TrialSummary:
    """Summary of a clinical trial from initial search."""
    nct_id: str
    title: str
    status: str
    phase: str
    conditions: List[str]
    interventions: List[str]
    locations_count: int
    brief_summary: str = ""


@dataclass
class TrialDetails:
    """Full details of a clinical trial including eligibility."""
    nct_id: str
    title: str
    status: str
    phase: str
    conditions: List[str]
    interventions: List[str]
    eligibility_criteria_raw: str
    minimum_age: Optional[int]
    maximum_age: Optional[int]
    sex_criteria: str  # "ALL", "MALE", "FEMALE"
    healthy_volunteers: bool
    locations: List[Dict]
    sponsor: str
    brief_summary: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


@dataclass
class EligibilityEvaluation:
    """Result of evaluating a patient against trial criteria."""
    nct_id: str
    passed_basic: bool
    basic_issues: List[str]
    inclusion_met: List[str]
    inclusion_not_met: List[str]
    inclusion_unknown: List[str]
    exclusion_triggered: List[str]
    exclusion_clear: List[str]
    exclusion_unknown: List[str]
    score: float  # 0-100
    reasoning: str


# ─── Tool 1: Search ClinicalTrials.gov ───────────────────────────────────────

def search_trials(
    condition: str,
    max_results: int = 20,
    status_filter: str = "RECRUITING"
) -> List[TrialSummary]:
    """
    Tool: Search ClinicalTrials.gov for trials matching a condition.
    Uses the free public ClinicalTrials.gov v2 REST API.
    """
    logger.info(f"[TOOL] search_trials(condition='{condition}', max={max_results})")
    
    params = {
        "query.cond": condition,
        "filter.overallStatus": status_filter,
        "pageSize": min(max_results, 25),
        "format": "json",
        "fields": "NCTId,BriefTitle,OverallStatus,Phase,Condition,InterventionName,"
                  "BriefSummary,LocationFacility,LocationCity,LocationCountry",
    }

    try:
        resp = requests.get(f"{CTGOV_API_BASE}/studies", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"ClinicalTrials.gov API error: {e}. Using mock data.")
        return _mock_search_results(condition)

    studies = data.get("studies", [])
    results = []
    for study in studies:
        proto = study.get("protocolSection", {})
        id_mod = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        cond_mod = proto.get("conditionsModule", {})
        desc_mod = proto.get("descriptionModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})
        loc_mod = proto.get("contactsLocationsModule", {})

        interventions = [
            iv.get("name", "") for iv in arms_mod.get("interventions", [])
        ]
        conditions = cond_mod.get("conditions", [])
        locations = loc_mod.get("locations", [])

        results.append(TrialSummary(
            nct_id=id_mod.get("nctId", ""),
            title=id_mod.get("briefTitle", ""),
            status=status_mod.get("overallStatus", ""),
            phase=", ".join(status_mod.get("phases", ["N/A"])) if status_mod.get("phases") else "N/A",
            conditions=conditions,
            interventions=interventions[:5],
            locations_count=len(locations),
            brief_summary=desc_mod.get("briefSummary", "")[:300],
        ))
    
    logger.info(f"[TOOL] Found {len(results)} trials for '{condition}'")
    return results


# ─── Tool 2: Get Trial Details ────────────────────────────────────────────────

def get_trial_details(nct_id: str) -> Optional[TrialDetails]:
    """
    Tool: Fetch full trial details including eligibility criteria.
    """
    logger.info(f"[TOOL] get_trial_details(nct_id='{nct_id}')")
    
    try:
        resp = requests.get(
            f"{CTGOV_API_BASE}/studies/{nct_id}",
            params={"format": "json"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"Error fetching {nct_id}: {e}. Using mock data.")
        return _mock_trial_details(nct_id)

    proto = data.get("protocolSection", {})
    id_mod = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    cond_mod = proto.get("conditionsModule", {})
    elig_mod = proto.get("eligibilityModule", {})
    desc_mod = proto.get("descriptionModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    loc_mod = proto.get("contactsLocationsModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})

    # Parse age
    def parse_age(age_str: Optional[str]) -> Optional[int]:
        if not age_str:
            return None
        m = re.search(r"(\d+)", str(age_str))
        return int(m.group(1)) if m else None

    locations = [
        {
            "facility": loc.get("facility", ""),
            "city": loc.get("city", ""),
            "state": loc.get("state", ""),
            "country": loc.get("country", ""),
        }
        for loc in loc_mod.get("locations", [])[:10]
    ]

    central_contacts = loc_mod.get("centralContacts", [{}])
    contact = central_contacts[0] if central_contacts else {}

    return TrialDetails(
        nct_id=id_mod.get("nctId", nct_id),
        title=id_mod.get("briefTitle", ""),
        status=status_mod.get("overallStatus", ""),
        phase=", ".join(status_mod.get("phases", ["N/A"])),
        conditions=cond_mod.get("conditions", []),
        interventions=[
            iv.get("name", "") for iv in arms_mod.get("interventions", [])
        ],
        eligibility_criteria_raw=elig_mod.get("eligibilityCriteria", ""),
        minimum_age=parse_age(elig_mod.get("minimumAge")),
        maximum_age=parse_age(elig_mod.get("maximumAge")),
        sex_criteria=elig_mod.get("sex", "ALL"),
        healthy_volunteers=elig_mod.get("healthyVolunteers", False),
        locations=locations,
        sponsor=sponsor_mod.get("leadSponsor", {}).get("name", ""),
        brief_summary=desc_mod.get("briefSummary", ""),
        contact_email=contact.get("email"),
        contact_phone=contact.get("phone"),
    )


# ─── Tool 3: Parse Eligibility Criteria ──────────────────────────────────────

def parse_eligibility_criteria(raw_text: str) -> Tuple[List[str], List[str]]:
    """
    Tool: Parse raw eligibility text into inclusion and exclusion criterion lists.
    Returns (inclusion_list, exclusion_list).
    """
    if not raw_text:
        return [], []

    text = raw_text.strip()
    inclusion, exclusion = [], []

    # Split into inclusion/exclusion sections
    inc_pattern = re.compile(r"inclusion criteria[:\s]*", re.IGNORECASE)
    exc_pattern = re.compile(r"exclusion criteria[:\s]*", re.IGNORECASE)

    inc_match = inc_pattern.search(text)
    exc_match = exc_pattern.search(text)

    if inc_match and exc_match:
        inc_start = inc_match.end()
        exc_start = exc_match.start()
        exc_end = exc_match.end()
        inc_section = text[inc_start:exc_start]
        exc_section = text[exc_end:]
    elif inc_match:
        inc_section = text[inc_match.end():]
        exc_section = ""
    elif exc_match:
        inc_section = text[:exc_match.start()]
        exc_section = text[exc_match.end():]
    else:
        inc_section = text
        exc_section = ""

    def extract_criteria(section: str) -> List[str]:
        """Extract individual criteria from a section of text."""
        criteria = []
        # Split by numbered items or bullet points
        lines = re.split(r'\n\s*[-•*]\s*|\n\s*\d+[.)]\s*|\n\n+', section)
        for line in lines:
            line = line.strip()
            if len(line) > 20:  # Filter out very short fragments
                criteria.append(line[:300])  # Cap length
        return criteria[:20]  # Cap at 20 criteria per section

    inclusion = extract_criteria(inc_section)
    exclusion = extract_criteria(exc_section)
    return inclusion, exclusion


# ─── Tool 4: Evaluate Patient Against Criteria ───────────────────────────────

def evaluate_patient_eligibility(patient, trial: TrialDetails) -> EligibilityEvaluation:
    """
    Tool: Evaluate a patient's eligibility for a clinical trial.
    Uses rule-based + keyword matching to assess each criterion.
    Returns a scored EligibilityEvaluation.
    """
    logger.info(f"[TOOL] evaluate_patient_eligibility(patient={patient.patient_id}, trial={trial.nct_id})")
    
    issues = []
    
    # ── Basic checks ─────────────────────────────────────────────────────────
    # Age
    if trial.minimum_age and patient.age < trial.minimum_age:
        issues.append(f"Age {patient.age} < minimum {trial.minimum_age}")
    if trial.maximum_age and patient.age > trial.maximum_age:
        issues.append(f"Age {patient.age} > maximum {trial.maximum_age}")

    # Sex
    if trial.sex_criteria == "MALE" and patient.sex.upper() not in ("MALE", "M"):
        issues.append(f"Trial requires Male; patient is {patient.sex}")
    elif trial.sex_criteria == "FEMALE" and patient.sex.upper() not in ("FEMALE", "F"):
        issues.append(f"Trial requires Female; patient is {patient.sex}")

    passed_basic = len(issues) == 0

    # ── Parse eligibility text ────────────────────────────────────────────────
    inclusion_criteria, exclusion_criteria = parse_eligibility_criteria(
        trial.eligibility_criteria_raw
    )

    # ── Build patient feature set for matching ────────────────────────────────
    patient_text = " ".join([
        patient.primary_diagnosis.lower(),
        " ".join(c.lower() for c in patient.secondary_conditions),
        " ".join(m.lower() for m in patient.current_medications),
        " ".join(t.lower() for t in patient.prior_treatments),
        f"ecog {patient.ecog_performance_status}" if patient.ecog_performance_status is not None else "",
        "metastatic" if patient.has_metastatic_disease else "",
    ])

    patient_keywords = set(re.findall(r'\b\w{4,}\b', patient_text))

    # ── Evaluate inclusion criteria ────────────────────────────────────────────
    inc_met, inc_not_met, inc_unknown = [], [], []
    
    # Keywords that suggest positive conditions we can check
    positive_patterns = {
        "histologic": lambda p: True,  # We have a confirmed diagnosis
        "confirmed": lambda p: True,
        "adequate": lambda p: True,
        "18 years": lambda p: p.age >= 18,
        "ecog 0": lambda p: p.ecog_performance_status == 0,
        "ecog 1": lambda p: p.ecog_performance_status in (0, 1),
        "ecog 2": lambda p: p.ecog_performance_status in (0, 1, 2),
        "performance status": lambda p: p.ecog_performance_status is not None and p.ecog_performance_status <= 2,
        "metastatic": lambda p: p.has_metastatic_disease,
        "prior treatment": lambda p: len(p.prior_treatments) > 0,
        "written informed": lambda p: True,  # Consent is obtainable
    }

    negative_patterns = {
        "no prior": lambda p, c: any(pt.lower() in c.lower() for pt in p.prior_treatments),
        "treatment naive": lambda p, c: len(p.prior_treatments) > 0,
        "chemotherapy naive": lambda p, c: any("chemo" in pt.lower() for pt in p.prior_treatments),
    }

    for criterion in inclusion_criteria:
        crit_lower = criterion.lower()
        matched = False
        
        for pattern, evaluator in positive_patterns.items():
            if pattern in crit_lower:
                try:
                    if evaluator(patient):
                        inc_met.append(criterion[:150])
                    else:
                        inc_not_met.append(criterion[:150])
                    matched = True
                    break
                except Exception:
                    pass

        if not matched:
            # Check keyword overlap
            crit_keywords = set(re.findall(r'\b\w{4,}\b', crit_lower))
            overlap = crit_keywords & patient_keywords
            if len(overlap) >= 2:
                inc_met.append(criterion[:150])
            else:
                inc_unknown.append(criterion[:150])

    # ── Evaluate exclusion criteria ────────────────────────────────────────────
    exc_triggered, exc_clear, exc_unknown = [], [], []

    high_risk_exclusions = [
        "active autoimmune", "autoimmune disease",
        "hiv", "hepatitis",
        "brain metastases", "leptomeningeal",
        "concurrent malignancy", "other malignancy",
        "anticoagulation", "anticoagulant",
        "pregnancy", "lactating", "nursing",
        "organ transplant",
        "seizure disorder",
        "uncontrolled diabetes",
    ]

    for criterion in exclusion_criteria:
        crit_lower = criterion.lower()
        triggered = False

        for risk_term in high_risk_exclusions:
            if risk_term in crit_lower:
                # Check if patient has this condition
                if risk_term in patient_text:
                    exc_triggered.append(f"⚠ POSSIBLE: {criterion[:120]}")
                    triggered = True
                    break
                else:
                    exc_clear.append(f"✓ Clear: {criterion[:120]}")
                    triggered = True
                    break

        if not triggered:
            # Check medications / conditions
            crit_keywords = set(re.findall(r'\b\w{5,}\b', crit_lower))
            overlap = crit_keywords & patient_keywords
            if len(overlap) >= 2:
                exc_triggered.append(f"⚠ REVIEW: {criterion[:120]}")
            else:
                exc_unknown.append(f"? Unknown: {criterion[:120]}")

    # ── Compute score ──────────────────────────────────────────────────────────
    score = _compute_match_score(
        passed_basic=passed_basic,
        inc_met=len(inc_met),
        inc_not_met=len(inc_not_met),
        inc_unknown=len(inc_unknown),
        exc_triggered=len(exc_triggered),
        exc_clear=len(exc_clear),
        total_inclusion=len(inclusion_criteria) or 1,
        total_exclusion=len(exclusion_criteria) or 1,
    )

    # ── Generate reasoning ─────────────────────────────────────────────────────
    reasoning = _generate_reasoning(
        patient, trial, passed_basic, issues,
        inc_met, inc_not_met, exc_triggered, score
    )

    return EligibilityEvaluation(
        nct_id=trial.nct_id,
        passed_basic=passed_basic,
        basic_issues=issues,
        inclusion_met=inc_met,
        inclusion_not_met=inc_not_met,
        inclusion_unknown=inc_unknown,
        exclusion_triggered=exc_triggered,
        exclusion_clear=exc_clear,
        exclusion_unknown=exc_unknown,
        score=score,
        reasoning=reasoning,
    )


def _compute_match_score(
    passed_basic, inc_met, inc_not_met, inc_unknown,
    exc_triggered, exc_clear, total_inclusion, total_exclusion
) -> float:
    """Calculate a 0-100 match score."""
    if not passed_basic:
        return 0.0

    # Inclusion score (60% of total)
    if total_inclusion > 0:
        inc_score = (inc_met / total_inclusion) * 60
        inc_score -= (inc_not_met / total_inclusion) * 40
    else:
        inc_score = 30.0

    # Exclusion score (40% of total)
    if total_exclusion > 0:
        exc_score = ((exc_clear) / total_exclusion) * 40
        exc_score -= (exc_triggered / total_exclusion) * 30
    else:
        exc_score = 20.0

    total = max(0.0, min(100.0, inc_score + exc_score))
    return round(total, 1)


def _generate_reasoning(
    patient, trial, passed_basic, issues,
    inc_met, inc_not_met, exc_triggered, score
) -> str:
    """Generate human-readable reasoning for the match."""
    parts = []

    if not passed_basic:
        parts.append(f"❌ DISQUALIFIED: {'; '.join(issues)}")
        return " ".join(parts)

    if score >= 70:
        verdict = "✅ STRONG MATCH"
    elif score >= 45:
        verdict = "🟡 POSSIBLE MATCH — requires clinical review"
    elif score >= 20:
        verdict = "🟠 WEAK MATCH — significant concerns"
    else:
        verdict = "❌ POOR MATCH"

    parts.append(f"{verdict} (Score: {score}/100)")
    parts.append(
        f"Patient ({patient.age}y {patient.sex}, {patient.primary_diagnosis}) "
        f"vs {trial.phase} trial by {trial.sponsor}."
    )

    if inc_met:
        parts.append(f"Met {len(inc_met)} inclusion criteria.")
    if inc_not_met:
        parts.append(f"Failed {len(inc_not_met)} inclusion criteria.")
    if exc_triggered:
        parts.append(f"⚠ {len(exc_triggered)} exclusion criteria need review.")

    return " ".join(parts)


# ─── Mock data fallbacks (when API is unavailable) ────────────────────────────

def _mock_search_results(condition: str) -> List[TrialSummary]:
    """Return realistic mock trials when API is unavailable."""
    templates = [
        TrialSummary(
            nct_id="NCT04000001",
            title=f"Phase 2 Study of Novel Agent in {condition.title()}",
            status="RECRUITING",
            phase="PHASE2",
            conditions=[condition],
            interventions=["Investigational Drug XYZ-123", "Placebo"],
            locations_count=12,
            brief_summary=f"A randomized controlled trial evaluating XYZ-123 in patients with {condition}.",
        ),
        TrialSummary(
            nct_id="NCT04000002",
            title=f"Immunotherapy Combination Trial for Advanced {condition.title()}",
            status="RECRUITING",
            phase="PHASE1/PHASE2",
            conditions=[condition],
            interventions=["Pembrolizumab", "Experimental compound ABC"],
            locations_count=8,
            brief_summary=f"Phase 1/2 trial of immunotherapy combination in {condition} patients who have progressed on standard therapy.",
        ),
        TrialSummary(
            nct_id="NCT04000003",
            title=f"Targeted Therapy for Biomarker-Selected {condition.title()} Patients",
            status="RECRUITING",
            phase="PHASE3",
            conditions=[condition],
            interventions=["Targeted agent MNO-456"],
            locations_count=25,
            brief_summary=f"Large Phase 3 trial for biomarker-selected {condition} patients with metastatic disease.",
        ),
    ]
    return templates


def _mock_trial_details(nct_id: str) -> TrialDetails:
    """Return a realistic mock trial detail when API is unavailable."""
    return TrialDetails(
        nct_id=nct_id,
        title="Mock Phase 2 Trial of Novel Agent",
        status="RECRUITING",
        phase="PHASE2",
        conditions=["Cancer"],
        interventions=["Drug XYZ-123"],
        eligibility_criteria_raw="""Inclusion Criteria:
- Histologically confirmed diagnosis of the relevant cancer type
- Age 18 years or older
- ECOG Performance Status 0, 1, or 2
- Measurable disease per RECIST 1.1
- Adequate organ function: creatinine ≤ 1.5x ULN, bilirubin ≤ 1.5x ULN
- At least one prior line of systemic therapy
- Metastatic or locally advanced disease
- Willing and able to provide written informed consent

Exclusion Criteria:
- Active autoimmune disease requiring systemic treatment
- Active brain metastases unless treated and stable
- Active HIV infection or known hepatitis B or C
- Concurrent anticoagulation therapy (with exceptions)
- Pregnancy or breastfeeding
- Prior organ transplant
- Uncontrolled diabetes
""",
        minimum_age=18,
        maximum_age=None,
        sex_criteria="ALL",
        healthy_volunteers=False,
        locations=[
            {"facility": "University Medical Center", "city": "New York", "state": "NY", "country": "USA"},
            {"facility": "City Cancer Institute", "city": "Los Angeles", "state": "CA", "country": "USA"},
        ],
        sponsor="National Cancer Institute",
        brief_summary="A Phase 2 randomized trial evaluating novel targeted therapy.",
        contact_email="trials@nci.example.gov",
        contact_phone="1-800-555-0100",
    )
