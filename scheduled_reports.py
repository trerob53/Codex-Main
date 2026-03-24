"""Scheduled report generation for CerasusHub.
Can be triggered manually or on a timer."""

import os
from datetime import datetime, timedelta
from src.config import REPORTS_DIR, ensure_directories


def generate_weekly_reports() -> list:
    """Generate all weekly site reports and executive summary.
    Returns list of file paths created."""
    ensure_directories()
    files = []

    try:
        from src.report_generator import generate_executive_summary, generate_all_site_reports

        end = datetime.now().date()
        start = end - timedelta(days=7)

        # Executive summary
        try:
            fp = generate_executive_summary(start.isoformat(), end.isoformat())
            if fp:
                files.append(fp)
        except Exception:
            pass

        # Per-site reports
        try:
            site_files = generate_all_site_reports(start.isoformat(), end.isoformat())
            files.extend(site_files or [])
        except Exception:
            pass
    except ImportError:
        pass

    return files


def email_weekly_reports(recipient: str = "") -> bool:
    """Generate weekly reports and email them.
    Uses SMTP settings from the database."""
    files = generate_weekly_reports()
    if not files:
        return False

    try:
        from src.database import get_conn
        conn = get_conn()

        # Get email settings
        settings = {}
        for key in ['smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'smtp_from', 'admin_email']:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            settings[key] = row["value"] if row else ""
        conn.close()

        if not settings.get('smtp_host') or not settings.get('admin_email'):
            return False

        to_addr = recipient or settings['admin_email']

        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        msg = MIMEMultipart()
        msg['From'] = settings.get('smtp_from', settings['smtp_user'])
        msg['To'] = to_addr
        msg['Subject'] = f"Cerasus Weekly Report - {datetime.now().strftime('%B %d, %Y')}"

        body = f"Attached are the weekly reports generated on {datetime.now().strftime('%B %d, %Y')}.\n\n"
        body += f"{len(files)} report(s) generated.\n\nCerasus Hub"
        msg.attach(MIMEText(body, 'plain'))

        for fp in files:
            if os.path.isfile(fp):
                with open(fp, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(fp)}"')
                msg.attach(part)

        server = smtplib.SMTP(settings['smtp_host'], int(settings.get('smtp_port', 587)))
        server.starttls()
        if settings.get('smtp_user'):
            server.login(settings['smtp_user'], settings.get('smtp_pass', ''))
        server.send_message(msg)
        server.quit()
        return True
    except Exception:
        return False
