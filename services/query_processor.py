from typing import Dict, Any, Optional
import pandas as pd
from services.llm_service import LLMService
from services.analysis_planner import AnalysisPlanner
from services.pandas_executor import PandasExecutor
from services.response_generator import ResponseGenerator
from services.conversation_manager import ConversationManager

# Initialize singletons for services
llm_service = LLMService()
planner = AnalysisPlanner(llm_service)
executor = PandasExecutor()
generator = ResponseGenerator(llm_service)
conversation_manager = ConversationManager()

def handle_question(question: str, df: pd.DataFrame, profile: Optional[Dict[str, Any]] = None, session_id: str = "default_session") -> Dict[str, Any]:
    """Main pipeline handling dataset-agnostic, multi-domain conversational queries."""
    if df is None or not isinstance(df, pd.DataFrame):
        return {"answer": "No active dataset found. Please upload a CSV file first.", "chart": None}

    profile = profile or {}

    # Check for KPI or Alert inquiry
    q_lower = question.lower()
    is_kpi_query = any(k in q_lower for k in [
        "which kpi", "what kpi", "critical kpi", "at risk kpi", "kpi status",
        "active kpi", "target status", "alert history", "recent alert", "why is",
        "behind target", "exceeded target", "kpis are", "kpi monitoring"
    ]) and any(w in q_lower for w in ["kpi", "target", "alert", "risk", "critical", "monitor"])

    if is_kpi_query:
        from services.db_service import db_service
        summary = db_service.get_dashboard_summary()
        alerts = db_service.get_alert_history(limit=10)
        kpis = summary.get("kpis", [])
        
        kpi_context = {
            "total_kpis": summary.get("total_kpis", 0),
            "on_track": summary.get("on_track", 0),
            "at_risk": summary.get("at_risk", 0),
            "critical": summary.get("critical", 0),
            "exceeded": summary.get("exceeded", 0),
            "active_kpis": [
                {
                    "name": k.get("kpi_name"),
                    "metric": k.get("metric_column"),
                    "actual": k.get("actual_value"),
                    "target": k.get("target_value"),
                    "achievement_pct": k.get("achievement_pct"),
                    "performance_gap": k.get("performance_gap"),
                    "status": k.get("latest_status")
                } for k in kpis
            ],
            "recent_alerts": [
                {
                    "kpi": a.get("kpi_name"),
                    "severity": a.get("severity"),
                    "gap": a.get("performance_gap"),
                    "message": a.get("message")
                } for a in alerts[:5]
            ]
        }

        domain = profile.get("domain_info", {}).get("primary_domain", "Business Operations")
        conversational_answer = generator.generate_response(
            question=question,
            calculation_result=kpi_context,
            context_history=conversation_manager.get_context_formatted(session_id),
            domain=domain
        )
        return {
            "answer": conversational_answer,
            "chart": None,
            "kpi_summary": summary
        }

    try:
        # 1. Fetch conversation context safely
        history_context = conversation_manager.get_context_formatted(session_id)

        # 2. Generate structured JSON plan via LLM
        plan = planner.create_plan(question, profile, history_context)

        # 3. Execute plan safely in Pandas
        execution_output = executor.execute(plan, df, profile)

        if not execution_output.get("success", False):
            error_msg = execution_output.get("error", "Unable to compute the requested analysis.")
            return {"answer": error_msg, "chart": None}

        # 4. Synthesize natural language answer
        domain = profile.get("domain_info", {}).get("primary_domain", "General Analytics")
        conversational_answer = generator.generate_response(
            question=question,
            calculation_result=execution_output.get("data"),
            context_history=history_context,
            domain=domain
        )

        # 5. Record turn into session memory
        summary_str = str(execution_output.get("data"))
        conversation_manager.add_turn(session_id, question, plan, summary_str, execution_output.get("data"))

        return {
            "answer": conversational_answer,
            "chart": execution_output.get("chart")
        }

    except Exception as e:
        return {
            "answer": f"An error occurred while analyzing the dataset: {str(e)}",
            "chart": None
        }

def reset_session(session_id: str = "default_session"):
    """Resets conversation history on new file uploads."""
    conversation_manager.clear_session(session_id)