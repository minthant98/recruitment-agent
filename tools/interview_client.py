"""
Recruitment Agent — Interview Client
Calls the Interview Agent API to launch an interview for a shortlisted candidate.
Env vars read at call time so restarts pick up .env changes immediately.
"""

import logging
import os
import httpx

logger = logging.getLogger(__name__)


async def launch_interview(
    candidate_id: str,
    job_id: str,
    org_id: str,
    candidate_name: str,
    candidate_email: str,
    job_title: str,
    cv_text: str,
    jd_text: str,
    screening_gaps: list[dict],
    recruiter_name: str = "HR Team",
    company_name: str = "Pansy Work",
    questions_target: int = 5,
) -> dict:
    """
    Launch an interview session via the Interview Agent API.
    Returns the launch response including session_id and interview_url.
    Raises on failure.
    """
    # Read at call time — never at import time
    interview_agent_url = os.getenv("INTERVIEW_AGENT_URL", "http://localhost:8001")
    base_url            = os.getenv("INTERVIEW_UI_URL",    "http://localhost:3000")

    payload = {
        "candidate_id":     candidate_id,
        "job_id":           job_id,
        "org_id":           org_id,
        "launched_by":      org_id,  # placeholder until auth is added
        "cv_text":          cv_text or "",
        "jd_text":          jd_text or "",
        "screening_gaps":   screening_gaps or [],
        "questions_target": questions_target,
        "max_turns":        30,
        "candidate_email":  candidate_email or "",
        "candidate_name":   candidate_name,
        "job_title":        job_title,
        "recruiter_name":   recruiter_name,
        "recruiter_title":  "Talent Acquisition",
        "company_name":     company_name,
        "base_url":         base_url,
    }

    print(f"[InterviewClient] Calling: {interview_agent_url}/interviews/launch")
    print(f"[InterviewClient] Candidate: {candidate_name} | Job: {job_title}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{interview_agent_url}/interviews/launch",
            json=payload,
        )

    print(f"[InterviewClient] Response: {resp.status_code}")

    if resp.status_code == 409:
        raise ValueError("An active interview session already exists for this candidate.")

    if resp.status_code != 201:
        raise RuntimeError(
            f"Interview Agent returned {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    logger.info(
        "Interview launched for candidate %s — session %s",
        candidate_name, data.get("session_id")
    )
    return data


def get_hr_dashboard_url(session_id: str = None) -> str:
    """Return the HR dashboard URL."""
    return os.getenv("HR_DASHBOARD_URL", "http://localhost:3001")