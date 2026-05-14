"""
audit.py — Audit node.

Responsibilities:
1. Collect all pipeline data from state
2. Append row to Excel HR audit sheet
3. Update pipeline_run status to done
4. Log final audit entry to Supabase
"""
from datetime import datetime, timezone

from config import get_settings
from state.agent_state import AgentState
from tools.excel import append_audit_row
from db.queries import (
    get_jd_by_id,
    log_audit,
    update_pipeline_run,
)


def audit_node(state: AgentState) -> dict:
    """
    LangGraph node — writes final audit record to Excel and Supabase.

    Reads from state:
        All fields — this node is the final recorder

    Writes to state:
        current_node, pipeline_status
    """
    settings = get_settings()
    run_id = state.get("run_id", "")
    final_decision = state.get("final_decision", "REJECT")

    print(f"\n[Audit] Recording final decision: {final_decision} "
          f"for {state.get('candidate_name')}")

    # ── 1. Pull JD details for audit row ─────────────
    jd = get_jd_by_id(state.get("matched_jd_id", ""))
    jd_title = jd["role_title"] if jd else state.get("matched_jd_title", "")
    department = ""
    if jd and jd.get("departments"):
        department = jd["departments"].get("name", "")

    # ── 2. Unpack nested dicts from state ─────────────
    screening = state.get("screening_result", {})
    judge = state.get("judge_verdict", {})
    skills = screening.get("skills_analysis", {})
    exp = screening.get("experience_analysis", {})

    # ── 3. Build audit row ────────────────────────────
    row_data = {
        # Pipeline metadata
        "run_id":           run_id,
        "reviewed_at":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),

        # Candidate info
        "candidate_name":               state.get("candidate_name", ""),
        "candidate_email":              state.get("candidate_email", ""),
        "total_experience_years":       screening.get("total_experience_years", ""),
        "relevant_experience_years":    screening.get("relevant_experience_years", ""),
        "previous_roles":               screening.get("previous_roles", []),
        "education":                    screening.get("education", ""),

        # JD info
        "jd_title":     jd_title,
        "department":   department,

        # Screening scores
        "required_skills_score":    screening.get("required_skills_score", ""),
        "experience_score":         screening.get("experience_score", ""),
        "preferred_skills_score":   screening.get("preferred_skills_score", ""),
        "education_domain_score":   screening.get("education_domain_score", ""),
        "composite_score":          screening.get("composite_score", ""),
        "experience_match_rating":  exp.get("experience_match_rating", ""),

        # Screener output
        "matched_required_skills":  skills.get("matched_required", []),
        "missing_required_skills":  skills.get("missing_required", []),
        "strengths":                screening.get("strengths", []),
        "weaknesses":               screening.get("weaknesses", []),
        "screener_recommendation":  screening.get("recommendation", ""),
        "decision_justification":   screening.get("decision_justification", ""),

        # Judge output
        "judge_overall_agrees":          judge.get("overall_agrees", ""),
        "judge_suggested_recommendation": judge.get("suggested_recommendation", ""),
        "conflict_flag":                 judge.get("conflict_flag", False),
        "conflict_reason":               state.get("conflict_reason", ""),
        "judge_confidence":              judge.get("confidence", ""),

        # HR decision
        "hr_final_decision":    final_decision,
        "hr_reviewed_by":       state.get("reviewed_by", ""),
        "hr_override_reason":   state.get("hitl_override_reason", ""),
        "was_overridden":       state.get("hitl_override_reason", "") != "",

        # Pipeline path
        "hitl_reviewed":    state.get("hitl_reviewed", True),
        "pipeline_status":  "done",
    }

    # ── 4. Write to Excel ─────────────────────────────
    row_num = append_audit_row(
        file_path=settings.audit_excel_path,
        row_data=row_data,
    )
    print(f"[Audit] Written to Excel row {row_num}: {settings.audit_excel_path}")

    # ── 5. Update pipeline run status ─────────────────
    update_pipeline_run(
        run_id=run_id,
        current_node="audit",
        status="done",
    )

    # ── 6. Log to Supabase audit trail ────────────────
    log_audit(
        run_id=run_id,
        node_name="audit",
        action="completed",
        payload={
            "final_decision": final_decision,
            "composite_score": screening.get("composite_score"),
            "excel_row": row_num,
            "excel_path": settings.audit_excel_path,
        }
    )

    print(f"[Audit] Pipeline run {run_id} marked as done")

    return {
        "current_node": "audit",
        "pipeline_status": "done",
    }