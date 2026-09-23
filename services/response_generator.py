import os
import json
from services.llm_service import LLMService

class ResponseGenerator:
    """Synthesizes human-friendly, domain-aware answers based strictly on calculated output."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def generate_response(self, question: str, calculation_result: any, context_history: str, domain: str = "General Analytics") -> str:
        if isinstance(calculation_result, str):
            return calculation_result

        system_prompt = f"""
You are an expert Data Analyst specializing in {domain}.
Synthesize the user's question and calculated Pandas results into a direct, conversational response.

STRICT INSTRUCTIONS:
1. Base your response ONLY on the CALCULATED RESULT provided below.
2. DO NOT invent or hallucinate extra numbers, dates, or facts.
3. Present key figures clearly (use currency symbols, percentages, or commas where appropriate).
4. If the calculated result contains items grouped within categories (e.g. "Region → Product"), organize the response clearly grouped by each primary category (e.g. bold the category and list the top items under it).
5. Keep the output clean and well-structured with bullet points.
"""

        user_prompt = f"""
DOMAIN CONTEXT: {domain}

RECENT HISTORY:
{context_history}

USER QUESTION: {question}

CALCULATED PANDAS RESULT:
{json.dumps(calculation_result, indent=2, default=str)}

Generate the final concise response:
"""

        if os.environ.get("FAST_TEST") == "1" or not getattr(self.llm, "api_key", None):
            return self._format_fallback(question, calculation_result)

        try:
            return self.llm.completion(system_prompt, user_prompt, json_mode=False)
        except Exception:
            # Fallback formatting if LLM service is unavailable
            return self._format_fallback(question, calculation_result)

    def _format_fallback(self, question: str, calculation_result: any) -> str:
        """Deterministic human-readable fallback when LLM is unavailable."""
        if isinstance(calculation_result, dict):
            # Check if multi-level grouping (e.g. Region → Product)
            has_nested = any("→" in str(k) or " - " in str(k) for k in calculation_result.keys())
            if has_nested:
                grouped_items = {}
                for k, v in calculation_result.items():
                    sep = "→" if "→" in str(k) else " - "
                    parts = str(k).split(sep, 1)
                    cat = parts[0].strip()
                    item = parts[1].strip() if len(parts) > 1 else ""
                    if cat not in grouped_items:
                        grouped_items[cat] = []
                    grouped_items[cat].append((item, v))

                lines = ["Top items inside each category:"]
                for cat, items in grouped_items.items():
                    sub_items = [f"{it}: ${val:,.2f}" if isinstance(val, (int, float)) else f"{it} ({val})" for it, val in items]
                    lines.append(f"• **{cat}**:\n  " + "\n  ".join(f"- {s}" for s in sub_items))
                return "\n\n".join(lines)

            parts = []
            for k, v in calculation_result.items():
                clean_k = k.replace("_", " ").title()
                if isinstance(v, float):
                    parts.append(f"{clean_k}: {v:,.2f}")
                elif isinstance(v, int):
                    parts.append(f"{clean_k}: {v:,}")
                else:
                    parts.append(f"{clean_k}: {v}")
            return "Analysis Result:\n" + "\n".join(f"• {p}" for p in parts)
        return f"Result: {str(calculation_result)}"