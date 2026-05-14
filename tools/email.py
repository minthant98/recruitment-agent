"""
email.py — Gmail sender for notifications, routing, and scheduling.

Uses Gmail API with OAuth2 credentials.
Handles three email types:
1. HITL notification — alerts HR when review is needed
2. Profile forwarding — sends shortlisted profile to dept head
3. Interview invite — sends invite to candidate
"""
import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import get_settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # read + mark as read
]


def get_gmail_service():
    """
    Build and return authenticated Gmail API service.
    Handles token refresh automatically.
    """
    settings = get_settings()
    creds = None

    token_path = settings.gmail_token_path
    creds_path = settings.gmail_credentials_path

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _encode_message(message) -> dict:
    """Encode MIME message for Gmail API."""
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def send_hitl_notification(
    to_email: str,
    candidate_name: str,
    role_title: str,
    composite_score: float,
    screener_recommendation: str,
    judge_recommendation: str,
    conflict_flag: bool,
    review_url: str,
) -> bool:
    """
    Send HTML notification email to HR officer when HITL is triggered.
    Includes a Review Now button linking to the web UI.
    """
    conflict_badge = ""
    if conflict_flag:
        conflict_badge = """
        <div style="background:#FFC7CE;color:#9C0006;padding:8px 16px;
                    border-radius:4px;margin:16px 0;font-weight:bold;">
            ⚠ Agents disagree — review carefully
        </div>"""

    screener_colour = _rec_colour(screener_recommendation)
    judge_colour    = _rec_colour(judge_recommendation)

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
        <h2 style="color:#1F4E79">Recruitment Agent — Review Required</h2>
        {conflict_badge}
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
            <tr style="background:#F2F2F2">
                <td style="padding:10px;font-weight:bold">Candidate</td>
                <td style="padding:10px">{candidate_name}</td>
            </tr>
            <tr>
                <td style="padding:10px;font-weight:bold">Role</td>
                <td style="padding:10px">{role_title}</td>
            </tr>
            <tr style="background:#F2F2F2">
                <td style="padding:10px;font-weight:bold">Composite Score</td>
                <td style="padding:10px"><strong>{composite_score:.1f} / 100</strong></td>
            </tr>
            <tr>
                <td style="padding:10px;font-weight:bold">Screener</td>
                <td style="padding:10px">
                    <span style="background:{screener_colour};padding:3px 10px;
                                 border-radius:4px">{screener_recommendation}</span>
                </td>
            </tr>
            <tr style="background:#F2F2F2">
                <td style="padding:10px;font-weight:bold">Judge</td>
                <td style="padding:10px">
                    <span style="background:{judge_colour};padding:3px 10px;
                                 border-radius:4px">{judge_recommendation}</span>
                </td>
            </tr>
        </table>
        <a href="{review_url}"
           style="display:inline-block;background:#1F4E79;color:white;
                  padding:14px 32px;border-radius:6px;text-decoration:none;
                  font-size:16px;font-weight:bold;margin:16px 0">
            Review Now
        </a>
        <p style="color:#666;font-size:12px;margin-top:24px">
            Recruitment Agent — CB Bank Internal System
        </p>
    </body></html>
    """

    subject = f"[Review Required] {candidate_name} — {role_title}"
    if conflict_flag:
        subject = f"[⚠ Conflict] {candidate_name} — {role_title}"

    return _send_html_email(to_email=to_email, subject=subject, html=html)


def send_profile_to_dept_head(
    to_email: str,
    dept_head_name: str,
    candidate_name: str,
    role_title: str,
    composite_score: float,
    strengths: list[str],
    decision_justification: str,
    cv_file_path: str | None = None,
) -> bool:
    """
    Send shortlisted candidate profile to department head.
    Attaches CV file if path provided.
    """
    strengths_html = "".join(f"<li>{s}</li>" for s in strengths)

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
        <h2 style="color:#1F4E79">Shortlisted Candidate — {role_title}</h2>
        <p>Dear {dept_head_name},</p>
        <p>A candidate has been shortlisted for your review.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
            <tr style="background:#F2F2F2">
                <td style="padding:10px;font-weight:bold">Candidate</td>
                <td style="padding:10px">{candidate_name}</td>
            </tr>
            <tr>
                <td style="padding:10px;font-weight:bold">Role</td>
                <td style="padding:10px">{role_title}</td>
            </tr>
            <tr style="background:#F2F2F2">
                <td style="padding:10px;font-weight:bold">Score</td>
                <td style="padding:10px"><strong>{composite_score:.1f} / 100</strong></td>
            </tr>
        </table>
        <h3 style="color:#1F4E79">Key Strengths</h3>
        <ul>{strengths_html}</ul>
        <h3 style="color:#1F4E79">Recruiter Assessment</h3>
        <p>{decision_justification}</p>
        <p style="color:#666;font-size:12px;margin-top:24px">
            CV attached. Recruitment Agent — CB Bank Internal System
        </p>
    </body></html>
    """

    subject = f"[Shortlisted] {candidate_name} — {role_title}"
    return _send_html_email(
        to_email=to_email,
        subject=subject,
        html=html,
        attachment_path=cv_file_path,
    )


def send_interview_invite(
    to_email: str,
    candidate_name: str,
    role_title: str,
    company_name: str = "CB Bank",
) -> bool:
    """
    Send interview invitation email to shortlisted candidate.
    HR will follow up with specific time slot.
    """
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
        <h2 style="color:#1F4E79">Interview Invitation — {company_name}</h2>
        <p>Dear {candidate_name},</p>
        <p>
            Thank you for your interest in the <strong>{role_title}</strong> position
            at {company_name}.
        </p>
        <p>
            We are pleased to inform you that after reviewing your application,
            we would like to invite you for an interview.
        </p>
        <p>
            Our HR team will be in touch shortly with the interview schedule,
            format, and any further details you may need to prepare.
        </p>
        <p>We look forward to speaking with you.</p>
        <br>
        <p>Best regards,<br>
           <strong>Talent Acquisition Team</strong><br>
           {company_name}
        </p>
        <p style="color:#666;font-size:12px;margin-top:24px">
            This is an automated notification from the {company_name} Recruitment System.
        </p>
    </body></html>
    """

    subject = f"Interview Invitation — {role_title} at {company_name}"
    return _send_html_email(to_email=to_email, subject=subject, html=html)


# ── Internal helpers ──────────────────────────────────

def _rec_colour(recommendation: str) -> str:
    """Map recommendation to background colour for email badges."""
    colours = {
        "SHORTLIST_INTERVIEW": "#C6EFCE",
        "HOLD":                "#FFEB9C",
        "REJECT":              "#FFC7CE",
    }
    return colours.get(recommendation, "#F2F2F2")


def _send_html_email(
    to_email: str,
    subject: str,
    html: str,
    attachment_path: str | None = None,
) -> bool:
    """
    Send an HTML email via Gmail API.
    Returns True on success, False on failure.
    """
    try:
        message = MIMEMultipart("alternative")
        message["to"]      = to_email
        message["subject"] = subject

        message.attach(MIMEText(html, "html"))

        # Attach file if provided
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = Path(attachment_path).name
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={filename}"
            )
            message.attach(part)

        service = get_gmail_service()
        service.users().messages().send(
            userId="me",
            body=_encode_message(message)
        ).execute()

        print(f"  Email sent to: {to_email}")
        return True

    except Exception as e:
        print(f"  Email failed: {e}")
        return False