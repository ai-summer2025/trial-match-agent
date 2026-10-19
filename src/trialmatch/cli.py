"""trialmatch match patient.json --trials data/trials/fixtures.json [--llm]
trialmatch match patient.json --search "type 2 diabetes"     (live ClinicalTrials.gov query)"""
from __future__ import annotations

import argparse
import json
import sys

from .matcher import rank
from .pipeline import load_patient, load_trials
from .report import to_markdown


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="trialmatch", description="Screen a patient against clinical trials.")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("match")
    m.add_argument("patient")
    src = m.add_mutually_exclusive_group(required=True)
    src.add_argument("--trials", help="JSON file of ClinicalTrials.gov v2 study records")
    src.add_argument("--search", help="Condition to search live on ClinicalTrials.gov")
    m.add_argument("--max", type=int, default=20)
    m.add_argument("--llm", action="store_true", help="Parse criteria with an LLM")
    m.add_argument("--format", choices=["markdown", "json"], default="markdown")
    a = p.parse_args(argv)

    patient = load_patient(a.patient)
    if a.trials:
        trials = load_trials(a.trials)
    else:
        from .ctgov import search
        trials = search(a.search, page_size=a.max)
    client = None
    if a.llm:
        from .llm import client_from_env
        client = client_from_env()
    results = rank(patient, trials[: a.max], client)
    if a.format == "json":
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(to_markdown(patient, results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
