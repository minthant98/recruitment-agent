"""
hitl.py — Human-in-the-Loop checkpoint node.

Uses LangGraph's interrupt() to pause the pipeline and wait
for an HR officer to review conflicted screening decisions.

How it works:
1. interrupt() pauses execution and surfaces the conflict to the caller
2. The caller (main.py) displays the conflict in the CLI
3. HR officer inputs their decision
4. graph.invoke() is called again with the human's decision in state
5. Pipeline resumes from this node with the override applied
"""
from langgraph.types import interrupt

from state.agent_state import AgentState
from db.queries import (
    insert_hitl_review,
    log_audit,
    update_pipeline_run,
)


# Valid decisions HR can make
VALID_DECISIONS = ["SHORTLIST_INTERVIEW", "HOLD", "REJECT"]


def format_conflict_summary(state: AgentState) -> str:
    """
    Format a clear conflict summary for the HR reviewer.
    Shows screener vs judge side by side.
    """
    screening = state.get("screening_result", {})
    judge = state.get("judge_verdict", {})

    screener_rec = state.get("recommendation", "N/A")
    judge_rec = judge.get("suggested_recommendation", "N/A")
    conflict_reason = state.get("conflict_reason", "No reason provided")

    lines = [
        "=" * 60,
        "  HITL REVIEW REQUIRED — CONFLICT DETECTED",
        "=" * 60,
        f"  Candidate:    {state.get('candidate_name')}",
        f"  Role:         {state.get('matched_jd_title')}",
        f"  Composite Score: {state.get('composite_score')}",
        "-" * 60,
        "  SCORING BREAKDOWN",
        f"  Required Skills:  {screening.get('required_skills_score')} / 100",
        f"  Experience:       {screening.get('experience_score')} / 100",
        f"  Preferred Skills: {screening.get('preferred_skills_score')} / 100",
        f"  Education:        {screening.get('education_domain_score')} / 100",
        "-" * 60,
        "  SCREENER vs JUDGE",
        f"  Screener:  {screener_rec}",
        f"  Judge:     {judge_rec}",
        f"  Conflict:  {conflict_reason}",
        "-" * 60,
        "  CRITERION VERDICTS",
    ]

    for cv in judge.get("criterion_verdicts", []):
        agrees = "✅" if cv.get("judge_agrees") else "❌"
        lines.append(
            f"  {agrees} {cv.get('criterion')}: "
            f"{cv.get('screener_value')} — {cv.get('judge_comment')}"
        )

    lines += [
        "-" * 60,
        "  STRENGTHS:",
    ]
    for s in screening.get("strengths", []):
        lines.append(f"    + {s}")

    lines += ["  WEAKNESSES / RISKS:"]
    for w in screening.get("weaknesses", []):
        lines.append(f"    - {w}")

    lines.append("=" * 60)
    return "\n".join(lines)


def hitl_node(state: AgentState) -> dict:
    """
    LangGraph node — pauses pipeline for human review.

    Uses interrupt() to surface the conflict.
    The caller must resume the graph with:
        {
            "hitl_final_decision": "SHORTLIST_INTERVIEW|HOLD|REJECT",
            "hitl_override_reason": "optional reason string",
            "reviewed_by": "HR officer name",
            "hitl_reviewed": True,
        }

    Reads from state:
        run_id, candidate_name, matched_jd_title,
        screening_result, judge_verdict, conflict_reason

    Writes to state:
        hitl_reviewed, hitl_final_decision, hitl_override_reason,
        reviewed_by, final_decision, current_node
    """
    run_id = state.get("run_id", "")
    final_decision  = state.get("hitl_final_decision", "REJECT")
    reviewed_by     = state.get("reviewed_by", "HR Officer")
    override_reason = state.get("hitl_override_reason", "")
    screener_rec    = state.get("recommendation", "")
    was_overridden  = final_decision != screener_rec

    print(f"\n[HITL] Review completed by: {reviewed_by}")
    print(f"[HITL] Final decision: {final_decision}")

    insert_hitl_review(
        run_id=run_id,
        reviewed_by=reviewed_by,
        final_decision=final_decision,
        override_reason=override_reason if override_reason else None,
        was_overridden=was_overridden,
    )

    log_audit(
        run_id=run_id,
        node_name="hitl",
        action="reviewed",
        payload={
            "final_decision":   final_decision,
            "reviewed_by":      reviewed_by,
            "was_overridden":   was_overridden,
            "override_reason":  override_reason,
        }
    )
    update_pipeline_run(run_id=run_id, current_node="hitl")

    return {
        "final_decision": final_decision,
        "hitl_reviewed":  True,
        "current_node":   "hitl",
    }
    # ── First pass — interrupt and wait for human ─────
    print(f"\n[HITL] Pausing pipeline for human review...")
    update_pipeline_run(run_id=run_id, current_node="hitl_pending")

    log_audit(
        run_id=run_id,
        node_name="hitl",
        action="interrupted",
        payload={
            "candidate_name": state.get("candidate_name"),
            "conflict_reason": state.get("conflict_reason"),
        }
    )

    # Surface conflict summary to the caller via interrupt()
    conflict_summary = format_conflict_summary(state)
    interrupt(conflict_summary)

    # Code below this line only runs after resume
    # (unreachable on first pass — LangGraph handles this)
    return {}