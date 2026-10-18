from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .ctgov import parse_study
from .models import Patient, Trial


def load_patient(path: str) -> Patient:
    d = json.loads(Path(path).read_text())
    return Patient(**{k: v for k, v in d.items() if k in Patient.__dataclass_fields__})


def load_trials(path: str) -> List[Trial]:
    """Load a JSON file holding a ClinicalTrials.gov v2 response ({"studies": [...]}) or a list of studies."""
    d = json.loads(Path(path).read_text())
    studies = d.get("studies", []) if isinstance(d, dict) else d
    return [parse_study(s) for s in studies]
