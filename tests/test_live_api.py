"""Live smoke test against ClinicalTrials.gov. Skipped unless TRIALMATCH_LIVE=1."""
import os

import pytest

from trialmatch.ctgov import search


@pytest.mark.skipif(os.environ.get("TRIALMATCH_LIVE") != "1", reason="set TRIALMATCH_LIVE=1 to run")
def test_live_search_returns_parsed_trials():
    trials = search("type 2 diabetes", page_size=5)
    assert trials and all(t.nct_id.startswith("NCT") for t in trials)
    assert any(t.eligibility_text for t in trials)
