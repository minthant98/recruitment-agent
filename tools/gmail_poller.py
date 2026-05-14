"""
gmail_poller.py — Polls Gmail inbox for new CV emails.
"""
import os
import base64
from pathlib import Path
from tools.email import get_gmail_service

ATTACHMENT_DIR = "attachments"
CV_EXTENSIONS  = {".pdf", ".docx", ".doc"}


def _decode_body(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _get_email_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_body(data) if data else ""

    if payload.get("mimeType") == "text/html":
        return ""

    body_parts = []
    for part in payload.get("parts", []):
        text = _get_email_body(part)
        if text:
            body_parts.append(text)

    return "\n".join(body_parts)


def _download_attachment(
    service, message_id: str, attachment_id: str, filename: str
) -> str | None:
    try:
        Path(ATTACHMENT_DIR).mkdir(parents=True, exist_ok=True)

        attachment = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )

        data = base64.urlsafe_b64decode(attachment["data"] + "==")
        file_path = os.path.join(ATTACHMENT_DIR, filename)

        with open(file_path, "wb") as f:
            f.write(data)

        return file_path

    except Exception as e:
        print(f"  Failed to download attachment {filename}: {e}")
        return None
    
def _extract_attachments(service, message_id: str, payload: dict) -> list[dict]:
    attachments = []

    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        if not filename:
            continue

        ext = Path(filename).suffix.lower()
        if ext not in CV_EXTENSIONS:
            continue

        attachment_id = part.get("body", {}).get("attachmentId")
        if not attachment_id:
            continue

        file_path = _download_attachment(service, message_id, attachment_id, filename)
        if file_path:
            attachments.append({
                "filename":  filename,
                "file_path": file_path,
                "file_type": ext.lstrip("."),
            })

    return attachments


def get_unread_cv_emails() -> list[dict]:
    """
    Poll Gmail inbox for unread emails with CV attachments.
    Returns list of dicts with email data and attachment path.
    """
    service = get_gmail_service()
    results = []

    try:
        response = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread has:attachment", maxResults=10)
            .execute()
        )

        messages = response.get("messages", [])
        if not messages:
            return []

        for msg_ref in messages:
            msg_id = msg_ref["id"]

            message = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            payload = message.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

            subject = headers.get("Subject", "")
            sender  = headers.get("From", "")
            body    = _get_email_body(payload)

            attachments = _extract_attachments(service, msg_id, payload)
            if not attachments:
                service.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()
                continue

            attachment = attachments[0]

            results.append({
                "email_id":        msg_id,
                "email_subject":   subject,
                "email_sender":    sender,
                "email_body":      body,
                "attachment_path": attachment["file_path"],
                "cv_file_type":    attachment["file_type"],
            })

            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()

    except Exception as e:
        print(f"Gmail polling error: {e}")

    return results