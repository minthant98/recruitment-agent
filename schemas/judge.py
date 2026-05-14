"""
judge.py — Pydantic models for the judge node output.
"""
from pydantic import BaseModel, Field
from typing import Optional
from schemas.screening import Recommendation


class CriterionVerdict(BaseModel):
    criterion: str           # e.g. "required_skills_score"
    screener_value: float    # what the screener gave
    judge_agrees: bool       # does the judge agree?
    judge_comment: str       # why or why not


class JudgeVerdict(BaseModel):
    candidate_name: str
    criterion_verdicts: list[CriterionVerdict]
    overall_agrees: bool
    suggested_recommendation: Recommendation
    conflict_flag: bool      # True = route to HITL
    conflict_reason: Optional[str] = None
    confidence: float = Field(ge=0, le=100)