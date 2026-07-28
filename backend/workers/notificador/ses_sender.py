"""
SES email sending with per-recipient error isolation.

Requirements: 7.4, 7.6, 11.1, 11.2, 11.3, 11.4
"""

import os
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_notification_email(
    recipient_email: str,
    subject: str,
    body: str,
    user_id: str,
    scan_job_id: str,
) -> bool:
    """
    Send a notification email via SES.

    On any failure: logs userId and truncated (<=500 chars) failure reason
    without sensitive content. Never raises — continues processing.

    Args:
        recipient_email: Destination email address
        subject: Email subject line
        body: Plain text email body
        user_id: User ID (for logging only, never in email content)
        scan_job_id: ScanJob ID (for logging context)

    Returns:
        True if sent successfully, False otherwise
    """
    import boto3
    from botocore.exceptions import ClientError

    sender_email = os.environ.get("SES_SENDER_EMAIL", "noreply@job-app.com")

    try:
        ses_client = boto3.client("ses")
        ses_client.send_email(
            Source=sender_email,
            Destination={"ToAddresses": [recipient_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )

        _log_structured("INFO", "email_sent_successfully", {
            "scanJobId": scan_job_id,
            "userId": user_id,
        })
        return True

    except ClientError as e:
        error_msg = str(e)[:500]
        _log_structured("ERROR", "email_send_failed", {
            "scanJobId": scan_job_id,
            "userId": user_id,
            "error": error_msg,
        })
        return False

    except Exception as e:
        error_msg = str(e)[:500]
        _log_structured("ERROR", "email_send_unexpected_error", {
            "scanJobId": scan_job_id,
            "userId": user_id,
            "error": error_msg,
        })
        return False


def _log_structured(level: str, message: str, context: dict) -> None:
    """Emit structured JSON log to stdout."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": level,
        "component": "Notificador_Lambda",
        "message": message,
        "context": context,
    }
    print(json.dumps(log_entry, default=str))
