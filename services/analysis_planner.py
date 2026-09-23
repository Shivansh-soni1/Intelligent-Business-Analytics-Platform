import os
import json
import re
from typing import Dict, Any, List, Optional
from services.llm_service import LLMService
from services.data_loader import find_best_column_match, normalize_text

class AnalysisPlanner:
    """Translates user natural language into structured execution plans supporting 40+ operations."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def create_plan(self, question: str, profile: Dict[str, Any], context_history: str) -> Dict[str, Any]:
        all_cols = profile.get("columns", [])
        num_cols = profile.get("numeric_cols", [])
        cat_cols = profile.get("categorical_cols", [])
        date_cols = profile.get("date_cols", [])
        id_cols = profile.get("identifier_cols", [])
        target_cols = profile.get("target_cols", [])
        kpi_cols = profile.get("kpi_cols", [])
        detected_semantics = profile.get("detected_semantics", {})

        # Handle large datasets (60+ columns) gracefully
        if len(all_cols) > 60:
            q_words = re.findall(r'\b\w+\b', question.lower())
            matched_candidates = []
            for w in q_words:
                m = find_best_column_match(w, all_cols)
                if m and m not in matched_candidates:
                    matched_candidates.append(m)
            
            num_display = (matched_candidates + [c for c in num_cols if c not in matched_candidates])[:25]
            cat_display = (matched_candidates + [c for c in cat_cols if c not in matched_candidates])[:25]
            schema_summary = f"""
DATASET SCHEMA & PROFILE (Large Dataset: {len(all_cols)} total columns):
- Total Rows: {profile.get('row_count', 0)}
- Numeric Columns (Sample): {num_display}
- Categorical Columns (Sample): {cat_display}
- Target Columns: {target_cols}
- KPI / Rate Columns: {kpi_cols}
- Date Columns: {date_cols}
- Identifier Columns (Do not aggregate): {id_cols[:15]}
- Relevant Candidate Columns for Query: {matched_candidates}
"""
        else:
            schema_summary = f"""
DATASET SCHEMA & PROFILE ({len(all_cols)} columns):
- Total Rows: {profile.get('row_count', 0)}
- Numeric Columns: {num_cols}
- Categorical Columns: {cat_cols}
- Target Columns: {target_cols}
- KPI / Rate Columns: {kpi_cols}
- Date Columns: {date_cols}
- Identifier Columns (Do not aggregate): {id_cols}
- Detected Business Fields: {detected_semantics}
"""

        system_prompt = """
You are a Senior Universal Data Architect & Lead Data Analyst. Convert natural language questions into structured JSON execution plans.

STRICT UNIVERSAL SCHEMA RULES:
1. The provided dataset schema is the ABSOLUTE SOURCE OF TRUTH. Use ONLY columns that exist in the schema.
2. NEVER assume or invent columns that do not exist in the schema.
3. The semantic dictionary is ONLY a knowledge base. If the user asks for a business term (e.g. 'profit', 'salary', 'churn') that has NO matching column or synonym in this dataset, DO NOT invent a column. Return:
   {
     "operation": "missing_column",
     "missing_entity": "<term>",
     "message": "I couldn't find a '<term>'-related column in this dataset."
   }
4. DO NOT select identifier_cols (e.g. Order_ID, Customer_ID, Employee_ID) for sum/mean/median operations.
5. CONTEXT & FOLLOW-UP RESOLUTION:
   If the question refers to "its", "it", "that", "this", or "the same" (e.g. "What about its profit?"):
   Look at RECENT CONVERSATION HISTORY. If the previous question evaluated a specific entity (e.g. Region == 'North'), include:
   "filters": [{"column": "<prev_group_col>", "operator": "==", "value": "<prev_entity>"}]
6. MULTI-STEP & ADVANCED PATTERNS:
   - "top N items inside/in each group" -> operation: "top_n", group_by: ["<container>", "<item>"], limit: N, per_group: true
   - "What percentage of total sales comes from the top 3 products?" -> operation: "top_n_contribution", metric_column: "Sales", group_by: ["Product"], limit: 3
   - "Compare sales between North and South and percentage difference" -> operation: "difference_between_groups", group_by: ["Region"], compare_groups: ["North", "South"], metric_column: "Sales"
   - "Which customers purchased more than average customer spending?" -> operation: "above_average_filter", group_by: ["Customer_ID"], metric_column: "Sales"
   - "Which product has highest sales but lowest profit margin?" -> operation: "extreme_combination", group_by: ["Product"]
   - "Actual vs target sales" -> operation: "actual_vs_target", metric_column: "Sales", comparison_column: "Target_Sales"
   - "Distribution / summary statistics of X" -> operation: "distribution_analysis", metric_column: "X"
   - "Return rate / Cancellation rate / Delivery rate" -> operation: "return_rate" | "cancellation_rate" | "delivery_rate"
7. Return ONLY a valid JSON object. No markdown formatting, no explanation.

SUPPORTED OPERATIONS:
1. Basic: "sum", "mean", "median", "min", "max", "count", "nunique", "distinct_values"
2. Grouping & Ranking: "group_by", "top_n", "bottom_n", "filter", "sort", "ranking", "partitioned_top_n"
3. Mathematical: "addition", "subtraction", "multiplication", "division", "percentage", "formula", "percentage_contribution", "percentage_difference", "difference", "ratio"
4. Comparisons: "difference_between_groups", "actual_vs_target", "period_comparison", "comparison"
5. Statistical: "correlation", "covariance", "std", "variance", "percentile", "quartile", "outlier_detection", "distribution_analysis"
6. Time Series: "trend", "daily_trend", "weekly_trend", "monthly_trend", "quarterly_trend", "yearly_trend", "growth_rate", "month_over_month", "year_over_year", "moving_average", "cumulative_sum", "cumulative_total"
7. Business KPIs: "profit_margin", "average_order_value", "return_rate", "cancellation_rate", "delivery_rate", "category_contribution", "regional_contribution"
8. Multi-Step Analytics: "top_n_contribution", "above_average_filter", "extreme_combination"
9. System: "data_quality", "missing_column"

UNIVERSAL JSON PLAN STRUCTURE:
{
  "operation": "<operation_name>",
  "metric_column": "<column_or_null>",
  "comparison_column": "<column_or_null>",
  "group_by": ["<column_1>", "<column_2>"],
  "compare_groups": ["<group_A>", "<group_B>"],
  "filters": [
    {"column": "<col>", "operator": "== | != | > | < | >= | <=", "value": "<val>"}
  ],
  "date_column": "<date_column_or_null>",
  "date_grouping": "<day | week | month | quarter | year | null>",
  "sort": "<ascending | descending | none>",
  "limit": <number_or_null>,
  "percentile": <number_or_null>,
  "window": <number_or_null>,
  "per_group": <true | false>,
  "missing_entity": "<term_or_null>"
}
"""

        user_prompt = f"""
RECENT CONVERSATION HISTORY:
{context_history}

{schema_summary}

USER QUESTION: {question}

Construct the exact JSON execution plan:
"""

        if os.environ.get("FAST_TEST") == "1" or not getattr(self.llm, "api_key", None):
            plan = self._fallback_plan(question, profile, context_history)
        else:
            try:
                raw_response = self.llm.completion(system_prompt, user_prompt, json_mode=True)
                plan = self._clean_and_parse_json(raw_response)
            except Exception:
                plan = self._fallback_plan(question, profile, context_history)

        # Detect per_group intent directly from question phrasing
        q_lower = question.lower()
        if any(w in q_lower for w in ["in each", "inside each", "within each", "per each", "for each"]):
            plan["per_group"] = True

        # Validate and resolve columns dynamically against actual columns
        plan = self._resolve_plan_columns(plan, question, profile, context_history)
        return plan

    def _resolve_plan_columns(self, plan: Dict[str, Any], question: str, profile: Dict[str, Any], context_history: str = "") -> Dict[str, Any]:
        """
        Validates planned columns against actual DataFrame columns using dynamic matching.
        Resolves follow-up pronouns and multi-step constraints.
        """
        all_cols = profile.get("columns", [])
        num_cols = profile.get("numeric_cols", [])
        cat_cols = profile.get("categorical_cols", [])
        op = plan.get("operation", "sum")
        q_lower = question.lower()

        if op in ["data_quality", "missing_column"]:
            return plan

        # Resolve follow-up references ("its", "that", "this")
        if any(pronoun in q_lower.split() for pronoun in ["its", "it", "that", "this"]):
            if context_history:
                entity_match = re.search(r"Focus Entity:\s*([a-zA-Z0-9_\s]+)", context_history)
                group_match = re.search(r"'group_by':\s*\[(?:'|\")([a-zA-Z0-9_]+)(?:'|\")", context_history)
                ent = entity_match.group(1).strip() if entity_match else None
                grp = group_match.group(1).strip() if group_match else None

                if not ent:
                    res_match = re.search(r"Result:\s*\{'([a-zA-Z0-9_\s]+)':", context_history)
                    if res_match:
                        ent = res_match.group(1).strip()

                if ent:
                    if not grp and cat_cols:
                        grp = cat_cols[0]
                    if grp:
                        plan["filters"] = [{
                            "column": grp,
                            "operator": "==",
                            "value": ent
                        }]

        # Resolve metric_column
        metric = plan.get("metric_column")
        if metric:
            matched_metric = find_best_column_match(metric, all_cols)
            if matched_metric:
                plan["metric_column"] = matched_metric
            else:
                plan["operation"] = "missing_column"
                plan["missing_entity"] = metric
                return plan

        # Resolve comparison_column
        comp = plan.get("comparison_column")
        if comp:
            matched_comp = find_best_column_match(comp, all_cols)
            if matched_comp:
                plan["comparison_column"] = matched_comp
            else:
                plan["comparison_column"] = None

        # Resolve group_by columns
        raw_group = plan.get("group_by") or []
        if isinstance(raw_group, str):
            raw_group = [raw_group]
        resolved_groups = []
        for g in raw_group:
            m = find_best_column_match(g, all_cols)
            if m and m not in resolved_groups:
                resolved_groups.append(m)

        # Detect partitioned / nested grouping intent from question text (e.g. "top 3 products inside each region")
        mentioned_cats = []
        words = q_lower.split()
        for n in range(3, 0, -1):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                m = find_best_column_match(phrase, cat_cols)
                if m and m not in mentioned_cats:
                    mentioned_cats.append(m)

        part_match = re.search(r'(?:inside|within|in|for|per)\s+(?:each|every)\s+([a-zA-Z0-9_\s]+)', q_lower)
        if part_match and len(mentioned_cats) >= 2:
            container_term = part_match.group(1).strip()
            container_col = find_best_column_match(container_term, cat_cols)
            if container_col:
                item_cols = [c for c in mentioned_cats if c != container_col]
                if item_cols:
                    resolved_groups = [container_col, item_cols[0]]
                    plan["per_group"] = True
                    plan["operation"] = "top_n"

        # Extract explicit limit if present in question (e.g. "top 3")
        limit_match = re.search(r'\b(?:top|bottom|first|last)\s+(\d+)\b', q_lower)
        if limit_match:
            plan["limit"] = int(limit_match.group(1))

        # If 2 categories were detected with per_group, ensure both are in group_by
        if plan.get("per_group") and len(mentioned_cats) >= 2 and len(resolved_groups) < 2:
            resolved_groups = mentioned_cats[:2]

        plan["group_by"] = resolved_groups

        # Resolve date_column
        date_col = plan.get("date_column")
        if date_col:
            m_date = find_best_column_match(date_col, all_cols)
            if m_date:
                plan["date_column"] = m_date
            elif profile.get("date_cols"):
                plan["date_column"] = profile.get("date_cols")[0]

        return plan

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Ensures clean JSON parsing and strips markdown code blocks if present."""
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip("` \n\r\t")
        return json.loads(cleaned)

    def _fallback_plan(self, question: str, profile: Dict[str, Any], context_history: str = "") -> Dict[str, Any]:
        """Heuristic fallback plan generator if LLM is unreachable."""
        q = question.lower()
        all_cols = profile.get("columns", [])
        num_cols = profile.get("numeric_cols", [])
        cat_cols = profile.get("categorical_cols", [])

        if any(w in q for w in ["quality", "missing", "duplicate", "null", "audit", "health"]):
            return {"operation": "data_quality"}

        # Multi-Step patterns
        if "percentage of total" in q or ("percentage" in q and "top" in q):
            return {
                "operation": "top_n_contribution",
                "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None),
                "group_by": [find_best_column_match("product", cat_cols) or (cat_cols[0] if cat_cols else None)],
                "limit": 3
            }

        if "more than the average" in q or "above average" in q:
            if "profit margin" in q:
                return {
                    "operation": "extreme_combination",
                    "group_by": [find_best_column_match("product", cat_cols) or "Product"]
                }
            return {
                "operation": "above_average_filter",
                "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None),
                "group_by": [find_best_column_match("customer_id", all_cols) or (cat_cols[0] if cat_cols else None)]
            }

        if "compare" in q and ("between" in q or "difference" in q):
            comp_match = re.findall(r'\b([A-Z][a-z]+)\b', question)
            return {
                "operation": "difference_between_groups",
                "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None),
                "group_by": [find_best_column_match("region", cat_cols) or "Region"],
                "compare_groups": comp_match[:2] if len(comp_match) >= 2 else ["North", "South"]
            }

        if "target" in q:
            return {
                "operation": "actual_vs_target",
                "metric_column": find_best_column_match("sales", all_cols) or "Sales",
                "comparison_column": find_best_column_match("target_sales", all_cols) or "Target_Sales"
            }

        if "return rate" in q: return {"operation": "return_rate"}
        if "cancellation rate" in q: return {"operation": "cancellation_rate"}
        if "delivery rate" in q: return {"operation": "delivery_rate"}
        if "profit margin" in q or "margin" in q: return {"operation": "profit_margin"}
        if "distribution" in q or "skew" in q: return {"operation": "distribution_analysis", "metric_column": num_cols[0] if num_cols else None}

        date_cols = profile.get("date_cols", [])

        # Time Series
        if "monthly" in q and "trend" in q:
            return {"operation": "monthly_trend", "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None), "date_column": date_cols[0] if date_cols else None}
        if "yearly" in q and "trend" in q:
            return {"operation": "yearly_trend", "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None), "date_column": date_cols[0] if date_cols else None}
        if "year over year" in q or "yoy" in q:
            return {"operation": "year_over_year", "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None), "date_column": date_cols[0] if date_cols else None}
        if "growth" in q:
            return {"operation": "growth_rate", "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None), "date_column": date_cols[0] if date_cols else None}
        if "moving average" in q:
            return {"operation": "moving_average", "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None), "window": 3, "date_column": date_cols[0] if date_cols else None}
        if "cumulative" in q:
            return {"operation": "cumulative_total", "metric_column": find_best_column_match("sales", all_cols) or (num_cols[0] if num_cols else None), "date_column": date_cols[0] if date_cols else None}

        # Match columns mentioned in question
        words = re.findall(r'\b\w+\b', q)
        matched_num = None
        for w in words:
            m = find_best_column_match(w, num_cols)
            if m:
                matched_num = m
                break

        matched_cats = []
        for w in words:
            m = find_best_column_match(w, cat_cols)
            if m and m not in matched_cats:
                matched_cats.append(m)

        # Statistical Operations
        if "variance" in q:
            return {"operation": "variance", "metric_column": matched_num or (num_cols[0] if num_cols else None)}
        if "standard deviation" in q or "std" in q:
            return {"operation": "std", "metric_column": matched_num or (num_cols[0] if num_cols else None)}
        if "percentile" in q or "quantile" in q:
            p_match = re.search(r'(\d+)(?:th|st|nd|rd)?\s*(?:percentile|quantile)', q)
            p = int(p_match.group(1)) if p_match else 90
            return {"operation": "percentile", "metric_column": matched_num or (num_cols[0] if num_cols else None), "percentile": p}
        if "correlation" in q:
            comp_metric = find_best_column_match("sales", all_cols) if matched_num != "Sales" else find_best_column_match("marketing_spend", all_cols)
            return {"operation": "correlation", "metric_column": matched_num or "Marketing_Spend", "comparison_column": comp_metric or "Sales"}
        if "covariance" in q:
            comp_metric = find_best_column_match("profit", all_cols) if matched_num != "Profit" else find_best_column_match("sales", all_cols)
            return {"operation": "covariance", "metric_column": matched_num or "Sales", "comparison_column": comp_metric or "Profit"}
        if "outlier" in q:
            return {"operation": "outlier_detection", "metric_column": matched_num or (num_cols[0] if num_cols else None)}

        # Mathematical & Business KPIs
        if "average order value" in q or "aov" in q:
            return {"operation": "average_order_value"}
        if "ratio" in q:
            comp_metric = find_best_column_match("marketing_spend", all_cols)
            return {"operation": "ratio", "metric_column": matched_num or "Sales", "comparison_column": comp_metric or "Marketing_Spend"}
        if "percentage difference" in q or ("percentage" in q and "difference" in q):
            comp_metric = find_best_column_match("total_cost", all_cols) or find_best_column_match("cost", all_cols)
            return {"operation": "percentage_difference", "metric_column": matched_num or "Sales", "comparison_column": comp_metric or "Total_Cost"}
        if "difference" in q or "subtraction" in q:
            comp_metric = find_best_column_match("total_cost", all_cols) or find_best_column_match("cost", all_cols)
            return {"operation": "difference", "metric_column": matched_num or "Sales", "comparison_column": comp_metric or "Total_Cost"}
        if "contribution" in q and ("percentage" in q or "revenue" in q or "%" in q):
            return {"operation": "percentage_contribution", "metric_column": matched_num or "Sales", "group_by": matched_cats or ["Region"], "limit": 5}

        # Detect Basic Operations
        op = "sum"
        if any(w in q for w in ["average", "avg", "mean"]): op = "mean"
        elif any(w in q for w in ["median", "middle"]): op = "median"
        elif any(w in q for w in ["max", "maximum", "highest", "top", "best"]): op = "max"
        elif any(w in q for w in ["min", "minimum", "lowest", "worst", "bottom"]): op = "min"
        elif any(w in q for w in ["count", "how many", "number of"]): op = "count"
        elif any(w in q for w in ["unique", "distinct"]): op = "distinct_values"

        # Check for explicit filters in question
        filters = []
        # Numeric filter: e.g. experience > 5
        exp_match = re.search(r'experience\s*(?:greater than|>|above)\s*(\d+)', q)
        if exp_match:
            exp_col = find_best_column_match("experience_years", all_cols)
            if exp_col:
                filters.append({"column": exp_col, "operator": ">", "value": float(exp_match.group(1))})

        # Date filter: e.g. after 2024-01-01
        date_match = re.search(r'(?:after|since|>)\s*(\d{4}-\d{2}-\d{2})', q)
        if date_match:
            d_col = date_cols[0] if date_cols else "Order_Date"
            filters.append({"column": d_col, "operator": ">", "value": date_match.group(1)})

        # Region/Category filter: e.g. in North, in Electronics
        for reg in ["north", "south", "east", "west", "central"]:
            if reg in q and "region" not in matched_cats:
                reg_col = find_best_column_match("region", cat_cols)
                if reg_col:
                    filters.append({"column": reg_col, "operator": "==", "value": reg.capitalize()})
                    break

        for cat in ["electronics", "furniture", "clothing", "office supplies", "accessories"]:
            if cat in q and "category" not in matched_cats:
                cat_col = find_best_column_match("category", cat_cols)
                if cat_col:
                    filters.append({"column": cat_col, "operator": "==", "value": cat.title()})
                    break

        # Check if question asked about a missing concept
        missing_terms = ["churn", "retention", "nps", "bounce", "tax", "dividend", "depreciation"]
        for term in missing_terms:
            if term in q and not find_best_column_match(term, all_cols):
                return {
                    "operation": "missing_column",
                    "missing_entity": term
                }

        metric = matched_num or (num_cols[0] if num_cols else None)
        limit_val = 5 if "5" in q else (3 if "3" in q else 10)

        if any(w in q for w in ["bottom", "lowest", "least"]):
            return {
                "operation": "bottom_n",
                "metric_column": metric,
                "group_by": matched_cats[:2] if matched_cats else [cat_cols[0] if cat_cols else "Department"],
                "sort": "ascending",
                "limit": limit_val,
                "filters": filters
            }

        if any(w in q for w in ["top", "highest", "best"]):
            sub_ag = "mean" if any(w in q for w in ["average", "avg", "mean"]) else "sum"
            return {
                "operation": "top_n",
                "metric_column": metric,
                "group_by": matched_cats[:2] if matched_cats else [cat_cols[0] if cat_cols else "Product"],
                "sort": "descending",
                "aggregation": sub_ag,
                "limit": limit_val,
                "filters": filters
            }

        return {
            "operation": "group_by" if matched_cats else op,
            "metric_column": metric,
            "group_by": matched_cats[:2] if matched_cats else [],
            "sort": "descending",
            "limit": limit_val,
            "filters": filters
        }