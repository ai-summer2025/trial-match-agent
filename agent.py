"""
Clinical Trial Match Agent — Agentic AI system for matching patients to clinical trials.

Architecture:
  PatientProfile → [Agent Loop] → TrialSearch → DetailFetch → EligibilityEval → Report

The agent autonomously:
  1. Extracts search terms from patient profile
  2. Queries ClinicalTrials.gov (free public API)
  3. Fetches details for each trial
  4. Evaluates eligibility criterion by criterion
  5. Scores and ranks matches
  6. Generates a clinical report
"""
import argparse
import json
import logging
import sys
import time
from typing import List, Optional

from patient import PatientProfile, SAMPLE_PATIENTS
from report import TrialMatch, generate_report
from tools import (
    EligibilityEvaluation,
    TrialDetails,
    TrialSummary,
    evaluate_patient_eligibility,
    get_trial_details,
    search_trials,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


class ClinicalTrialMatchAgent:
    """
    Agentic system that autonomously matches patients to clinical trials.
    
    The agent loop:
      Step 1: Profile Analysis  — Extract key clinical features
      Step 2: Trial Search      — Query ClinicalTrials.gov
      Step 3: Detail Retrieval  — Fetch full trial details
      Step 4: Eligibility Eval  — Evaluate each criterion
      Step 5: Scoring & Ranking — Score and rank matches
      Step 6: Report Generation — Create clinical output
    """

    def __init__(
        self,
        max_trials: int = 10,
        min_score_threshold: float = 0.0,
        trial_status: str = "RECRUITING",
        delay_between_calls: float = 0.5,
        verbose: bool = True,
    ):
        self.max_trials = max_trials
        self.min_score_threshold = min_score_threshold
        self.trial_status = trial_status
        self.delay_between_calls = delay_between_calls
        self.verbose = verbose
        self._steps_log: List[str] = []

    def log_step(self, step: int, message: str):
        """Log an agent step."""
        entry = f"[Step {step}] {message}"
        self._steps_log.append(entry)
        if self.verbose:
            logger.info(entry)

    def run(self, patient: PatientProfile, output_format: str = "text") -> str:
        """
        Run the full agentic matching pipeline for a patient.
        
        Returns formatted report string.
        """
        self._steps_log = []
        print(f"\n{'='*60}")
        print(f"  CLINICAL TRIAL MATCH AGENT — Patient {patient.patient_id}")
        print(f"{'='*60}")

        # ── Step 1: Profile Analysis ──────────────────────────────────────────
        self.log_step(1, "Analyzing patient profile...")
        search_terms = self._extract_search_terms(patient)
        self.log_step(1, f"Search terms: {search_terms}")

        # ── Step 2: Trial Search ──────────────────────────────────────────────
        self.log_step(2, f"Searching ClinicalTrials.gov for '{search_terms[0]}'...")
        summaries = search_trials(
            condition=search_terms[0],
            max_results=self.max_trials,
            status_filter=self.trial_status,
        )
        self.log_step(2, f"Found {len(summaries)} candidate trials")

        if not summaries:
            self.log_step(2, "No trials found. Trying broader search term...")
            if len(search_terms) > 1:
                summaries = search_trials(
                    condition=search_terms[1],
                    max_results=self.max_trials,
                    status_filter=self.trial_status,
                )

        # ── Step 3: Detail Retrieval ──────────────────────────────────────────
        self.log_step(3, f"Retrieving details for {len(summaries)} trials...")
        detailed_trials: List[TrialDetails] = []
        
        for i, summary in enumerate(summaries):
            self.log_step(3, f"  Fetching {summary.nct_id} ({i+1}/{len(summaries)}): {summary.title[:50]}")
            details = get_trial_details(summary.nct_id)
            if details:
                detailed_trials.append(details)
            if self.delay_between_calls > 0:
                time.sleep(self.delay_between_calls)

        self.log_step(3, f"Retrieved details for {len(detailed_trials)} trials")

        # ── Step 4: Eligibility Evaluation ───────────────────────────────────
        self.log_step(4, "Evaluating patient eligibility for each trial...")
        evaluations: List[EligibilityEvaluation] = []

        for trial in detailed_trials:
            self.log_step(4, f"  Evaluating against {trial.nct_id}...")
            eval_result = evaluate_patient_eligibility(patient, trial)
            evaluations.append(eval_result)

        # ── Step 5: Scoring & Ranking ─────────────────────────────────────────
        self.log_step(5, "Scoring and ranking matches...")
        
        trial_map = {t.nct_id: t for t in detailed_trials}
        matches = []

        for eval_result in evaluations:
            if eval_result.score >= self.min_score_threshold and eval_result.passed_basic:
                trial = trial_map.get(eval_result.nct_id)
                if trial:
                    matches.append((eval_result.score, eval_result, trial))

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)

        ranked_matches = [
            TrialMatch(trial=m[2], evaluation=m[1], rank=i + 1)
            for i, m in enumerate(matches)
        ]

        self.log_step(5, f"Ranked {len(ranked_matches)} matches above threshold")

        # ── Step 6: Report Generation ─────────────────────────────────────────
        self.log_step(6, "Generating clinical report...")
        report = generate_report(patient, ranked_matches, output_format=output_format)

        self.log_step(6, "✅ Agent run complete")
        return report

    def _extract_search_terms(self, patient: PatientProfile) -> List[str]:
        """Extract prioritized search terms from patient profile."""
        terms = [patient.primary_diagnosis]
        
        # Add common synonyms / broader terms
        diagnosis = patient.primary_diagnosis.lower()
        
        if "lung" in diagnosis:
            terms.extend(["lung cancer", "lung neoplasm"])
        elif "colorectal" in diagnosis or "colon" in diagnosis:
            terms.extend(["colorectal cancer", "colon cancer"])
        elif "prostate" in diagnosis:
            terms.extend(["prostate cancer", "prostate neoplasm"])
        elif "breast" in diagnosis:
            terms.extend(["breast cancer", "breast neoplasm"])
        elif "leukemia" in diagnosis:
            terms.extend(["leukemia", "acute leukemia"])
        elif "lymphoma" in diagnosis:
            terms.extend(["lymphoma", "non-hodgkin lymphoma"])
        
        # Always add a fallback
        terms.append("cancer")
        
        return terms[:3]

    def get_agent_log(self) -> List[str]:
        """Return the agent's step log."""
        return self._steps_log.copy()


# ─── CLI Interface ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Clinical Trial Match Agent — Agentic AI for clinical trial matching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py --patient PT001
  python agent.py --patient PT002 --format json --max-trials 15
  python agent.py --demo

Built on ClinicalTrials.gov v2 API (no API key required)
        """
    )
    parser.add_argument(
        "--patient", "-p",
        type=str,
        default="PT001",
        choices=list(SAMPLE_PATIENTS.keys()),
        help="Patient ID to match (default: PT001)"
    )
    parser.add_argument(
        "--format", "-f",
        type=str,
        default="text",
        choices=["text", "json"],
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--max-trials", "-n",
        type=int,
        default=8,
        help="Max number of trials to evaluate (default: 8)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo with all sample patients"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=True,
        help="Verbose output (default: True)"
    )

    args = parser.parse_args()

    agent = ClinicalTrialMatchAgent(
        max_trials=args.max_trials,
        verbose=args.verbose,
    )

    if args.demo:
        print("\n🏥 CLINICAL TRIAL MATCH AGENT — DEMO MODE")
        print("Running agent for all sample patients...\n")
        for patient_id, patient in SAMPLE_PATIENTS.items():
            report = agent.run(patient, output_format="text")
            print(report)
            print("\n" + "="*70 + "\n")
    else:
        patient = SAMPLE_PATIENTS[args.patient]
        report = agent.run(patient, output_format=args.format)
        print(report)


if __name__ == "__main__":
    main()
