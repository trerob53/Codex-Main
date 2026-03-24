"""
Cerasus Hub — Email Service
SMTP-based email sender for automated notifications.
No Exchange/Outlook dependency — works headless on any machine.
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.config import APP_NAME, load_setting


def _load_settings():
    """Load SMTP settings from the hub database."""
    try:
        raw = load_setting("hub_smtp", "{}")
        if isinstance(raw, str):
            return json.loads(raw)
    except Exception:
        pass
    return {}


def is_email_configured():
    """Check if SMTP is configured and enabled."""
    s = _load_settings()
    return bool(s.get("enabled") and s.get("server") and s.get("username"))


def test_smtp_connection():
    """Test SMTP connectivity. Returns (success: bool, message: str)."""
    s = _load_settings()
    if not s.get("server"):
        return False, "No SMTP server configured."

    try:
        server = smtplib.SMTP(s["server"], int(s.get("port", 587)), timeout=10)
        if s.get("use_tls", True):
            server.starttls()
        if s.get("username") and s.get("password"):
            server.login(s["username"], s["password"])
        server.quit()
        return True, f"Connected to {s['server']}:{s.get('port', 587)}"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check username and password (use app-specific password for Gmail)."
    except Exception as e:
        return False, str(e)


def send_email(to, subject, body_html, email_type="general", triggered_by=""):
    """Send an HTML email via SMTP.

    Args:
        to: Recipient email address (or comma-separated list)
        subject: Email subject line
        body_html: HTML body content (will be wrapped in branded template)
        email_type: Category for audit logging
        triggered_by: Username that triggered the email

    Returns:
        True if sent successfully, False otherwise.
    """
    s = _load_settings()
    if not s.get("enabled") or not s.get("server"):
        return False

    from_email = s.get("from_email", s.get("username", ""))
    from_name = s.get("from_name", APP_NAME)

    # Build branded email
    full_html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif; max-width:600px; margin:0 auto;">
        {_brand_header()}
        <div style="padding:24px; background:#ffffff;">
            {body_html}
        </div>
        {_brand_footer()}
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to
    msg.attach(MIMEText(full_html, "html"))

    try:
        server = smtplib.SMTP(s["server"], int(s.get("port", 587)), timeout=15)
        if s.get("use_tls", True):
            server.starttls()
        if s.get("username") and s.get("password"):
            server.login(s["username"], s["password"])

        recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
        server.sendmail(from_email, recipients, msg.as_string())
        server.quit()

        # Audit log
        try:
            from src import audit
            audit.log_event("hub", "email_sent", triggered_by or "system",
                            f"Email sent to {to}: {subject} ({email_type})")
        except Exception:
            pass

        return True
    except Exception as e:
        try:
            from src import audit
            audit.log_event("hub", "email_failed", triggered_by or "system",
                            f"Email to {to} failed: {e}")
        except Exception:
            pass
        return False


def _brand_header():
    return """
    <div style="background:#0F1A2E; padding:18px 24px; text-align:center;">
        <span style="color:#FFFFFF; font-family:'Segoe UI',Arial,sans-serif;
                     font-size:22px; font-weight:800; letter-spacing:2px;">
            CERASUS
        </span>
        <span style="color:#C8102E; font-family:'Segoe UI',Arial,sans-serif;
                     font-size:22px; font-weight:800;">
            &nbsp;HUB
        </span>
    </div>
    """


def _brand_footer():
    return """
    <div style="background:#f5f5f5; padding:12px 24px; text-align:center;
                font-size:11px; color:#888; font-family:'Segoe UI',Arial,sans-serif;">
        Sent automatically by Cerasus Hub. Do not reply to this email.
    </div>
    """
