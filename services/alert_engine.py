from typing import Dict, Any, Optional
from services.db_service import db_service
from services.email_service import email_service

class AlertEngine:
    """Enterprise Alert Decision & Anti-Spam Cooldown Engine.
    
    Responsibilities:
    - Analyzes evaluated KPI performance snapshots
    - Evaluates business threshold breaches and performance gap rules
    - Determines alert severity (CRITICAL, WARNING, INFO)
    - Enforces strict cooldown / deduplication logic to prevent email spam
    - Triggers automated emails and logs persistent alert audit history
    """

    DEFAULT_COOLDOWN_HOURS = 24

    def evaluate_and_notify(
        self,
        snapshot: Dict[str, Any],
        cooldown_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """Evaluates a KPI snapshot, enforces cooldown, and dispatches email if warranted."""
        kpi_id = snapshot["kpi_id"]
        kpi_name = snapshot.get("kpi_name", "KPI")
        status = snapshot.get("status", "ON TRACK")
        actual_val = snapshot.get("actual_value", 0.0)
        target_val = snapshot.get("target_value", 0.0)
        variance = snapshot.get("variance", 0.0)
        achievement = snapshot.get("achievement_pct", 0.0)
        gap = snapshot.get("performance_gap", 0.0)
        recipients = snapshot.get("recipients", "")
        cd_hours = cooldown_hours or self.DEFAULT_COOLDOWN_HOURS

        # -------------------------------------------------------------
        # 1. ALERT CONDITION & SEVERITY RULES
        # -------------------------------------------------------------
        alert_triggered = False
        alert_type = None
        severity = None
        message = ""
        subject = ""

        if status == "CRITICAL":
            alert_triggered = True
            alert_type = "CRITICAL"
            severity = "CRITICAL"
            subject = f"🔴 Critical KPI Alert: {kpi_name}"
            message = (
                f"Critical performance breach on '{kpi_name}'. "
                f"Current achievement is {achievement:.1f}% ({actual_val:,.2f} of {target_val:,.2f} target). "
                f"Performance gap is {gap:+.1f}% against expected progress."
            )
        elif status == "AT RISK":
            alert_triggered = True
            alert_type = "AT_RISK"
            severity = "WARNING"
            subject = f"🟡 KPI At Risk Alert: {kpi_name}"
            message = (
                f"'{kpi_name}' is currently at risk. "
                f"Achievement stands at {achievement:.1f}%, lagging expected progress by {abs(gap):.1f}%."
            )
        elif status == "EXCEEDED":
            alert_triggered = True
            alert_type = "TARGET_EXCEEDED"
            severity = "INFO"
            subject = f"🟢 KPI Target Exceeded: {kpi_name}"
            message = (
                f"Target exceeded for '{kpi_name}'! "
                f"Actual value {actual_val:,.2f} reached {achievement:.1f}% of the {target_val:,.2f} target."
            )
        else:
            # ON TRACK - No alert triggered
            return {
                "kpi_id": kpi_id,
                "alert_triggered": False,
                "status": status,
                "message": f"'{kpi_name}' is currently ON TRACK with a performance gap of {gap:+.1f}%."
            }

        # -------------------------------------------------------------
        # 2. ANTI-SPAM / COOLDOWN DEDUPLICATION
        # -------------------------------------------------------------
        is_on_cooldown = db_service.is_alert_on_cooldown(kpi_id, alert_type, severity, cd_hours)
        
        email_sent = False
        email_error = None
        email_result = {}

        if is_on_cooldown:
            email_error = f"Suppressed: Identical alert sent within {cd_hours}h cooldown period."
        else:
            # Send email if recipients exist
            if recipients and "@" in recipients:
                alert_payload = {
                    "kpi_name": kpi_name,
                    "severity": severity,
                    "actual_value": actual_val,
                    "target_value": target_val,
                    "achievement_pct": achievement,
                    "expected_progress_pct": snapshot.get("expected_progress_pct", 0.0),
                    "performance_gap": gap,
                    "message": message
                }
                email_result = email_service.send_alert_email(recipients, subject, alert_payload)
                email_sent = email_result.get("success", False)
                if not email_sent:
                    email_error = email_result.get("error", "Failed to dispatch email")

        # -------------------------------------------------------------
        # 3. RECORD ALERT IN AUDIT HISTORY
        # -------------------------------------------------------------
        alert_record = {
            "kpi_id": kpi_id,
            "kpi_name": kpi_name,
            "alert_type": alert_type,
            "severity": severity,
            "actual_value": actual_val,
            "target_value": target_val,
            "variance": variance,
            "performance_gap": gap,
            "message": message,
            "recipients": recipients,
            "email_sent": email_sent,
            "email_error": email_error
        }
        alert_id = db_service.save_alert(alert_record)

        return {
            "alert_id": alert_id,
            "kpi_id": kpi_id,
            "kpi_name": kpi_name,
            "alert_triggered": True,
            "alert_type": alert_type,
            "severity": severity,
            "performance_gap": gap,
            "cooldown_active": is_on_cooldown,
            "email_sent": email_sent,
            "email_error": email_error,
            "email_result": email_result,
            "message": message
        }

# Singleton instance
alert_engine = AlertEngine()

