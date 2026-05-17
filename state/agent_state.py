"""
agent_state.py — Shared state that flows through every LangGraph node.

Every node receives the full state and returns only the fields it updates.
Nothing is stored in node local variables — everything lives here.
"""
from typing import TypedDict, Optional


class AgentState(TypedDict):

    # ── Email / trigger ───────────────────────────────
    email_id: str                        # Gmail message ID
    email_subject: str                   # Email subject line
    email_body: str                      # Email body text
    email_sender: str                    # Sender email address
    attachment_path: str                 # Local path to extracted CV file

    # ── Classifier output ─────────────────────────────
    has_cv: bool                         # Did we find a CV?
    cv_file_type: str                    # "pdf" or "docx"
    matched_jd_id: str                   # Which JD this CV is matched to
    matched_jd_title: str                # Human readable JD title
    discard_reason: Optional[str]        # Why email was discarded if no CV

    # ── Ingest output ─────────────────────────────────
    candidate_id: str                    # Supabase candidates.id
    raw_cv_text: str                     # Full extracted CV text
    candidate_name: str                  # Parsed from CV
    candidate_email: str                 # Parsed from CV

    # ── Pipeline run ──────────────────────────────────
    run_id: str                          # Supabase pipeline_runs.id
    current_node: str                    # Tracks which node is executing

    # ── Screening output ──────────────────────────────
    screening_result: Optional[dict]     # Full ScreeningResult as dict
    composite_score: Optional[float]     # 0-100 final score
    recommendation: Optional[str]        # SHORTLIST_INTERVIEW | HOLD | REJECT

    # ── Judge output ──────────────────────────────────
    judge_verdict: Optional[dict]        # Full JudgeVerdict as dict
    conflict_flag: Optional[bool]        # True = route to HITL
    conflict_reason: Optional[str]       # Why judge disagrees

    # ── HITL output ───────────────────────────────────
    hitl_reviewed: bool                  # Was this reviewed by a human?
    hitl_final_decision: Optional[str]   # Human's final decision
    hitl_override_reason: Optional[str]  # Why human overrode agents
    reviewed_by: Optional[str]           # HR officer name

    # ── Final decision ────────────────────────────────
    final_decision: str                  # SHORTLIST_INTERVIEW | HOLD | REJECT

    # ── Error handling ────────────────────────────────
    error: Optional[str]                 # Set if any node fails
    error_node: Optional[str]            # Which node failed
    
    # Classifier confidence
    confidence_score:  float             # 0.0 – 1.0 match confidence
    match_status:      str               # AUTO_ASSIGNED | AWAITING_CONFIRMATION | UNMATCHED | MANUALLY_ASSIGNED
    top_jd_matches:    list              # [{jd, score, confidence}] for MEDIUM tier UI
    
    org_id: str 
    
    source: str                          # EMAIL | MANUAL_UPLOAD