"""
candidate.py — Pydantic model for structured CV data extracted by the ingest node.
"""
from pydantic import BaseModel, field_validator
from typing import Optional


class CandidateData(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_experience_years: float = 0.0
    relevant_experience_years: float = 0.0
    previous_roles: Optional[list[str]] = []
    industry_exposure: Optional[list[str]] = []
    education: Optional[str] = None
    technical_skills: Optional[list[str]] = []
    soft_skills: Optional[list[str]] = []
    certifications: Optional[list[str]] = []
    languages: Optional[list[str]] = []
    summary: Optional[str] = None

    @field_validator(
        'previous_roles', 'industry_exposure', 'technical_skills',
        'soft_skills', 'certifications', 'languages',
        mode='before'
    )
    @classmethod
    def none_to_empty_list(cls, v):
        """Convert None to empty list for all list fields."""
        if v is None:
            return []
        return v