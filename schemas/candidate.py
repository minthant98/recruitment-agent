"""
candidate.py — Pydantic model for structured CV data extracted by the ingest node.
"""
from pydantic import BaseModel
from typing import Optional


class CandidateData(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_experience_years: float = 0.0
    relevant_experience_years: float = 0.0
    previous_roles: list[str] = []
    industry_exposure: list[str] = []
    education: Optional[str] = None
    technical_skills: list[str] = []
    soft_skills: list[str] = []
    certifications: list[str] = []
    languages: list[str] = []
    summary: Optional[str] = None