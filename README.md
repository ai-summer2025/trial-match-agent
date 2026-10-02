# 🧬 Clinical Trial Match Agent

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-32%20passing-brightgreen.svg)](#testing)
[![No Paid APIs](https://img.shields.io/badge/APIs-free%20%26%20open-orange.svg)](https://clinicaltrials.gov/data-api/api)

An **agentic AI system** that autonomously matches cancer patients to recruiting clinical trials using real-time data from the ClinicalTrials.gov public API — no paid API keys required.

---

## 🚨 The Problem

- **85%** of clinical trials fail to meet enrollment targets
- Only **3–5%** of eligible patients ever participate in a trial
- Oncologists spend hours manually combing through thousands of trials
- Patients miss life-extending treatments they never knew existed

A single oncologist managing 50+ active patients cannot realistically evaluate 400,000+ trials on ClinicalTrials.gov by hand. The matching process demands structured reasoning: eligibility criterion parsing, age/sex checks, comorbidity filtering, and treatment history analysis.

---

## 🤖 Architecture

This is **not a chatbot wrapper**. The agent runs a deterministic 6-step autonomous loop:

```
Patient Profile
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1 │ Profile Analysis   Extract conditions, demographics,  │
│         │                   prior treatments, ECOG status       │
│  Step 2 │ Trial Search       Query ClinicalTrials.gov API v2    │
│         │                   with condition-specific terms       │
│  Step 3 │ Detail Retrieval   Fetch full eligibility criteria    │
│         │                   for each candidate trial            │
│  Step 4 │ Eligibility Eval   Rule-based + keyword analysis:     │
│         │                   inclusion/exclusion per criterion   │
│  Step 5 │ Scoring & Ranking  Weighted match score (0-100)       │
│  Step 6 │ Report Generation  Structured clinical output         │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
Ranked Match Report (text or JSON)
```

### Scoring Formula
| Component | Weight | Signal |
|-----------|--------|--------|
| Inclusion criteria met | +60% | Higher = better |
| Inclusion criteria not met | −40% | Lower = better |
| Exclusion criteria clear | +40% | Higher = better |
| Exclusion criteria triggered | −30% | Lower = better |

Patients who fail basic checks (age out of range, wrong sex for trial) receive a score of **0** and are excluded from the report.

---

## 📁 Project Structure

```
clinical-trial-match-agent/
├── agent.py          # Main agentic loop (6-step pipeline)
├── patient.py        # PatientProfile dataclass + sample patients
├── tools.py          # Agent tools: search, fetch, parse, evaluate
├── report.py         # Report generation (text + JSON)
├── test_main.py      # 32 unit tests covering all core logic
├── requirements.txt  # Dependencies (just requests)
└── README.md
```

---

## ⚙️ Installation

```bash
git clone https://github.com/ai-summer2025/clinical-trial-match-agent
cd clinical-trial-match-agent
pip install -r requirements.txt
```

**Requirements:** Python 3.8+, `requests` — no paid API keys, no accounts needed.

---

## 🚀 Usage

### Run on a sample patient

```bash
# Match a 58-year-old female NSCLC patient (ECOG 1) — text report
python agent.py --patient PT001 --format text

# Colorectal cancer patient — JSON output, max 5 trials
python agent.py --patient PT002 --format json --max-trials 5

# Demo mode with mock data (no network required)
python agent.py --demo --patient PT001
```

### Example output (truncated)

```
============================================================
  CLINICAL TRIAL MATCH AGENT — Patient PT001
============================================================

[Step 1] Analyzing patient profile...
[Step 2] Searching ClinicalTrials.gov for 'non-small cell lung cancer'...
[Step 3] Retrieved details for 8 trials
[Step 4] Evaluating eligibility for 8 trials...
[Step 5] Scoring and ranking 8 matches...
[Step 6] Generating report...

══════════════════════════════════════════════════════
         CLINICAL TRIAL MATCH REPORT
══════════════════════════════════════════════════════
Patient: PT001 | Age: 58 | Sex: Female
Diagnosis: non-small cell lung cancer
ECOG PS: 1 | Metastatic: Yes
Report Date: 2026-10-02
──────────────────────────────────────────────────────
MATCH SUMMARY
  Trials Evaluated:  8
  Trials Matched:    5
  Top Score:         78.0/100
──────────────────────────────────────────────────────
RANKED MATCHES

  #1  NCT04892056  [Score: 78.0]
  ✅ STRONG MATCH
  Phase 2/3 Pembrolizumab + Chemotherapy for NSCLC
  Sponsor: National Cancer Institute
  
  Inclusion criteria met (4/5):
    ✓ Age ≥18 years
    ✓ Histologically confirmed NSCLC
    ✓ ECOG Performance Status 0-1
    ✓ No prior immunotherapy
    ? Adequate organ function (unknown)
  
  Exclusion triggers (0):
    ✓ No active autoimmune disease
    ✓ No brain metastases requiring steroids
```

### Use as a library

```python
from agent import ClinicalTrialMatchAgent
from patient import PatientProfile

patient = PatientProfile(
    patient_id="MY001",
    age=62,
    sex="Male",
    primary_diagnosis="prostate cancer",
    ecog_performance_status=0,
    has_metastatic_disease=True,
    prior_treatments=["androgen deprivation therapy"],
)

agent = ClinicalTrialMatchAgent(max_trials=10, verbose=True)
report = agent.run(patient, output_format="text")
print(report)
```

---

## 🧪 Testing

```bash
python test_main.py
```

**32 tests** covering:
- Patient profile parsing and serialization
- Eligibility criteria parsing (inclusion/exclusion split)
- Match scoring algorithm bounds and correctness
- Age/sex basic eligibility checks
- Mock data fallback integrity
- Full agent run with mocked API (JSON + text output)
- Empty result handling

All tests run **offline** — no network access required.

---

## 📊 Impact Potential

| Metric | Current State | With Agent |
|--------|--------------|-----------|
| Time to screen 100 trials | 4–8 hours (manual) | ~30 seconds |
| Criteria checked per trial | 5–10 (fatigue) | All criteria |
| Audit trail | None | Structured JSON |
| Replicability | Subjective | Deterministic |

---

## 🔌 Data Source

All trial data comes from **[ClinicalTrials.gov v2 API](https://clinicaltrials.gov/data-api/api)** — a free, public, no-key-required REST API maintained by the U.S. National Library of Medicine. The system gracefully falls back to mock data when the API is unavailable.

---

## ⚠️ Disclaimer

This tool is for **research and demonstration purposes only**. It does not constitute medical advice. All clinical trial eligibility determinations must be made by a licensed physician who has reviewed the full protocol and the patient's complete medical history.

---

## 🤝 Contributing

PRs welcome. Areas for improvement:
- NLP-based criterion parsing (replace keyword matching)
- FHIR R4 patient record import
- Geographic proximity filtering
- Biomarker/genomic matching

---

## 📄 License

MIT © 2026 ai-summer2025
