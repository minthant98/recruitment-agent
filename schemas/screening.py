"""
screening.py — Pydantic models for the screening node output.
Derived from the screener prompt structure.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ExperienceMatch(str, Enum):
    STRONG = "STRONG_MATCH"
    PARTIAL = "PARTIAL_MATCH"
    WEAK = "WEAK_MATCH"


class Recommendation(str, Enum):
    SHORTLIST = "SHORTLIST_INTERVIEW"
    HOLD = "HOLD"
    REJECT = "REJECT"


class SkillsAnalysis(BaseModel):
    matched_required: list[str] = []
    missing_required: list[str] = []
    matched_preferred: list[str] = []
    transferable: list[str] = []
    skills_match_score: float = Field(ge=0, le=100)


class ExperienceAnalysis(BaseModel):
    required_years: float = 0.0        # ← add default
    candidate_years: float = 0.0       # ← add default
    role_similarity: str = ""
    scope_of_responsibility: str = ""
    industry_alignment: str = ""
    career_progression: str = ""
    experience_match_rating: ExperienceMatch = ExperienceMatch.WEAK


class ScreeningResult(BaseModel):
    # Candidate summary
    candidate_name: str
    total_experience_years: float = 0.0        # ← add default
    relevant_experience_years: float = 0.0     # ← add default
    previous_roles: list[str] = []
    industry_exposure: list[str] = []
    education: Optional[str] = None

    # Analysis
    skills_analysis: SkillsAnalysis
    experience_analysis: ExperienceAnalysis

    # Scoring — 4 components exposed for judge to critique
    required_skills_score: float = Field(ge=0, le=100)   # 40%
    experience_score: float = Field(ge=0, le=100)         # 40%
    preferred_skills_score: float = Field(ge=0, le=100)   # 10%
    education_domain_score: float = Field(ge=0, le=100)   # 10%
    composite_score: float = Field(ge=0, le=100)

    # Strengths and risks
    strengths: list[str] = []
    weaknesses: list[str] = []

    # Final output
    recommendation: Recommendation
    decision_justification: str

    # Pipeline metadata
    jd_id: str
    screened_at: str