import re
from services.data_loader import find_best_column_match
from services.data_analyzer import (
    validate_operation,
    calculate_single_metric,
    calculate_group_breakdown,
    calculate_time_trend,
    get_ranking,
    analyze_sales_drop
)

OPERATIONS = {
    "sum": ["total", "sum", "overall", "combined", "add"],
    "mean": ["average", "avg", "mean"],
    "min": ["minimum", "min", "lowest", "smallest", "worst"],
    "max": ["maximum", "max", "highest", "largest", "top", "best"],
    "count": ["count", "number of", "how many", "total records"],
    "median": ["median", "middle"]
}

def detect_operation(question_text: str) -> str:
    """Detects requested math operation from question keywords."""
    q = question_text.lower()
    for op, keywords in OPERATIONS.items():
        if any(kw in q for kw in keywords):
            return op
    return "sum"

def extract_column_mentions(question_text: str, df_columns) -> list:
    """Extracts matching columns from full query text, handling multi-word column names."""
    q = question_text.lower()
    words = q.split()
    matched_cols = []
    
    # Check 3-word, 2-word, and 1-word n-grams for column matching
    for n in range(3, 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i+n])
            match = find_best_column_match(phrase, df_columns)
            if match and match not in matched_cols:
                matched_cols.append(match)
                
    return matched_cols

def handle_question(question: str, df, profile: dict) -> dict:
    """Universal NLP query handler with validation, ambiguity checks, rankings, and charts."""
    q = question.lower().strip()
    cols = list(df.columns)
    num_cols = profile.get("numeric_cols", [])
    cat_cols = profile.get("categorical_cols", [])
    date_cols = profile.get("date_cols", [])

    op = detect_operation(q)

    # Missing column check for common requested concepts
    known_concepts = ["profit", "salary", "revenue", "sales", "discount", "cost", "quantity", "price", "rating", "expense", "budget"]
    for concept in known_concepts:
        if concept in q and not find_best_column_match(concept, cols):
            num_str = " and ".join(num_cols) if len(num_cols) <= 2 else ", ".join(num_cols)
            return {
                "answer": f"I couldn't find a {concept}-related column in this dataset. Available numeric columns are {num_str or 'none'}.",
                "chart": None
            }

    # 1. SALES DROP / ROOT-CAUSE ANALYSIS CHECK
    if "drop" in q or "decline" in q or "decrease" in q or "why" in q:
        date_col = date_cols[0] if date_cols else None
        sales_col = num_cols[0] if num_cols else None
        
        if date_col and sales_col:
            months = ['january', 'february', 'march', 'april', 'may', 'june', 
                      'july', 'august', 'september', 'october', 'november', 'december']
            target_month = next((m for m in months if m in q), None)
            
            if target_month:
                prod_col = next((c for c in cols if 'product' in c.lower() or 'item' in c.lower()), None)
                reg_col = next((c for c in cols if 'region' in c.lower() or 'city' in c.lower() or 'state' in c.lower()), None)
                cat_col = next((c for c in cols if 'cat' in c.lower() or 'type' in c.lower()), None)
                
                explanation = analyze_sales_drop(
                    df, date_col, sales_col, target_month,
                    product_col=prod_col, region_col=reg_col, category_col=cat_col
                )
                return {"answer": explanation, "chart": None}

    # 2. AMBIGUITY CHECK: Total/average requested without metric column
    matched_columns = extract_column_mentions(q, cols)
    if not matched_columns and op in ["sum", "mean", "median"] and len(num_cols) > 1:
        options = ", ".join([f"**{c}**" for c in num_cols])
        return {
            "answer": f"Multiple numeric columns detected. Which column would you like to calculate the **{op}** for?\n\nOptions: {options}",
            "chart": None
        }

    # 3. DETECT TARGET METRIC AND GROUPING COLUMNS
    group_col = None
    target_metric = None

    # Check for grouping phrases ("by X", "per X", "for each X")
    group_match = re.search(r'(?:by|per|across|for each)\s+([a-zA-Z0-9_\s]+)', q)
    if group_match:
        group_term = group_match.group(1).strip()
        group_col = find_best_column_match(group_term, cols)

    # Assign target metric
    for col in matched_columns:
        if col != group_col:
            target_metric = col
            break

    if not target_metric and num_cols:
        target_metric = num_cols[0]

    # 4. RANKING ANALYSIS (Top / Highest / Lowest)
    if any(w in q for w in ["highest", "top", "best", "lowest", "worst"]) and group_col and target_metric:
        is_highest = not any(w in q for w in ["lowest", "worst", "bottom"])
        ranking = get_ranking(df, group_col, target_metric, highest=is_highest)
        if ranking:
            label = "highest" if is_highest else "lowest"
            return {
                "answer": f"The **{label}** {group_col} by **{target_metric}** is **{ranking['name']}** with **{ranking['value']:,.2f}**.",
                "chart": None
            }

    # 5. OPERATION VALIDATION
    if target_metric:
        valid, err_msg = validate_operation(df, target_metric, op, profile)
        if not valid:
            return {"answer": err_msg, "chart": None}

    # 6. EXECUTE GROUPED ANALYSIS (With Visual Chart Output)
    if group_col and target_metric:
        data_dict, chart = calculate_group_breakdown(df, target_metric, group_col, op)
        formatted = "\n".join([f"* **{k}**: {v:,.2f}" for k, v in data_dict.items()])
        return {
            "answer": f"**{op.capitalize()} of {target_metric} by {group_col}:**\n\n{formatted}",
            "chart": chart
        }

    # 7. EXECUTE TIME-SERIES TREND ANALYSIS
    if ("trend" in q or "monthly" in q or "over time" in q) and date_cols:
        date_col_target = date_cols[0]
        metric = target_metric or (num_cols[0] if num_cols else None)
        if metric:
            data_dict, chart = calculate_time_trend(df, metric, date_col_target, op)
            formatted = "\n".join([f"* **{k}**: {v:,.2f}" for k, v in data_dict.items()])
            return {
                "answer": f"**Monthly {op.capitalize()} trend for {metric}:**\n\n{formatted}",
                "chart": chart
            }

    # 8. EXECUTE SINGLE METRIC CALCULATION
    if target_metric:
        val = calculate_single_metric(df, target_metric, op)
        if isinstance(val, (int, float)):
            return {"answer": f"The overall **{op}** for **{target_metric}** is **{val:,.2f}**.", "chart": None}
        return {"answer": f"The **{op}** for **{target_metric}** is **{val}**.", "chart": None}

    # 9. DEFAULT FALLBACK
    return {
        "answer": "I couldn't infer the exact analysis from your question. Try asking:\n" +
                  "\n".join([f"* {sq}" for sq in profile.get("suggested_questions", [])]),
        "chart": None
    }