"""
routing.py — Routing node.

Responsibilities:
1. Pull department head contact from Supabase
2. Send formatted profile email to dept head with CV attached
3. Log routing action to audit trail
"""
from state.agent_state import AgentState
from tools.email import send_profile_to_dept_head
from db.queries import get_jd_by_id, log_audit, update_pipeline_run


def routing_node(state: AgentState) -> dict:
    """
    LangGraph node — forwards shortlisted candidate to department head.

    Reads from state:
        run_id, candidate_name, matched_jd_id,
        screening_result, attachment_path, final_decision

    Writes to state:
        current_node
    """
    print(f"\n[Routing] Forwarding profile: {state.get('candidate_name')}")

    run_id        = state.get("run_id", "")
    screening     = state.get("screening_result", {})
    attachment    = state.get("attachment_path", "")

    # ── 1. Get dept head contact from Supabase ────────
    jd = get_jd_by_id(state.get("matched_jd_id", ""))
    if not jd:
        raise ValueError(f"JD not found: {state.get('matched_jd_id')}")

    dept = jd.get("departments", {})
    dept_head_name  = dept.get("head_name", "Department Head")
    dept_head_email = dept.get("head_email", "")

    if not dept_head_email:
        print(f"[Routing] No dept head email found — skipping email")
    else:
        # ── 2. Send profile email ─────────────────────
        send_profile_to_dept_head(
            to_email=dept_head_email,
            dept_head_name=dept_head_name,
            candidate_name=state.get("candidate_name", ""),
            role_title=state.get("matched_jd_title", ""),
            composite_score=state.get("composite_score", 0),
            strengths=screening.get("strengths", []),
            decision_justification=screening.get("decision_justification", ""),
            cv_file_path=attachment if attachment else None,
        )

    # ── 3. Log audit ──────────────────────────────────
    log_audit(
        run_id=run_id,
        node_name="routing",
        action="completed",
        payload={
            "dept_head_email": dept_head_email,
            "dept_head_name": dept_head_name,
            "candidate_name": state.get("candidate_name"),
        }
    )
    update_pipeline_run(run_id=run_id, current_node="routing")

    return {"current_node": "routing"}