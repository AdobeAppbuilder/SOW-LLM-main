from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict

COMPETENCY_KEYS = [
    "workfront_core",
    "workfront_planning",
    "workfront_fusion",
    "integrations",
    "aem",
    "csc",
    "migration",
]

class Competency(BaseModel):
    model_config = ConfigDict(extra='forbid')

    required: bool = False
    weight: float = 0.0
    evidence: List[str] = Field(default_factory=list)
    why: List[str] = Field(default_factory=list)


    @field_validator('weight')
    @classmethod
    def weight_range(cls, v):
        if v < 0 or v > 1:
            raise ValueError('weight must be between 0 and 1')
        return v

class Step1Output(BaseModel):
    model_config = ConfigDict(extra='forbid')

    meta: Dict[str, object]
    timeline: Dict[str, object]
    detected_competencies: Dict[str, Competency]
    notes: List[str] = Field(default_factory=list)

    @field_validator('detected_competencies')
    @classmethod
    def ensure_all_keys_present(cls, v):
        missing = [k for k in COMPETENCY_KEYS if k not in v]
        if missing:
            raise ValueError(f"missing competency keys: {missing}")
        extras = [k for k in v.keys() if k not in COMPETENCY_KEYS]
        if extras:
            raise ValueError(f"unexpected competency keys: {extras}")
        return v

    @field_validator('detected_competencies')
    @classmethod
    def weights_sum_to_one(cls, v):
        total = sum(float(v[k].weight) for k in v)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total}")
        return v

    @field_validator('detected_competencies')
    @classmethod
    def required_has_evidence(cls, v):
        for k, c in v.items():
            if c.required and not c.evidence:
                raise ValueError(f"{k} is required but has no evidence")
        return v
