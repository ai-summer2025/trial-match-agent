"""ClinicalTrials.gov API v2 client (https://clinicaltrials.gov/data-api/api).

`parse_study` converts one v2 study record into a `Trial`. The bundled fixtures in
data/trials/ use the same record shape, so the parser is exercised offline in tests.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import List, Optional

from .models import Trial

BASE = "https://clinicaltrials.gov/api/v2/studies"


def _years(age: Optional[str]) -> Optional[float]:
    if not age:
        return None
    m = re.match(r"(\d+(?:\.\d+)?)\s*(year|month|week|day)", age.lower())
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2)
    return n / {"year": 1, "month": 12, "week": 52.18, "day": 365.25}[unit]


def parse_study(study: dict) -> Trial:
    ps = study.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    elig = ps.get("eligibilityModule", {})
    locs = ps.get("contactsLocationsModule", {}).get("locations", [])
    return Trial(
        nct_id=ident.get("nctId", ""),
        title=ident.get("briefTitle", ""),
        conditions=ps.get("conditionsModule", {}).get("conditions", []),
        eligibility_text=elig.get("eligibilityCriteria", ""),
        min_age=_years(elig.get("minimumAge")),
        max_age=_years(elig.get("maximumAge")),
        sex=elig.get("sex", "ALL"),
        status=ps.get("statusModule", {}).get("overallStatus", "UNKNOWN"),
        locations=[", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x)
                   for loc in locs],
    )


def search(condition: str, page_size: int = 20, recruiting_only: bool = True, timeout: float = 30) -> List[Trial]:
    params = {"query.cond": condition, "pageSize": str(page_size), "format": "json"}
    if recruiting_only:
        params["filter.overallStatus"] = "RECRUITING"
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # errors propagate: never treated as "no trials"
        data = json.loads(r.read())
    return [parse_study(s) for s in data.get("studies", [])]
