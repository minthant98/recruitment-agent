"""
ingest.py — Ingest node.

Responsibilities:
1. Extract raw text from CV file (PDF or Word)
2. Call Groq to parse CV into structured CandidateData
3. Insert candidate into Supabase
4. Create pipeline_run record
5. Update state with candidate_id, run_id, raw_cv_text
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from docx import Document
from groq import Groq

from config import get_settings
from state.agent_state import AgentState
from schemas.candidate import CandidateData
from prompts.ingest import CV_EXTRACTION_PROMPT
from db.queries import (
    insert_candidate,
    insert_pipeline_run,
    log_audit,
    update_pipeline_run,
)
from utils.text import clean_text


# ── CV text extraction ────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF CV using pdfplumber."""
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return clean_text("\n".join(text_parts))


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from a Word CV using python-docx."""
    doc = Document(file_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return clean_text("\n".join(paragraphs))


def extract_cv_text(file_path: str, file_type: str) -> str:
    """Route to correct extractor based on file type."""
    if file_type == "pdf":
        return extract_text_from_pdf(file_path)
    elif file_type in ("docx", "doc"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported CV file type: {file_type}")


# ── Groq CV parser ────────────────────────────────────

def parse_cv_with_groq(raw_text: str) -> CandidateData:
    """
    Send raw CV text to Groq and return structured CandidateData.
    Uses screener model (fast, deterministic).
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    response = client.chat.completions.create(
        model=settings.groq_screener_model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": CV_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Extract structured data from this CV:\n\n{raw_text}"},
        ],
    )

    raw_output = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw_output.startswith("```"):
        raw_output = raw_output.split("```")[1]
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]

    parsed = json.loads(raw_output.strip())
    return CandidateData(**parsed)


# ── Ingest node ───────────────────────────────────────

def ingest_node(state: AgentState) -> dict:
    """
    LangGraph node — extracts and stores candidate data from CV.

    Reads from state:
        attachment_path, cv_file_type, matched_jd_id, email_id

    Writes to state:
        candidate_id, run_id, raw_cv_text,
        candidate_name, candidate_email, current_node
    """
    print(f"\n[Ingest] Processing CV: {state.get('attachment_path')}")

    attachment_path = state.get("attachment_path", "")
    cv_file_type = state.get("cv_file_type", "")
    matched_jd_id = state.get("matched_jd_id", "")

    # ── 1. Extract raw text from CV ───────────────────
    raw_cv_text = extract_cv_text(attachment_path, cv_file_type)
    print(f"[Ingest] Extracted {len(raw_cv_text)} characters from CV")

    # ── 2. Parse CV with Groq ─────────────────────────
    candidate_data = parse_cv_with_groq(raw_cv_text)
    print(f"[Ingest] Parsed candidate: {candidate_data.name}")

    # ── 3. Insert candidate into Supabase ─────────────
    candidate_row = insert_candidate({
    "name": candidate_data.name,
    "email": candidate_data.email,
    "total_experience_years": candidate_data.total_experience_years,
    "relevant_experience_years": candidate_data.relevant_experience_years,
    "previous_roles": candidate_data.previous_roles,
    "industry_exposure": candidate_data.industry_exposure,
    "education": candidate_data.education,
    "raw_cv_text": raw_cv_text,
    "structured_cv": candidate_data.model_dump(),
    "source_email_id": state.get("email_id", ""),
    "org_id": state.get("org_id"),   # ← add this
})
    candidate_id = candidate_row["id"]
    print(f"[Ingest] Candidate saved: {candidate_id}")

    # ── 4. Create pipeline run ────────────────────────
    run_row = insert_pipeline_run(
    candidate_id=candidate_id,
    jd_id=matched_jd_id,
    org_id=state.get("org_id"),                          # ← add
    confidence_score=state.get("confidence_score"),       # ← add
    match_status=state.get("match_status", "AUTO_ASSIGNED"),  # ← add
    source=state.get("source", "EMAIL"),                  # ← add
)
    run_id = run_row["id"]
    print(f"[Ingest] Pipeline run created: {run_id}")

    # ── 5. Log to audit ───────────────────────────────
    log_audit(
        run_id=run_id,
        node_name="ingest",
        action="completed",
        payload={
            "candidate_name": candidate_data.name,
            "cv_file_type": cv_file_type,
            "total_experience_years": candidate_data.total_experience_years,
            "matched_jd_id": matched_jd_id,
        }
    )
    update_pipeline_run(run_id=run_id, current_node="ingest")

    return {
        "candidate_id": candidate_id,
        "run_id": run_id,
        "raw_cv_text": raw_cv_text,
        "candidate_name": candidate_data.name,
        "candidate_email": candidate_data.email or "",
        "current_node": "ingest",
    }