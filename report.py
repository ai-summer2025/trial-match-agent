"""
Report generation for clinical trial match results.
"""
import json
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

from tools import TrialDetails, EligibilityEvaluation
from patient import PatientProfile


@dataclass
class TrialMatch:
    """A complete trial match result combining trial details and evaluation."""
    trial: TrialDetails
    evaluation: EligibilityEvaluation
    rank: int


def generate_report(
    patient: PatientProfile,
    matches: List[TrialMatch],
    output_format: str = "text"
) -> str:
    """
    Generate a formatted clinical trial match report.
    
    Args:
        patient: Patient profile
        matches: Ranked list of trial matches
        output_format: "text" or "json"
    
    Returns:
        Formatted report string
    """
    if output_format == "json":
        return _generate_json_report(patient, matches)
    return _generate_text_report(patient, matches)


def _generate_text_report(patient: PatientProfile, matches: List[TrialMatch]) -> str:
    """Generate a human-readable text report."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append("=" * 70)
    lines.append("  CLINICAL TRIAL MATCH REPORT")
    lines.append(f"  Generated: {now}")
    lines.append("=" * 70)
    lines.append("")
    
    # Patient summary
    lines.append("PATIENT PROFILE")
    lines.append("-" * 40)
    lines.append(patient.to_summary())
    lines.append("")

    if not matches:
        lines.append("⚠ No matching clinical trials found.")
        lines.append("Recommendation: Expand search criteria or consult with oncology team.")
        return "\n".join(lines)

    # Match summary
    strong = [m for m in matches if m.evaluation.score >= 70]
    possible = [m for m in matches if 45 <= m.evaluation.score < 70]
    weak = [m for m in matches if m.evaluation.score < 45 and m.evaluation.passed_basic]

    lines.append("MATCH SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total trials evaluated: {len(matches)}")
    lines.append(f"  ✅ Strong matches (score ≥70):    {len(strong)}")
    lines.append(f"  🟡 Possible matches (45–69):      {len(possible)}")
    lines.append(f"  🟠 Weak matches (<45):             {len(weak)}")
    lines.append("")

    # Ranked results
    lines.append("RANKED TRIAL MATCHES")
    lines.append("=" * 70)

    for match in matches:
        eval_ = match.evaluation
        trial = match.trial

        if eval_.score >= 70:
            indicator = "✅ STRONG"
        elif eval_.score >= 45:
            indicator = "🟡 POSSIBLE"
        elif eval_.score >= 20:
            indicator = "🟠 WEAK"
        else:
            indicator = "❌ POOR"

        lines.append("")
        lines.append(f"#{match.rank}  {indicator}  |  Score: {eval_.score}/100")
        lines.append(f"    NCT ID: {trial.nct_id}")
        lines.append(f"    Title:  {trial.title[:70]}")
        lines.append(f"    Phase:  {trial.phase}  |  Sponsor: {trial.sponsor[:40]}")
        lines.append(f"    Status: {trial.status}  |  Sites: {len(trial.locations)}")

        if trial.locations:
            loc = trial.locations[0]
            lines.append(f"    Nearest Site: {loc.get('facility', '')} — {loc.get('city', '')}, {loc.get('state', '')}")

        lines.append(f"    Assessment: {eval_.reasoning}")

        if eval_.inclusion_met:
            lines.append(f"    Inclusion Met ({len(eval_.inclusion_met)}):")
            for c in eval_.inclusion_met[:3]:
                lines.append(f"      • {c[:80]}")

        if eval_.inclusion_not_met:
            lines.append(f"    ❌ Inclusion NOT Met ({len(eval_.inclusion_not_met)}):")
            for c in eval_.inclusion_not_met[:2]:
                lines.append(f"      • {c[:80]}")

        if eval_.exclusion_triggered:
            lines.append(f"    ⚠ Exclusion Flags ({len(eval_.exclusion_triggered)}):")
            for c in eval_.exclusion_triggered[:2]:
                lines.append(f"      {c[:80]}")

        if trial.contact_email or trial.contact_phone:
            lines.append(f"    Contact: {trial.contact_email or ''} {trial.contact_phone or ''}")

        lines.append("    " + "─" * 60)

    # Referral recommendation
    lines.append("")
    lines.append("RECOMMENDED NEXT STEPS")
    lines.append("-" * 40)
    if strong:
        lines.append(f"1. Discuss top {min(3, len(strong))} strong matches with patient at next visit.")
        lines.append(f"2. Review eligibility criteria in detail for: {', '.join(m.trial.nct_id for m in strong[:3])}")
        lines.append("3. Contact trial coordinators listed above to confirm current enrollment.")
    elif possible:
        lines.append(f"1. Review possible matches with oncology team: {', '.join(m.trial.nct_id for m in possible[:3])}")
        lines.append("2. Obtain additional clinical data to clarify unknown eligibility criteria.")
    else:
        lines.append("1. No strong matches found. Consider expanded search with broader criteria.")
        lines.append("2. Re-evaluate after next treatment cycle.")

    lines.append("")
    lines.append("─" * 70)
    lines.append("DISCLAIMER: This report is generated by an AI system for informational")
    lines.append("purposes only. All trial eligibility must be confirmed by a qualified")
    lines.append("healthcare provider and the trial team before enrollment.")
    lines.append("─" * 70)

    return "\n".join(lines)


def _generate_json_report(patient: PatientProfile, matches: List[TrialMatch]) -> str:
    """Generate a structured JSON report."""
    data = {
        "generated_at": datetime.now().isoformat(),
        "patient": {
            "id": patient.patient_id,
            "age": patient.age,
            "sex": patient.sex,
            "diagnosis": patient.primary_diagnosis,
            "ecog_ps": patient.ecog_performance_status,
            "metastatic": patient.has_metastatic_disease,
        },
        "matches": [
            {
                "rank": m.rank,
                "nct_id": m.trial.nct_id,
                "title": m.trial.title,
                "phase": m.trial.phase,
                "sponsor": m.trial.sponsor,
                "score": m.evaluation.score,
                "passed_basic": m.evaluation.passed_basic,
                "reasoning": m.evaluation.reasoning,
                "inclusion_met_count": len(m.evaluation.inclusion_met),
                "inclusion_not_met_count": len(m.evaluation.inclusion_not_met),
                "exclusion_flags_count": len(m.evaluation.exclusion_triggered),
                "site_count": len(m.trial.locations),
                "contact_email": m.trial.contact_email,
                "clinicaltrials_url": f"https://clinicaltrials.gov/study/{m.trial.nct_id}",
            }
            for m in matches
        ],
        "summary": {
            "total_evaluated": len(matches),
            "strong_matches": sum(1 for m in matches if m.evaluation.score >= 70),
            "possible_matches": sum(1 for m in matches if 45 <= m.evaluation.score < 70),
        }
    }
    return json.dumps(data, indent=2)
