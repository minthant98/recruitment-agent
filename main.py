"""
main.py — Recruitment Agent entry point.

Starts two things:
1. FastAPI web UI server (background thread)
2. Gmail polling loop (main thread)

Usage:
    python main.py          # run pipeline loop + web UI
    python main.py --once   # process one batch and exit
"""
import os
import time
import argparse
import threading
import sqlite3
from datetime import datetime

import uvicorn

from graph import build_graph
from tools.gmail_poller import get_unread_cv_emails
from tools.email import send_hitl_notification
from db.queries import update_pipeline_run, log_audit
from config import get_settings
from ui.app import app as fastapi_app, set_resume_callback


POLL_INTERVAL   = 60
WEB_UI_BASE_URL = "http://localhost:8000"
CHECKPOINT_DB   = "checkpoints.db"

# ── Shared graph instance ─────────────────────────────────────────
# Module-level so polling loop and web UI share the
# same SqliteSaver checkpoint store.

_pipeline_app = None


def get_pipeline_app():
    global _pipeline_app
    if _pipeline_app is None:
        from langgraph.checkpoint.sqlite import SqliteSaver
        conn         = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        graph        = build_graph()
        _pipeline_app = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["hitl", "confirmation_pause", "unmatched_queue"],
        )
    return _pipeline_app


# ── Persistent thread mapping ─────────────────────────────────────
# Maps Supabase run_id → LangGraph thread_id (email_id)
# Stored in SQLite so it survives process restarts.

def _ensure_mapping_table():
    conn = sqlite3.connect(CHECKPOINT_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thread_mapping (
            run_id    TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _save_thread_mapping(run_id: str, thread_id: str):
    _ensure_mapping_table()
    conn = sqlite3.connect(CHECKPOINT_DB)
    conn.execute(
        "INSERT OR REPLACE INTO thread_mapping (run_id, thread_id) VALUES (?, ?)",
        (run_id, thread_id),
    )
    conn.commit()
    conn.close()


def _get_thread_id(run_id: str) -> str | None:
    try:
        _ensure_mapping_table()
        conn   = sqlite3.connect(CHECKPOINT_DB)
        cursor = conn.execute(
            "SELECT thread_id FROM thread_mapping WHERE run_id = ?", (run_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _delete_thread_mapping(run_id: str):
    try:
        conn = sqlite3.connect(CHECKPOINT_DB)
        conn.execute("DELETE FROM thread_mapping WHERE run_id = ?", (run_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Initial state builders ────────────────────────────────────────

def get_initial_state(email_data: dict) -> dict:
    """Build the initial AgentState from incoming email data."""
    return {
        "email_id":             email_data["email_id"],
        "email_subject":        email_data["email_subject"],
        "email_sender":         email_data["email_sender"],
        "email_body":           email_data["email_body"],
        "attachment_path":      email_data["attachment_path"],
        "cv_file_type":         email_data["cv_file_type"],
        "has_cv":               False,
        "matched_jd_id":        "",
        "matched_jd_title":     "",
        "confidence_score":     0.0,
        "match_status":         "",
        "top_jd_matches":       [],
        "discard_reason":       None,
        "candidate_id":         "",
        "run_id":               "",
        "raw_cv_text":          "",
        "candidate_name":       "",
        "candidate_email":      "",
        "current_node":         "classifier",
        "screening_result":     None,
        "composite_score":      None,
        "recommendation":       None,
        "judge_verdict":        None,
        "conflict_flag":        None,
        "conflict_reason":      None,
        "hitl_reviewed":        False,
        "hitl_final_decision":  None,
        "hitl_override_reason": None,
        "reviewed_by":          None,
        "final_decision":       "",
        "error":                None,
        "error_node":           None,
        "org_id": "00000000-0000-0000-0000-000000000001",   # ← for email intake, set this from org lookup later
    }


# ── HITL interrupt handler ────────────────────────────────────────

def handle_hitl_interrupt(state: dict) -> None:
    """
    Called when pipeline pauses at HITL node.
    Updates Supabase status and sends HR notification email.
    """
    settings        = get_settings()
    run_id          = state.get("run_id", "")
    judge           = state.get("judge_verdict") or {}
    candidate_name  = state.get("candidate_name", "Unknown")
    role_title      = state.get("matched_jd_title", "Unknown Role")
    composite_score = state.get("composite_score", 0) or 0
    conflict_flag   = state.get("conflict_flag", False)
    screener_rec    = state.get("recommendation", "N/A") or "N/A"
    judge_rec       = judge.get("suggested_recommendation", "N/A")
    review_url      = f"{WEB_UI_BASE_URL}/review/{run_id}"

    print(f"\n[HITL] Paused for: {candidate_name}")
    print(f"[HITL] Review URL: {review_url}")

    update_pipeline_run(
        run_id=run_id,
        current_node="hitl_pending",
        status="pending_review",
    )
    log_audit(
        run_id=run_id,
        node_name="hitl",
        action="notification_sent",
        payload={"review_url": review_url, "conflict_flag": conflict_flag},
    )

    print(f"[HITL] Candidate ready for review: {review_url}")

    hr_email = settings.hr_notification_email
    if hr_email:
        try:
            send_hitl_notification(
                to_email=hr_email,
                candidate_name=candidate_name,
                role_title=role_title,
                composite_score=composite_score,
                screener_recommendation=screener_rec,
                judge_recommendation=judge_rec,
                conflict_flag=conflict_flag,
                review_url=review_url,
            )
            print(f"[HITL] Email notification sent to: {hr_email}")
        except Exception as e:
            print(f"[HITL] Email notification failed (non-fatal): {e}")


def handle_confirmation_interrupt(state: dict, thread_id: str) -> None:
    """
    Called when pipeline pauses at confirmation_pause node.
    Updates Supabase so the dashboard shows the CV in the confirmation queue.
    """
    run_id         = state.get("run_id", "")
    candidate_name = state.get("candidate_name", "Unknown")
    confidence     = state.get("confidence_score", 0)
    top_pick       = state.get("matched_jd_title", "Unknown")

    print(f"\n[ConfirmationPause] Paused for: {candidate_name}")
    print(f"[ConfirmationPause] Confidence: {confidence:.0%} → top pick: {top_pick}")

    if run_id:
        _save_thread_mapping(run_id, thread_id)
        update_pipeline_run(
            run_id=run_id,
            current_node="confirmation_pause",
            status="in_progress",
        )
        log_audit(
            run_id=run_id,
            node_name="confirmation_pause",
            action="awaiting_confirmation",
            payload={
                "confidence_score": confidence,
                "top_pick":         top_pick,
            },
        )


def handle_unmatched_interrupt(state: dict, thread_id: str) -> None:
    """
    Called when pipeline pauses at unmatched_queue node.
    Updates Supabase so the dashboard shows the CV in the unmatched queue.
    """
    run_id         = state.get("run_id", "")
    candidate_name = state.get("candidate_name", "Unknown")

    print(f"\n[UnmatchedQueue] Parked: {candidate_name}")

    if run_id:
        _save_thread_mapping(run_id, thread_id)
        update_pipeline_run(
            run_id=run_id,
            current_node="unmatched_queue",
            status="in_progress",
        )
        log_audit(
            run_id=run_id,
            node_name="unmatched_queue",
            action="unmatched",
            payload={"candidate_name": candidate_name},
        )


# ── Email processor ───────────────────────────────────────────────

def process_email(app, email_data: dict) -> None:
    """Run the full pipeline for one incoming email."""
    print(f"\n{'='*60}")
    print(f"Processing: {email_data['email_subject']}")
    print(f"From:       {email_data['email_sender']}")
    print(f"{'='*60}")

    thread_id     = email_data["email_id"]
    config        = {"configurable": {"thread_id": thread_id}}
    initial_state = get_initial_state(email_data)

    try:
        for event in app.stream(initial_state, config):
            for node_name in event:
                print(f"  ✓ {node_name}")

        current_state = app.get_state(config)
        next_nodes    = current_state.next
        state_values  = current_state.values

        if not next_nodes:
            print(f"\n✅ Pipeline complete")
            return

        if "hitl" in next_nodes:
            run_id = state_values.get("run_id", "")
            _save_thread_mapping(run_id, thread_id)
            handle_hitl_interrupt(state_values)

        elif "confirmation_pause" in next_nodes:
            handle_confirmation_interrupt(state_values, thread_id)

        elif "unmatched_queue" in next_nodes:
            handle_unmatched_interrupt(state_values, thread_id)

    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()


# ── Manual upload processor ───────────────────────────────────────

def process_manual_upload(app, initial_state: dict) -> None:
    """
    Run pipeline for a manually uploaded CV.
    Starts at ingest node — classifier is skipped entirely.
    The initial_state is built by ui/routers/upload.py with
    has_cv=True and matched_jd_id already set.
    """
    thread_id = initial_state["email_id"]
    config    = {"configurable": {"thread_id": thread_id}}

    print(f"\n{'='*60}")
    print(f"Manual upload: {initial_state.get('matched_jd_title')}")
    print(f"Uploaded by:   {initial_state.get('email_sender')}")
    print(f"{'='*60}")

    try:
        for event in app.stream(initial_state, config):
            for node_name in event:
                print(f"  ✓ {node_name}")

        current_state = app.get_state(config)
        next_nodes    = current_state.next
        state_values  = current_state.values

        if not next_nodes:
            print(f"\n✅ Manual upload pipeline complete")
            return

        if "hitl" in next_nodes:
            run_id = state_values.get("run_id", "")
            _save_thread_mapping(run_id, thread_id)
            handle_hitl_interrupt(state_values)

    except Exception as e:
        print(f"\n❌ Manual upload error: {e}")
        import traceback
        traceback.print_exc()


# ── Pipeline resume ───────────────────────────────────────────────

def resume_pipeline(pipeline_app, run_id: str, state_update: dict) -> None:
    """
    Resume a paused pipeline from any interrupt point.
    Called by:
      - ui/app.py (HITL decision)
      - ui/routers/queue.py (confirmation + unmatched)

    state_update contains whatever fields need to be injected
    before resuming — differs per interrupt type.
    """
    thread_id = _get_thread_id(run_id)
    if not thread_id:
        print(f"[Resume] No thread mapping found for run_id: {run_id}")
        return

    config        = {"configurable": {"thread_id": thread_id}}
    current_state = pipeline_app.get_state(config)

    print(f"\n[Resume] run_id: {run_id}")
    print(f"[Resume] thread_id: {thread_id}")
    print(f"[Resume] next nodes: {current_state.next}")

    if not current_state.next:
        print(f"[Resume] No pending nodes — already completed")
        return

    # Inject updated state fields
    pipeline_app.update_state(config, state_update)

    try:
        print(f"[Resume] Resuming...")
        for event in pipeline_app.stream(None, config):
            for node_name in event:
                print(f"  ✓ {node_name}")

        # Check if pipeline hit another interrupt (e.g. hitl after confirmation)
        resumed_state = pipeline_app.get_state(config)
        if resumed_state.next and "hitl" in resumed_state.next:
            state_values = resumed_state.values
            run_id_new   = state_values.get("run_id", run_id)
            handle_hitl_interrupt(state_values)
        else:
            print(f"\n✅ Pipeline complete for: {run_id}")
            _delete_thread_mapping(run_id)

    except Exception as e:
        print(f"\n❌ Resume error: {e}")
        import traceback
        traceback.print_exc()


# ── Web UI ────────────────────────────────────────────────────────

def start_web_ui():
    """Start FastAPI in a background daemon thread."""
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")


# ── Main loop ─────────────────────────────────────────────────────

def run_pipeline_loop(once: bool = False) -> None:
    pipeline_app = get_pipeline_app()

    # ── Wire all callbacks ────────────────────────────
    # HITL resume (existing)
    set_resume_callback(
        lambda run_id, decision: resume_pipeline(pipeline_app, run_id, decision)
    )

    # Confirmation + unmatched queue resume (Phase 4)
    from ui.routers.queue import set_queue_resume_callback
    set_queue_resume_callback(
        lambda run_id, state_update: resume_pipeline(pipeline_app, run_id, state_update)
    )

    # Manual CV upload trigger (Phase 6)
    from ui.routers.upload import set_upload_trigger_callback
    set_upload_trigger_callback(
        lambda initial_state: process_manual_upload(pipeline_app, initial_state)
    )

    # Start FastAPI in background thread
    ui_thread = threading.Thread(target=start_web_ui, daemon=True)
    ui_thread.start()

    print("=" * 60)
    print("  Recruitment Agent — Started")
    print(f"  Web UI:      {WEB_UI_BASE_URL}")
    print(f"  Dashboard:   {WEB_UI_BASE_URL}/dashboard")
    print(f"  Jobs:        {WEB_UI_BASE_URL}/jobs")
    print(f"  Upload CV:   {WEB_UI_BASE_URL}/upload")
    print(f"  Checkpoints: {CHECKPOINT_DB}")
    print("=" * 60)

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Polling Gmail...")
        emails = get_unread_cv_emails()

        if not emails:
            print("  No new CV emails")
        else:
            print(f"  Found {len(emails)} email(s)")
            for email_data in emails:
                process_email(pipeline_app, email_data)

        if once:
            print("\nOne-shot mode — exiting")
            break

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recruitment Agent")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one batch and exit without looping",
    )
    args = parser.parse_args()
    run_pipeline_loop(once=args.once)