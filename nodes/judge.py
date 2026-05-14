"""
judge.py — Judge node.

Responsibilities:
1. Receive full ScreeningResult from state
2. Pull JD and CV from Supabase/state
3. Call Groq judge model to critique screener
4. Validate output against JudgeVerdict Pydantic schema
5. Set conflict_flag — drives the conditional edge to HITL or auto-pass
6. Save to judge_verdicts table
"""
import json

from groq import Groq

from config import get_settings
from state.agent_state import AgentState
from schemas.judge import JudgeVerdict
from prompts.judge import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt
from db.queries import (
    get_jd_by_id,
    insert_judge_verdict,
    log_audit,
    update_pipeline_run,
)


def call_groq_judge(system_prompt: str, user_prompt: str) -> dict:
    """
    Call Groq judge model and return parsed JSON dict.
    Temperature = 0.3 so judge genuinely challenges the screener.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    response = client.chat.completions.create(
        model=settings.groq_judge_model,
        temperature=settings.groq_judge_temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw_output = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw_output.startswith("```"):
        raw_output = raw_output.split("```")[1]
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]

    return json.loads(raw_output.strip())


def judge_node(state: AgentState) -> dict:
    """
    LangGraph node — critiques screener output and sets conflict flag.

    Reads from state:
        run_id, raw_cv_text, matched_jd_id, screening_result,
        candidate_name, composite_score, recommendation

    Writes to state:
        judge_verdict, conflict_flag, conflict_reason,
        final_decision, current_node
    """
    print(f"\n[Judge] Reviewing screening decision for: {state.get('candidate_name')}")
    print(f"[Judge] Screener recommendation: {state.get('recommendation')} "
          f"(score: {state.get('composite_score')})")

    run_id = state.get("run_id", "")
    matched_jd_id = state.get("matched_jd_id", "")
    raw_cv_text = state.get("raw_cv_text", "")
    screening_result = state.get("screening_result", {})

    # ── 1. Pull JD from Supabase ──────────────────────
    jd = get_jd_by_id(matched_jd_id)
    if not jd:
        raise ValueError(f"JD not found: {matched_jd_id}")

    # ── 2. Build judge prompt ─────────────────────────
    user_prompt = build_judge_user_prompt(
        jd_title=jd["role_title"],
        jd_raw_text=jd.get("raw_text", ""),
        raw_cv_text=raw_cv_text,
        screening_result=screening_result,
    )

    # ── 3. Call Groq judge ────────────────────────────
    print(f"[Judge] Calling Groq judge model...")
    raw_verdict = call_groq_judge(JUDGE_SYSTEM_PROMPT, user_prompt)

    # ── 4. Validate with Pydantic ─────────────────────
    judge_verdict = JudgeVerdict(**raw_verdict)
    conflict_flag = judge_verdict.conflict_flag

    print(f"[Judge] Overall agrees: {judge_verdict.overall_agrees} | "
          f"Conflict: {conflict_flag} | "
          f"Suggested: {judge_verdict.suggested_recommendation}")

    if conflict_flag:
        print(f"[Judge] Conflict reason: {judge_verdict.conflict_reason}")

    # ── 5. Determine final decision ───────────────────
    # If no conflict, screener recommendation stands
    # If conflict, HITL will set the final decision
    final_decision = state.get("recommendation", "REJECT")
    if not conflict_flag:
        # Judge agrees — screener recommendation is final
        final_decision = judge_verdict.suggested_recommendation.value

    # ── 6. Save to Supabase ───────────────────────────
    verdict_dict = judge_verdict.model_dump()
    insert_judge_verdict(run_id=run_id, verdict=verdict_dict)
    print(f"[Judge] Verdict saved to Supabase")

    # ── 7. Log audit ──────────────────────────────────
    log_audit(
        run_id=run_id,
        node_name="judge",
        action="completed",
        payload={
            "overall_agrees": judge_verdict.overall_agrees,
            "conflict_flag": conflict_flag,
            "suggested_recommendation": judge_verdict.suggested_recommendation,
            "confidence": judge_verdict.confidence,
        }
    )
    update_pipeline_run(run_id=run_id, current_node="judge")

    return {
        "judge_verdict": verdict_dict,
        "conflict_flag": conflict_flag,
        "conflict_reason": judge_verdict.conflict_reason,
        "final_decision": final_decision,
        "current_node": "judge",
    }