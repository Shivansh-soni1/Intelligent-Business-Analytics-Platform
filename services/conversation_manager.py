import re
from collections import defaultdict
from typing import List, Dict, Any, Optional

class ConversationManager:
    """Stores session memory and contextual entities to enable follow-up questions."""

    def __init__(self, max_history_turns: int = 5):
        self.sessions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.max_history_turns = max_history_turns

    def add_turn(self, session_id: str, question: str, plan: dict, result_summary: str, raw_data: Any = None):
        """Records a completed turn in session memory with extracted focus entities."""
        extracted_entity = None

        # 1. Try extracting directly from structured data
        if isinstance(raw_data, dict) and raw_data:
            first_k = list(raw_data.keys())[0]
            first_v = raw_data[first_k]
            if isinstance(first_v, dict) and "name" in first_v:
                extracted_entity = str(first_v["name"])
            elif not str(first_k).startswith(("sum_", "mean_", "count_", "unique_", "total_", "percentage_")):
                extracted_entity = str(first_k)

        # 2. Try regex extraction if not yet found
        if not extracted_entity and isinstance(result_summary, str):
            match_bold = re.search(r'\*\*([a-zA-Z0-9_\s]+)\*\*', result_summary)
            if match_bold:
                extracted_entity = match_bold.group(1).strip()
            else:
                match_dict = re.search(r"'(?:name|key)':\s*'([a-zA-Z0-9_\s]+)'", result_summary)
                if match_dict:
                    extracted_entity = match_dict.group(1).strip()
                else:
                    match_kv = re.search(r"'(?!(?:sum|mean|count|unique|total|percentage)_)([a-zA-Z0-9_\s]+)':\s*[\d\.]+", result_summary)
                    if match_kv:
                        extracted_entity = match_kv.group(1).strip()

        turn_data = {
            "question": question,
            "plan": plan,
            "result_summary": result_summary,
            "last_metric": plan.get("metric_column"),
            "last_group_column": plan.get("group_by", [None])[0] if plan.get("group_by") else None,
            "last_entity": extracted_entity
        }

        self.sessions[session_id].append(turn_data)
        if len(self.sessions[session_id]) > self.max_history_turns:
            self.sessions[session_id].pop(0)

    def get_last_turn(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns the most recent conversation turn for pronoun and context resolution."""
        history = self.sessions.get(session_id, [])
        return history[-1] if history else None

    def get_context_formatted(self, session_id: str) -> str:
        """Formats conversation history for LLM prompt context."""
        history = self.sessions.get(session_id, [])
        if not history:
            return "No previous context."

        formatted_turns = []
        for idx, turn in enumerate(history, 1):
            entity_info = f" (Focus Entity: {turn['last_entity']})" if turn.get('last_entity') else ""
            formatted_turns.append(
                f"Turn {idx}:\n"
                f"User Question: {turn['question']}\n"
                f"Executed Plan: {turn['plan']}\n"
                f"Result: {turn['result_summary']}{entity_info}"
            )
        return "\n---\n".join(formatted_turns)

    def clear_session(self, session_id: str):
        """Clears session history when a new dataset is uploaded."""
        if session_id in self.sessions:
            del self.sessions[session_id]