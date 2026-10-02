"""
Tests for Clinical Trial Match Agent.
Covers core logic without requiring live API access.
"""
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, "/tmp/clinical-trial-match-agent")

from agent import ClinicalTrialMatchAgent
from patient import PatientProfile, SAMPLE_PATIENTS
from tools import (
    EligibilityEvaluation,
    TrialDetails,
    TrialSummary,
    _compute_match_score,
    _mock_trial_details,
    _mock_search_results,
    evaluate_patient_eligibility,
    parse_eligibility_criteria,
)
from report import TrialMatch, generate_report


class TestPatientProfile(unittest.TestCase):
    """Tests for patient profile data structures."""

    def test_sample_patients_exist(self):
        """Verify sample patients are available."""
        self.assertIn("PT001", SAMPLE_PATIENTS)
        self.assertIn("PT002", SAMPLE_PATIENTS)
        self.assertIn("PT003", SAMPLE_PATIENTS)

    def test_patient_summary_contains_diagnosis(self):
        """Patient summary should include the diagnosis."""
        patient = SAMPLE_PATIENTS["PT001"]
        summary = patient.to_summary()
        self.assertIn("non-small cell lung cancer", summary)
        self.assertIn("PT001", summary)

    def test_patient_age_sex(self):
        """Patient attributes should be correctly set."""
        patient = SAMPLE_PATIENTS["PT001"]
        self.assertEqual(patient.age, 58)
        self.assertEqual(patient.sex, "Female")
        self.assertEqual(patient.ecog_performance_status, 1)

    def test_patient_fields_are_populated(self):
        """Verify key fields are populated for all sample patients."""
        for pid, patient in SAMPLE_PATIENTS.items():
            self.assertIsNotNone(patient.primary_diagnosis, f"Missing diagnosis for {pid}")
            self.assertGreater(patient.age, 0, f"Invalid age for {pid}")
            self.assertIn(patient.sex, ("Male", "Female", "Other"), f"Invalid sex for {pid}")


class TestEligibilityParsing(unittest.TestCase):
    """Tests for eligibility criteria parsing."""

    def test_parse_standard_format(self):
        """Parse standard inclusion/exclusion format."""
        raw = """
Inclusion Criteria:
- Age 18 years or older
- Histologically confirmed diagnosis
- ECOG Performance Status 0 or 1
- Adequate organ function

Exclusion Criteria:
- Active autoimmune disease
- Brain metastases
- HIV infection
"""
        inclusion, exclusion = parse_eligibility_criteria(raw)
        self.assertGreater(len(inclusion), 0)
        self.assertGreater(len(exclusion), 0)

    def test_parse_empty_criteria(self):
        """Handle empty criteria string gracefully."""
        inclusion, exclusion = parse_eligibility_criteria("")
        self.assertEqual(inclusion, [])
        self.assertEqual(exclusion, [])

    def test_parse_inclusion_only(self):
        """Handle criteria with only inclusion section."""
        raw = """
Inclusion Criteria:
- Confirmed cancer diagnosis
- Age over 18
"""
        inclusion, exclusion = parse_eligibility_criteria(raw)
        self.assertGreater(len(inclusion), 0)

    def test_parse_criteria_length_limits(self):
        """Ensure parsing caps at reasonable length."""
        raw = "Inclusion Criteria:\n" + "\n".join([f"- Criterion {i}: " + "x" * 100 for i in range(50)])
        inclusion, exclusion = parse_eligibility_criteria(raw)
        self.assertLessEqual(len(inclusion), 20)


class TestMatchScoring(unittest.TestCase):
    """Tests for the match scoring algorithm."""

    def test_perfect_match_score(self):
        """Perfect match should score near 100."""
        score = _compute_match_score(
            passed_basic=True,
            inc_met=10, inc_not_met=0, inc_unknown=0,
            exc_triggered=0, exc_clear=10,
            total_inclusion=10, total_exclusion=10,
        )
        self.assertGreater(score, 60)

    def test_disqualified_scores_zero(self):
        """Patient who fails basic checks should score 0."""
        score = _compute_match_score(
            passed_basic=False,
            inc_met=5, inc_not_met=0, inc_unknown=0,
            exc_triggered=0, exc_clear=5,
            total_inclusion=5, total_exclusion=5,
        )
        self.assertEqual(score, 0.0)

    def test_exclusion_triggers_reduce_score(self):
        """Exclusion triggers should reduce score."""
        score_clean = _compute_match_score(
            passed_basic=True,
            inc_met=5, inc_not_met=0, inc_unknown=0,
            exc_triggered=0, exc_clear=5,
            total_inclusion=5, total_exclusion=5,
        )
        score_flagged = _compute_match_score(
            passed_basic=True,
            inc_met=5, inc_not_met=0, inc_unknown=0,
            exc_triggered=5, exc_clear=0,
            total_inclusion=5, total_exclusion=5,
        )
        self.assertGreater(score_clean, score_flagged)

    def test_score_is_bounded_0_100(self):
        """Score should always be between 0 and 100."""
        for scenario in [
            dict(passed_basic=True, inc_met=10, inc_not_met=0, inc_unknown=0, exc_triggered=0, exc_clear=10, total_inclusion=10, total_exclusion=10),
            dict(passed_basic=True, inc_met=0, inc_not_met=10, inc_unknown=0, exc_triggered=10, exc_clear=0, total_inclusion=10, total_exclusion=10),
            dict(passed_basic=False, inc_met=10, inc_not_met=0, inc_unknown=0, exc_triggered=0, exc_clear=10, total_inclusion=10, total_exclusion=10),
        ]:
            score = _compute_match_score(**scenario)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 100.0)


class TestEligibilityEvaluation(unittest.TestCase):
    """Tests for the full eligibility evaluation tool."""

    def setUp(self):
        self.patient = SAMPLE_PATIENTS["PT001"]  # 58F, NSCLC, ECOG 1
        self.trial = _mock_trial_details("NCT04000001")

    def test_age_within_range_passes(self):
        """Patient within age range should pass basic check."""
        self.trial.minimum_age = 18
        self.trial.maximum_age = 75
        eval_result = evaluate_patient_eligibility(self.patient, self.trial)
        self.assertTrue(eval_result.passed_basic)

    def test_age_below_minimum_fails(self):
        """Patient below minimum age should fail basic check."""
        self.trial.minimum_age = 65
        self.trial.maximum_age = None
        eval_result = evaluate_patient_eligibility(self.patient, self.trial)
        self.assertFalse(eval_result.passed_basic)
        self.assertTrue(any("minimum" in issue.lower() or "age" in issue.lower() for issue in eval_result.basic_issues))

    def test_wrong_sex_fails(self):
        """Male-only trial should disqualify female patient."""
        self.trial.sex_criteria = "MALE"
        eval_result = evaluate_patient_eligibility(self.patient, self.trial)
        self.assertFalse(eval_result.passed_basic)

    def test_evaluation_returns_score(self):
        """Evaluation should always return a score."""
        eval_result = evaluate_patient_eligibility(self.patient, self.trial)
        self.assertIsInstance(eval_result.score, float)
        self.assertGreaterEqual(eval_result.score, 0.0)
        self.assertLessEqual(eval_result.score, 100.0)

    def test_evaluation_has_reasoning(self):
        """Evaluation should generate a reasoning string."""
        eval_result = evaluate_patient_eligibility(self.patient, self.trial)
        self.assertIsInstance(eval_result.reasoning, str)
        self.assertGreater(len(eval_result.reasoning), 10)

    def test_all_sex_criteria_passes_both(self):
        """ALL sex criteria should pass both male and female patients."""
        self.trial.sex_criteria = "ALL"
        for pid in ("PT001", "PT002"):  # Female and Male
            patient = SAMPLE_PATIENTS[pid]
            eval_result = evaluate_patient_eligibility(patient, self.trial)
            # Sex should not be an issue
            sex_issues = [i for i in eval_result.basic_issues if "sex" in i.lower() or "male" in i.lower() or "female" in i.lower()]
            self.assertEqual(len(sex_issues), 0, f"Unexpected sex issue for {pid}: {sex_issues}")


class TestMockData(unittest.TestCase):
    """Tests for mock data fallbacks."""

    def test_mock_search_returns_results(self):
        """Mock search should return trial summaries."""
        results = _mock_search_results("lung cancer")
        self.assertGreater(len(results), 0)
        for result in results:
            self.assertIsInstance(result, TrialSummary)
            self.assertIsNotNone(result.nct_id)

    def test_mock_trial_details_valid(self):
        """Mock trial details should have required fields."""
        details = _mock_trial_details("NCT99999999")
        self.assertIsNotNone(details.nct_id)
        self.assertIsNotNone(details.eligibility_criteria_raw)
        self.assertIsNotNone(details.title)

    def test_mock_trial_has_eligibility_text(self):
        """Mock trial should include parseable eligibility criteria."""
        details = _mock_trial_details("NCT99999999")
        inclusion, exclusion = parse_eligibility_criteria(details.eligibility_criteria_raw)
        self.assertGreater(len(inclusion), 0)
        self.assertGreater(len(exclusion), 0)


class TestReportGeneration(unittest.TestCase):
    """Tests for report generation."""

    def setUp(self):
        self.patient = SAMPLE_PATIENTS["PT001"]
        trial = _mock_trial_details("NCT04000001")
        trial.sponsor = "National Cancer Institute"
        eval_result = EligibilityEvaluation(
            nct_id="NCT04000001",
            passed_basic=True,
            basic_issues=[],
            inclusion_met=["Age ≥18", "ECOG 0-1", "Histologic confirmation"],
            inclusion_not_met=[],
            inclusion_unknown=["Adequate organ function"],
            exclusion_triggered=[],
            exclusion_clear=["No active autoimmune disease", "No brain mets"],
            exclusion_unknown=[],
            score=72.0,
            reasoning="✅ STRONG MATCH (Score: 72/100) Patient (58y Female, non-small cell lung cancer) vs Phase2 trial.",
        )
        self.match = TrialMatch(trial=trial, evaluation=eval_result, rank=1)

    def test_text_report_contains_patient_id(self):
        """Text report should contain patient ID."""
        report = generate_report(self.patient, [self.match], output_format="text")
        self.assertIn("PT001", report)

    def test_text_report_contains_nct_id(self):
        """Text report should contain trial NCT ID."""
        report = generate_report(self.patient, [self.match], output_format="text")
        self.assertIn("NCT04000001", report)

    def test_json_report_is_valid_json(self):
        """JSON report should be valid JSON."""
        report = generate_report(self.patient, [self.match], output_format="json")
        data = json.loads(report)
        self.assertIn("matches", data)
        self.assertIn("patient", data)
        self.assertEqual(len(data["matches"]), 1)

    def test_json_report_score_correct(self):
        """JSON report should contain the correct score."""
        report = generate_report(self.patient, [self.match], output_format="json")
        data = json.loads(report)
        self.assertEqual(data["matches"][0]["score"], 72.0)

    def test_empty_matches_report(self):
        """Report with no matches should handle gracefully."""
        report = generate_report(self.patient, [], output_format="text")
        self.assertIn("No matching clinical trials", report)


class TestAgentSearchTermExtraction(unittest.TestCase):
    """Tests for agent's search term extraction logic."""

    def setUp(self):
        self.agent = ClinicalTrialMatchAgent(verbose=False)

    def test_nsclc_terms(self):
        """NSCLC patient should get lung cancer search terms."""
        patient = SAMPLE_PATIENTS["PT001"]  # non-small cell lung cancer
        terms = self.agent._extract_search_terms(patient)
        self.assertIn("non-small cell lung cancer", terms)
        self.assertTrue(any("lung" in t.lower() for t in terms))

    def test_colorectal_terms(self):
        """Colorectal patient should get appropriate terms."""
        patient = SAMPLE_PATIENTS["PT002"]  # colorectal cancer
        terms = self.agent._extract_search_terms(patient)
        self.assertIn("colorectal cancer", terms)
        self.assertTrue(any("colorectal" in t.lower() or "colon" in t.lower() for t in terms))

    def test_returns_list_of_strings(self):
        """Search terms should be a list of non-empty strings."""
        for pid, patient in SAMPLE_PATIENTS.items():
            terms = self.agent._extract_search_terms(patient)
            self.assertIsInstance(terms, list, f"Terms not a list for {pid}")
            self.assertGreater(len(terms), 0, f"No terms for {pid}")
            for t in terms:
                self.assertIsInstance(t, str)
                self.assertGreater(len(t), 0)


class TestAgentRunWithMocks(unittest.TestCase):
    """Integration tests for the full agent run using mocked API calls."""

    @patch("agent.search_trials")
    @patch("agent.get_trial_details")
    def test_agent_run_produces_report(self, mock_get_details, mock_search):
        """Agent run should produce a non-empty report."""
        patient = SAMPLE_PATIENTS["PT001"]

        # Mock search results
        mock_search.return_value = _mock_search_results("non-small cell lung cancer")

        # Mock detail fetch
        mock_get_details.return_value = _mock_trial_details("NCT04000001")

        agent = ClinicalTrialMatchAgent(
            max_trials=3,
            delay_between_calls=0,
            verbose=False,
        )
        report = agent.run(patient, output_format="text")

        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 100)
        self.assertIn("PT001", report)

    @patch("agent.search_trials")
    @patch("agent.get_trial_details")
    def test_agent_json_output(self, mock_get_details, mock_search):
        """Agent should produce valid JSON output when requested."""
        patient = SAMPLE_PATIENTS["PT002"]
        mock_search.return_value = _mock_search_results("colorectal cancer")
        mock_get_details.return_value = _mock_trial_details("NCT04000002")

        agent = ClinicalTrialMatchAgent(max_trials=2, delay_between_calls=0, verbose=False)
        report = agent.run(patient, output_format="json")

        data = json.loads(report)
        self.assertIn("patient", data)
        self.assertIn("matches", data)
        self.assertEqual(data["patient"]["id"], "PT002")

    @patch("agent.search_trials")
    def test_agent_handles_empty_search(self, mock_search):
        """Agent should handle empty search results gracefully."""
        mock_search.return_value = []
        patient = SAMPLE_PATIENTS["PT003"]

        agent = ClinicalTrialMatchAgent(max_trials=5, delay_between_calls=0, verbose=False)
        report = agent.run(patient, output_format="text")

        self.assertIsInstance(report, str)
        # Should either find no matches or produce a valid report
        self.assertGreater(len(report), 10)


if __name__ == "__main__":
    print("Running Clinical Trial Match Agent tests...")
    result = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
