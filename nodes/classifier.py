"""
classifier.py — Classifier node.

Responsibilities:
1. Detect if the email has a CV attachment (.pdf or .docx)
2. Match the email to the correct JD using confidence scoring
3. Set match_status based on confidence tier:
      HIGH   → AUTO_ASSIGNED        (screening runs immediately)
      MEDIUM → AWAITING_CONFIRMATION (recruiter confirms job first)
      LOW    → UNMATCHED            (recruiter assigns manually)
4. Route to ingest (HIGH), confirmation_pause (MEDIUM), or unmatched_queue (LOW)

Manual uploads bypass all classification — job is already chosen by recruiter.
No LLM needed — purely rule-based + keyword scoring.
"""
import os
from pathlib import Path

from db.queries import get_all_job_descriptions, log_audit, update_pipeline_run
from state.agent_state import AgentState
from utils.text import clean_text, fuzzy_match_jd_scored

# Supported CV file extensions
CV_EXTENSIONS = {".pdf", ".docx", ".doc"}

# Confidence thresholds
THRESHOLD_HIGH   = 0.80
THRESHOLD_MEDIUM = 0.50


def is_cv_file(filename: str) -> bool:
    path = Path(filename)
    ext = path.suffix.lower()
    if ext not in CV_EXTENSIONS:
        return False
    non_cv_keywords = ["invoice", "receipt", "contract", "agreement", "report", "minutes"]
    name_lower = path.stem.lower()
    for keyword in non_cv_keywords:
        if keyword in name_lower:
            return False
    return True


def classifier_node(state: AgentState) -> dict:
    # ── Manual upload bypass ──────────────────────────────────────
    if state.get("source") == "MANUAL_UPLOAD":
        print(f"\n[Classifier] Manual upload — skipping classification")
        print(f"[Classifier] Job: {state.get('matched_jd_title')}")
        print(f"[Classifier] File: {state.get('attachment_path')}")
        return {
            "has_cv":            True,
            "cv_file_type":      Path(state.get("attachment_path", "")).suffix.lower().lstrip("."),
            "attachment_path":   state.get("attachment_path", ""),
            "matched_jd_id":     state.get("matched_jd_id", ""),
            "matched_jd_title":  state.get("matched_jd_title", ""),
            "confidence_score":  1.0,
            "match_status":      "MANUALLY_ASSIGNED",
            "top_jd_matches":    [],
            "discard_reason":    None,
            "current_node":      "classifier",
        }

    # ── Email intake classification ───────────────────────────────
    print(f"\n[Classifier] From: {state.get('email_sender')}")
    print(f"[Classifier] Subject: {state.get('email_subject')}")

    attachment_path = state.get("attachment_path", "")
    has_cv          = False
    cv_file_type    = ""
    discard_reason  = None

    if attachment_path and os.path.exists(attachment_path):
        filename = Path(attachment_path).name
        if is_cv_file(filename):
            has_cv       = True
            cv_file_type = Path(attachment_path).suffix.lower().lstrip(".")
            print(f"[Classifier] CV found: {filename} ({cv_file_type})")
        else:
            discard_reason = f"Attachment '{filename}' is not a recognised CV file"
            print(f"[Classifier] Not a CV: {filename}")
    else:
        discard_reason = "No attachment found in email"
        print(f"[Classifier] No attachment")

    matched_jd_id    = ""
    matched_jd_title = ""
    confidence_score = 0.0
    match_status     = "UNMATCHED"
    top_jd_matches   = []

    if has_cv:
        jd_list = get_all_job_descriptions()

        if not jd_list:
            has_cv         = False
            discard_reason = "No job descriptions found in database"
            print(f"[Classifier] No JDs in database — discarding")
        else:
            result = fuzzy_match_jd_scored(
                email_subject=state.get("email_subject", ""),
                email_body=clean_text(state.get("email_body", "")),
                jd_list=jd_list,
            )

            confidence_score = result["confidence"]
            tier             = result["tier"]
            top_jd_matches   = result["top_matches"]

            print(f"[Classifier] Confidence: {confidence_score:.0%} → tier: {tier}")

            if tier == "HIGH":
                best             = top_jd_matches[0]["jd"]
                matched_jd_id    = best["id"]
                matched_jd_title = best["role_title"]
                match_status     = "AUTO_ASSIGNED"
                print(f"[Classifier] AUTO_ASSIGNED → {matched_jd_title}")

            elif tier == "MEDIUM":
                best             = top_jd_matches[0]["jd"]
                matched_jd_id    = best["id"]
                matched_jd_title = best["role_title"]
                match_status     = "AWAITING_CONFIRMATION"
                print(f"[Classifier] AWAITING_CONFIRMATION → top pick: {matched_jd_title}")

            else:
                match_status = "UNMATCHED"
                print(f"[Classifier] UNMATCHED — no confident JD found")

    run_id = state.get("run_id", "")
    if run_id:
        log_audit(
            run_id=run_id,
            node_name="classifier",
            action="completed" if has_cv else "discarded",
            payload={
                "has_cv":           has_cv,
                "cv_file_type":     cv_file_type,
                "confidence_score": confidence_score,
                "match_status":     match_status,
                "matched_jd_title": matched_jd_title,
                "discard_reason":   discard_reason,
            },
        )
        update_pipeline_run(run_id=run_id, current_node="classifier")

    return {
        "has_cv":            has_cv,
        "cv_file_type":      cv_file_type,
        "attachment_path":   attachment_path,
        "matched_jd_id":     matched_jd_id,
        "matched_jd_title":  matched_jd_title,
        "confidence_score":  confidence_score,
        "match_status":      match_status,
        "top_jd_matches":    top_jd_matches,
        "discard_reason":    discard_reason,
        "current_node":      "classifier",
    }