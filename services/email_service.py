import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, List, Optional

class EmailService:
    """Enterprise Automated Email Service with HTML templates and mock fallback.
    
    Adheres strictly to safety rules:
    - Never crashes if SMTP credentials are not configured (seamless mock mode)
    - Beautiful responsive SaaS HTML email templates with severity color coding
    - Configured via standard environment variables
    """

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.smtp_from = os.getenv("SMTP_FROM", "alerts@dataplatform.ai")
        # Default to False in dev/testing to prevent unwanted emails
        self.email_enabled = os.getenv("EMAIL_ENABLED", "false").lower() in ("true", "1", "yes")

    def build_html_alert(self, alert_payload: Dict[str, Any]) -> str:
        """Constructs a responsive modern HTML email for the KPI alert."""
        severity = alert_payload.get("severity", "WARNING").upper()
        kpi_name = alert_payload.get("kpi_name", "KPI Alert")
        actual = alert_payload.get("actual_value", 0)
        target = alert_payload.get("target_value", 0)
        achievement = alert_payload.get("achievement_pct", 0)
        expected_prog = alert_payload.get("expected_progress_pct", 0)
        gap = alert_payload.get("performance_gap", 0)
        message = alert_payload.get("message", "")

        # Colors & badges
        if severity == "CRITICAL":
            header_bg = "#dc2626"
            badge_color = "#ef4444"
            icon = "🔴"
            status_text = "CRITICAL BREACH"
        elif severity == "WARNING":
            header_bg = "#d97706"
            badge_color = "#f59e0b"
            icon = "🟡"
            status_text = "AT RISK"
        else:
            header_bg = "#16a34a"
            badge_color = "#10b981"
            icon = "🟢"
            status_text = "TARGET ACHIEVED"

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
  .header {{ background-color: {header_bg}; color: #ffffff; padding: 24px; text-align: center; }}
  .header h1 {{ margin: 0; font-size: 20px; letter-spacing: -0.5px; }}
  .header p {{ margin: 6px 0 0; opacity: 0.9; font-size: 14px; }}
  .content {{ padding: 24px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; background-color: {badge_color}; color: #ffffff; font-weight: 600; font-size: 12px; margin-bottom: 16px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }}
  .card-label {{ font-size: 12px; color: #64748b; font-weight: 500; text-transform: uppercase; margin-bottom: 4px; }}
  .card-val {{ font-size: 18px; font-weight: 700; color: #0f172a; }}
  .message-box {{ background: #fffbeb; border-left: 4px solid {header_bg}; padding: 12px 16px; margin: 20px 0; border-radius: 4px; font-size: 14px; color: #1e293b; }}
  .footer {{ background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 16px; text-align: center; font-size: 12px; color: #94a3b8; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{icon} KPI Alert: {kpi_name}</h1>
    <p>Automated Business Performance Monitoring</p>
  </div>
  <div class="content">
    <div class="badge">{status_text}</div>
    <p style="color: #334155; font-size: 14px; line-height: 1.5; margin: 0 0 16px;">
      The automated monitoring system has evaluated <strong>{kpi_name}</strong> and detected a status requiring attention.
    </p>
    
    <div class="message-box">
      <strong>Alert Summary:</strong> {message}
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-label">Actual Value</div>
        <div class="card-val">{actual:,.2f}</div>
      </div>
      <div class="card">
        <div class="card-label">Target Value</div>
        <div class="card-val">{target:,.2f}</div>
      </div>
      <div class="card">
        <div class="card-label">Achievement</div>
        <div class="card-val">{achievement:.1f}%</div>
      </div>
      <div class="card">
        <div class="card-label">Expected Progress</div>
        <div class="card-val">{expected_prog:.1f}%</div>
      </div>
      <div class="card">
        <div class="card-label">Performance Gap</div>
        <div class="card-val" style="color: {'#dc2626' if gap < 0 else '#16a34a'};">{gap:+.1f}%</div>
      </div>
      <div class="card">
        <div class="card-label">Status</div>
        <div class="card-val" style="color: {header_bg};">{severity}</div>
      </div>
    </div>
  </div>
  <div class="footer">
    Sent automatically by AI Data Analytics Platform &bull; Anti-Spam Cooldown Active
  </div>
</div>
</body>
</html>
"""
        return html

    def send_alert_email(
        self,
        recipients: str,
        subject: str,
        alert_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sends an HTML alert email, with automatic mock mode fallback."""
        recipient_list = [r.strip() for r in recipients.split(",") if r.strip() and "@" in r]
        if not recipient_list:
            return {"success": False, "error": "No valid email recipients specified."}

        html_content = self.build_html_alert(alert_payload)

        # If SMTP is not configured or email is disabled, simulate send
        if not self.email_enabled or not self.smtp_host:
            # Mock / Simulated delivery mode
            return {
                "success": True,
                "simulated": True,
                "recipients": recipient_list,
                "subject": subject,
                "message": f"Simulated delivery to {', '.join(recipient_list)} (SMTP disabled or unconfigured)."
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = ", ".join(recipient_list)

            part = MIMEText(html_content, "html")
            msg.attach(part)

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                if self.smtp_user and self.smtp_pass:
                    server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.smtp_from, recipient_list, msg.as_string())

            return {
                "success": True,
                "simulated": False,
                "recipients": recipient_list,
                "subject": subject
            }

        except Exception as e:
            return {
                "success": False,
                "simulated": False,
                "error": f"SMTP delivery failed: {str(e)}",
                "recipients": recipient_list
            }

# Singleton instance
email_service = EmailService()

