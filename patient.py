"""
Patient profile data structures for clinical trial matching.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PatientProfile:
    """Structured patient profile for trial matching."""
    patient_id: str
    age: int
    sex: str  # "Male", "Female", "Other"
    primary_diagnosis: str
    secondary_conditions: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)
    prior_treatments: List[str] = field(default_factory=list)
    ecog_performance_status: Optional[int] = None  # 0-4 scale
    has_metastatic_disease: bool = False
    organ_function: dict = field(default_factory=dict)
    zip_code: Optional[str] = None
    notes: Optional[str] = None

    def to_summary(self) -> str:
        """Generate a clinical summary string for display."""
        lines = [
            f"Patient {self.patient_id}",
            f"Age: {self.age} | Sex: {self.sex}",
            f"Diagnosis: {self.primary_diagnosis}",
        ]
        if self.secondary_conditions:
            lines.append(f"Other conditions: {', '.join(self.secondary_conditions)}")
        if self.current_medications:
            lines.append(f"Medications: {', '.join(self.current_medications)}")
        if self.prior_treatments:
            lines.append(f"Prior treatments: {', '.join(self.prior_treatments)}")
        if self.ecog_performance_status is not None:
            lines.append(f"ECOG PS: {self.ecog_performance_status}")
        if self.has_metastatic_disease:
            lines.append("Metastatic disease: Yes")
        return "\n".join(lines)


# Sample patient profiles for demo
SAMPLE_PATIENTS = {
    "PT001": PatientProfile(
        patient_id="PT001",
        age=58,
        sex="Female",
        primary_diagnosis="non-small cell lung cancer",
        secondary_conditions=["hypertension", "type 2 diabetes"],
        current_medications=["metformin", "lisinopril", "aspirin"],
        prior_treatments=["platinum-based chemotherapy", "pembrolizumab"],
        ecog_performance_status=1,
        has_metastatic_disease=True,
        organ_function={"creatinine": "normal", "bilirubin": "normal", "ALT": "mildly elevated"},
        zip_code="10001",
        notes="Previously responded well to immunotherapy. Now progressed. Family in NYC."
    ),
    "PT002": PatientProfile(
        patient_id="PT002",
        age=45,
        sex="Male",
        primary_diagnosis="colorectal cancer",
        secondary_conditions=["hyperlipidemia"],
        current_medications=["atorvastatin", "folic acid"],
        prior_treatments=["FOLFOX", "bevacizumab"],
        ecog_performance_status=0,
        has_metastatic_disease=True,
        organ_function={"creatinine": "normal", "bilirubin": "normal", "ALT": "normal"},
        zip_code="94102",
        notes="MSI-high tumor. KRAS wild-type. Good functional status."
    ),
    "PT003": PatientProfile(
        patient_id="PT003",
        age=67,
        sex="Male",
        primary_diagnosis="prostate cancer",
        secondary_conditions=["atrial fibrillation", "chronic kidney disease stage 2"],
        current_medications=["apixaban", "leuprolide", "enzalutamide"],
        prior_treatments=["radiation therapy", "androgen deprivation therapy"],
        ecog_performance_status=1,
        has_metastatic_disease=True,
        organ_function={"creatinine": "mildly elevated", "bilirubin": "normal"},
        zip_code="60601",
        notes="Castration-resistant prostate cancer. PSA rising on enzalutamide."
    ),
}
