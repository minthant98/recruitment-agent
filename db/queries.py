"""
Typed query helpers — one function per table operation.
Every node imports from here instead of writing raw Supabase calls.
"""
import json
from uuid import UUID
from datetime import datetime
from db.client import get_db


# ── departments ───────────────────────────────────────────────────

def insert_department(name: str, head_name: str, head_email: str) -> dict:
    db = get_db()
    result = db.table("departments").insert({
        "name": name,
        "head_name": head_name,
        "head_email": head_email,
    }).execute()
    return result.data[0]


def get_department_by_name(name: str) -> dict | None:
    db = get_db()
    result = db.table("departments").select("*").eq("name", name).execute()
    return result.data[0] if result.data else None


def get_department_by_id(dept_id: str) -> dict | None:
    db = get_db()
    result = db.table("departments").select("*").eq("id", dept_id).execute()
    return result.data[0] if result.data else None


# ── job_descriptions ──────────────────────────────────────────────

def insert_job_description(
    dept_id: str,
    role_title: str,
    seniority_level: str | None,
    required_years: float | None,
    raw_text: str,
    source_file: str,
) -> dict:
    db = get_db()
    result = db.table("job_descriptions").insert({
        "dept_id": dept_id,
        "role_title": role_title,
        "seniority_level": seniority_level,
        "required_years": required_years,
        "raw_text": raw_text,
        "source_file": source_file,
    }).execute()
    return result.data[0]


def get_all_job_descriptions(org_id: str | None = None) -> list[dict]:
    db = get_db()
    query = db.table("job_descriptions").select(
        "*, departments(name, head_name, head_email)"
    )
    if org_id:
        query = query.eq("org_id", org_id)
    return query.execute().data

def get_jd_by_id(jd_id: str) -> dict | None:
    db = get_db()
    result = db.table("job_descriptions").select(
        "*, departments(name, head_name, head_email)"
    ).eq("id", jd_id).execute()
    return result.data[0] if result.data else None


# ── screening_criteria ────────────────────────────────────────────

def insert_screening_criteria(jd_id: str, criteria: list[dict]) -> list[dict]:
    """Insert multiple criteria rows for a JD at once."""
    db = get_db()
    rows = [{"jd_id": jd_id, **c} for c in criteria]
    result = db.table("screening_criteria").insert(rows).execute()
    return result.data


def get_criteria_by_jd(jd_id: str) -> list[dict]:
    db = get_db()
    result = db.table("screening_criteria").select("*").eq("jd_id", jd_id).execute()
    return result.data


# ── candidates ────────────────────────────────────────────────────

def insert_candidate(data: dict) -> dict:
    db = get_db()
    row = {
        "name":                     data["name"],
        "email":                    data.get("email"),
        "total_experience_years":   data.get("total_experience_years"),
        "relevant_experience_years": data.get("relevant_experience_years"),
        "previous_roles":           data.get("previous_roles", []),
        "industry_exposure":        data.get("industry_exposure", []),
        "education":                data.get("education"),
        "raw_cv_text":              data.get("raw_cv_text"),
        "structured_cv":            data.get("structured_cv"),
        "source_email_id":          data.get("source_email_id"),
        "org_id":                   data.get("org_id"),   # ← new
    }
    result = db.table("candidates").insert(row).execute()
    return result.data[0]


def get_candidate_by_id(candidate_id: str) -> dict | None:
    db = get_db()
    result = db.table("candidates").select("*").eq("id", candidate_id).execute()
    return result.data[0] if result.data else None


# ── pipeline_runs ─────────────────────────────────────────────────

def insert_pipeline_run(
    candidate_id: str,
    jd_id: str,
    org_id: str | None = None,
    confidence_score: float | None = None,
    match_status: str = "AUTO_ASSIGNED",
    source: str = "EMAIL",
) -> dict:
    db = get_db()
    result = db.table("pipeline_runs").insert({
        "candidate_id":    candidate_id,
        "jd_id":           jd_id,
        "current_node":    "classifier",
        "status":          "in_progress",
        "org_id":          org_id,            # ← new
        "confidence_score": confidence_score,  # ← new
        "match_status":    match_status,       # ← new
        "source":          source,             # ← new
    }).execute()
    return result.data[0]


def update_pipeline_run(run_id: str, current_node: str, status: str = "in_progress") -> dict:
    db = get_db()
    result = db.table("pipeline_runs").update({
        "current_node": current_node,
        "status": status,
    }).eq("id", run_id).execute()
    return result.data[0]


def get_pipeline_run(run_id: str) -> dict | None:
    db = get_db()
    result = db.table("pipeline_runs").select("*").eq("id", run_id).execute()
    return result.data[0] if result.data else None


# ── screening_results ─────────────────────────────────────────────

def insert_screening_result(run_id: str, screening: dict) -> dict:
    db = get_db()
    result = db.table("screening_results").insert({
        "run_id": run_id,
        "required_skills_score": screening.get("required_skills_score"),
        "experience_score": screening.get("experience_score"),
        "preferred_skills_score": screening.get("preferred_skills_score"),
        "education_domain_score": screening.get("education_domain_score"),
        "composite_score": screening.get("composite_score"),
        "experience_match_rating": screening.get("experience_match_rating"),
        "skills_analysis": screening.get("skills_analysis"),
        "experience_analysis": screening.get("experience_analysis"),
        "strengths": screening.get("strengths"),
        "weaknesses": screening.get("weaknesses"),
        "recommendation": screening.get("recommendation"),
        "decision_justification": screening.get("decision_justification"),
        "full_screener_output": screening,
    }).execute()
    return result.data[0]


def get_screening_result(run_id: str) -> dict | None:
    db = get_db()
    result = db.table("screening_results").select("*").eq("run_id", run_id).execute()
    return result.data[0] if result.data else None


# ── judge_verdicts ────────────────────────────────────────────────

def insert_judge_verdict(run_id: str, verdict: dict) -> dict:
    db = get_db()
    result = db.table("judge_verdicts").insert({
        "run_id": run_id,
        "criterion_verdicts": verdict.get("criterion_verdicts"),
        "overall_agrees": verdict.get("overall_agrees"),
        "suggested_recommendation": verdict.get("suggested_recommendation"),
        "conflict_flag": verdict.get("conflict_flag", False),
        "conflict_reason": verdict.get("conflict_reason"),
        "confidence": verdict.get("confidence"),
    }).execute()
    return result.data[0]


def get_judge_verdict(run_id: str) -> dict | None:
    db = get_db()
    result = db.table("judge_verdicts").select("*").eq("run_id", run_id).execute()
    return result.data[0] if result.data else None


# ── hitl_reviews ──────────────────────────────────────────────────

def insert_hitl_review(
    run_id: str,
    reviewed_by: str,
    final_decision: str,
    override_reason: str | None,
    was_overridden: bool,
) -> dict:
    db = get_db()
    result = db.table("hitl_reviews").insert({
        "run_id": run_id,
        "reviewed_by": reviewed_by,
        "final_decision": final_decision,
        "override_reason": override_reason,
        "was_overridden": was_overridden,
    }).execute()
    return result.data[0]


# ── audit_log ─────────────────────────────────────────────────────

def log_audit(run_id: str, node_name: str, action: str, payload: dict | None = None) -> dict:
    """Call this at the end of every node to write the audit trail."""
    db = get_db()
    result = db.table("audit_log").insert({
        "run_id": run_id,
        "node_name": node_name,
        "action": action,
        "payload": payload or {},
    }).execute()
    return result.data[0]


def get_audit_trail(run_id: str) -> list[dict]:
    db = get_db()
    result = db.table("audit_log").select("*").eq(
        "run_id", run_id
    ).order("created_at").execute()
    return result.data