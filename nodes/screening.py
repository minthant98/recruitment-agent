"""
screening.py — Screening node.

Responsibilities:
1. Pull JD and criteria from Supabase
2. Build dynamic prompt from JD criteria
3. Call Groq screener (temp=0, deterministic)
4. Validate output against ScreeningResult Pydantic schema
5. Save to screening_results table
6. Update state with score and recommendation
"""
import json
from datetime import datetime, timezone

from groq import Groq

from config import get_settings
from state.agent_state import AgentState
from schemas.screening import ScreeningResult
from prompts.screener import SCREENER_SYSTEM_PROMPT, build_screener_user_prompt
from db.queries import (
    get_jd_by_id,
    get_criteria_by_jd,
    insert_screening_result,
    log_audit,
    update_pipeline_run,
)


def call_groq_screener(system_prompt: str, user_prompt: str) -> dict:
    """
    Call Groq screener model and return parsed JSON dict.
    Temperature = 0 for deterministic scoring.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    response = client.chat.completions.create(
        model=settings.groq_screener_model,
        temperature=settings.groq_screener_temperature,
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


def screening_node(state: AgentState) -> dict:
    """
    LangGraph node — scores candidate CV against JD using Groq.

    Reads from state:
        run_id, candidate_id, raw_cv_text, matched_jd_id, matched_jd_title

    Writes to state:
        screening_result, composite_score, recommendation, current_node
    """
    print(f"\n[Screening] Scoring: {state.get('candidate_name')} "
          f"for {state.get('matched_jd_title')}")

    run_id = state.get("run_id", "")
    matched_jd_id = state.get("matched_jd_id", "")
    raw_cv_text = state.get("raw_cv_text", "")

    # ── 1. Pull JD and criteria from Supabase ─────────
    jd = get_jd_by_id(matched_jd_id)
    if not jd:
        raise ValueError(f"JD not found in database: {matched_jd_id}")

    criteria = get_criteria_by_jd(matched_jd_id)
    if not criteria:
        raise ValueError(f"No screening criteria found for JD: {matched_jd_id}")

    print(f"[Screening] Loaded JD: {jd['role_title']} with {len(criteria)} criteria")

    # ── 2. Build prompt ───────────────────────────────
    # Inject current datetime into prompt so model uses it for screened_at
    now_utc = datetime.now(timezone.utc).isoformat()

    user_prompt = build_screener_user_prompt(
        raw_cv_text=raw_cv_text,
        jd_title=jd["role_title"],
        jd_raw_text=jd.get("raw_text", ""),
        required_years=jd.get("required_years"),
        criteria=criteria,
        jd_id=matched_jd_id,
    )

    # Add current time hint to system prompt
    system_prompt = SCREENER_SYSTEM_PROMPT + f"\nCurrent UTC time: {now_utc}"

    # ── 3. Call Groq ──────────────────────────────────
    print(f"[Screening] Calling Groq screener model...")
    raw_result = call_groq_screener(system_prompt, user_prompt)

    # ── 4. Validate with Pydantic ─────────────────────
    screening_result = ScreeningResult(**raw_result)
    print(f"[Screening] Score: {screening_result.composite_score:.1f} | "
          f"Recommendation: {screening_result.recommendation}")

    # ── 5. Save to Supabase ───────────────────────────
    result_dict = screening_result.model_dump()
    insert_screening_result(
        run_id=run_id,
        screening=result_dict,
    )
    print(f"[Screening] Result saved to Supabase")

    # ── 6. Log audit ──────────────────────────────────
    log_audit(
        run_id=run_id,
        node_name="screening",
        action="completed",
        payload={
            "composite_score": screening_result.composite_score,
            "recommendation": screening_result.recommendation,
            "experience_match_rating": screening_result.experience_analysis.experience_match_rating,
        }
    )
    update_pipeline_run(run_id=run_id, current_node="screening")

    return {
        "screening_result": result_dict,
        "composite_score": screening_result.composite_score,
        "recommendation": screening_result.recommendation.value,
        "current_node": "screening",
    }