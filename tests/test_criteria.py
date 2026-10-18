import json

import pytest

from trialmatch import Criterion, Patient, evaluate, parse_llm, parse_rules, split_criteria


def crit(text, kind="inclusion"):
    return parse_rules(Criterion(text=text, kind=kind))


def test_split_inclusion_exclusion():
    cs = split_criteria("Inclusion Criteria:\n\n* A\n* B\n\nExclusion Criteria:\n\n1. C\n")
    assert [(c.kind, c.text) for c in cs] == [("inclusion", "A"), ("inclusion", "B"), ("exclusion", "C")]


@pytest.mark.parametrize("text,lab,low,high", [
    ("HbA1c between 7.0% and 10.5%", "hba1c", 7.0, 10.5),
    ("eGFR ≥ 45 mL/min/1.73m2", "egfr", 45, None),
    ("Platelets ≥ 100,000/mm³", "platelets", 100, None),
    ("Absolute neutrophil count ≥ 1,500/mm³", "anc", 1.5, None),
    ("LVEF ≤ 40%", "lvef", None, 40),
])
def test_lab_parsing_and_unit_normalization(text, lab, low, high):
    c = crit(text)
    assert (c.type, c.lab, c.low, c.high) == ("lab", lab, low, high)


def test_uln_relative_criteria_are_not_guessed():
    assert crit("ALT > 3 x upper limit of normal", "exclusion").type == "unparsed"


def test_exclusion_lab_range_describes_excluded_patients():
    c = crit("Hemoglobin < 8 g/dL", "exclusion")
    assert evaluate(c, Patient("p", 50, "male", labs={"hemoglobin": 7.5})).status == "not_met"
    assert evaluate(c, Patient("p", 50, "male", labs={"hemoglobin": 9.0})).status == "met"


def test_missing_lab_is_unknown_not_failed():
    assert evaluate(crit("eGFR ≥ 45"), Patient("p", 50, "male")).status == "unknown"


def test_type_numbers_must_match():
    c = crit("Type 1 diabetes", "exclusion")
    assert evaluate(c, Patient("p", 50, "male", conditions=["type 2 diabetes"])).status == "met"
    assert evaluate(c, Patient("p", 50, "male", conditions=["type 1 diabetes"])).status == "not_met"


def test_pregnancy_exclusion():
    c = crit("Pregnant or breastfeeding", "exclusion")
    assert evaluate(c, Patient("p", 30, "male")).status == "met"
    assert evaluate(c, Patient("p", 30, "female")).status == "unknown"
    assert evaluate(c, Patient("p", 30, "female", pregnant=True)).status == "not_met"


class FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user):
        return self.reply


def test_llm_parser_rejects_numbers_not_in_the_text():
    cs = [Criterion("HbA1c between 7.0% and 10.5%", "inclusion"), Criterion("eGFR ≥ 45", "inclusion")]
    reply = json.dumps([
        {"index": 0, "type": "lab", "lab": "hba1c", "low": 7.0, "high": 10.5},
        {"index": 1, "type": "lab", "lab": "egfr", "low": 30, "high": None},  # 30 is not in the text
    ])
    out = parse_llm(cs, FakeClient(reply))
    assert (out[0].type, out[0].low, out[0].high) == ("lab", 7.0, 10.5)
    assert out[1].type == "unparsed"


def test_llm_parser_normalizes_cell_counts():
    cs = [Criterion("Platelets ≥ 100,000/mm³", "inclusion")]
    reply = json.dumps([{"index": 0, "type": "lab", "lab": "platelets", "low": 100000, "high": None}])
    assert parse_llm(cs, FakeClient(reply))[0].low == 100
