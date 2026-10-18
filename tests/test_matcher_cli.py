import json
import subprocess
import sys
from pathlib import Path

from trialmatch import Patient, match, rank
from trialmatch.cli import main
from trialmatch.ctgov import _years, parse_study
from trialmatch.pipeline import load_trials

ROOT = Path(__file__).resolve().parents[1]
TRIALS = {t.nct_id: t for t in load_trials(str(ROOT / "data/trials/synthetic_trials.json"))}


def test_parse_study_ages_and_sex():
    t = TRIALS["SYNTH0005"]
    assert (t.min_age, t.max_age, t.sex) == (50, None, "FEMALE")
    assert _years("6 Months") == 0.5


def test_parse_study_tolerates_missing_modules():
    t = parse_study({"protocolSection": {"identificationModule": {"nctId": "X"}}})
    assert t.nct_id == "X" and t.eligibility_text == "" and t.status == "UNKNOWN"


def test_hard_filters():
    p = Patient("p", 40, "male", conditions=["postmenopausal osteoporosis"])
    r = match(p, TRIALS["SYNTH0005"])
    assert r.verdict == "ineligible" and any("female" in x for x in r.reasons)
    assert match(p, TRIALS["SYNTH0006"]).verdict == "ineligible"


def test_ranking_puts_likely_eligible_first():
    p = Patient("p", 67, "male", conditions=["heart failure with reduced ejection fraction"],
                labs={"lvef": 30, "egfr": 38})
    res = rank(p, list(TRIALS.values()))
    assert res[0].trial.nct_id == "SYNTH0002" and res[0].verdict == "likely_eligible"


def test_cli_json(capsys):
    assert main(["match", str(ROOT / "data/patients/P3.json"), "--trials",
                 str(ROOT / "data/trials/synthetic_trials.json"), "--format", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["nct_id"] == "SYNTH0003" and out[0]["verdict"] == "likely_eligible"


def test_eval_does_not_regress():
    r = subprocess.run([sys.executable, str(ROOT / "eval/run_eval.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
