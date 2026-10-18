"""trialmatch: screen patients against clinical trial eligibility criteria."""
from .criteria import evaluate, parse_llm, parse_rules, split_criteria
from .matcher import match, rank
from .models import Criterion, MatchResult, Patient, Trial

__all__ = ["Criterion", "MatchResult", "Patient", "Trial", "evaluate", "match", "parse_llm", "parse_rules",
           "rank", "split_criteria"]
__version__ = "1.0.0"
