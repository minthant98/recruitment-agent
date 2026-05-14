"""
scheduling.py — Scheduling node.

Responsibilities:
1. Send interview invitation email to shortlisted candidate
2. Log scheduling action to audit trail

Note: Google Calendar integration is a future enhancement.
      Requires OAuth setup and is noted in tasks/todo.md.
      For now, HR follows up manually with the time slot.
"""
from state.agent_state import AgentState
from tools.email import send_interview_invite
from db.queries import log_audit, update_pipeline_run


def scheduling_node(state: AgentState) -> dict:
    """
    LangGraph node — sends interview invitation to candidate.

    Reads from state:
        run_id, candidate_name, candidate_email,
        matched_jd_title, final_decision

    Writes to state:
        current_node
    """
    print(f"\n[Scheduling] Sending interview invite to: {state.get('candidate_name')}")

    run_id          = state.get("run_id", "")
    candidate_email = state.get("candidate_email", "")
    candidate_name  = state.get("candidate_name", "")
    role_title      = state.get("matched_jd_title", "")

    # ── 1. Send interview invitation ──────────────────
    if not candidate_email:
        print(f"[Scheduling] No candidate email found — skipping invite")
    else:
        send_interview_invite(
            to_email=candidate_email,
            candidate_name=candidate_name,
            role_title=role_title,
        )

    # ── 2. Log audit ──────────────────────────────────
    log_audit(
        run_id=run_id,
        node_name="scheduling",
        action="completed",
        payload={
            "candidate_email": candidate_email,
            "candidate_name": candidate_name,
            "role_title": role_title,
            "invite_sent": bool(candidate_email),
        }
    )
    update_pipeline_run(
        run_id=run_id,
        current_node="scheduling",
        status="done",
    )

    print(f"[Scheduling] Pipeline complete for: {candidate_name}")

    return {"current_node": "scheduling"}