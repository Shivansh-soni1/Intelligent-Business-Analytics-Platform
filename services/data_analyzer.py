import pandas as pd

def validate_operation(df, column, operation, profile):
    """Validates if the requested operation can be applied to the column type."""
    if column not in df.columns:
        return False, f"Column '{column}' does not exist in the dataset."

    num_cols = profile.get("numeric_cols", [])
    
    if operation in ["sum", "mean", "average", "median"] and column not in num_cols:
        return False, f"Cannot calculate **{operation}** on text/non-numeric column **'{column}'**. Try using 'count' or pick a numeric column like: {', '.join(num_cols)}."
    
    return True, ""

def calculate_single_metric(df, column, operation):
    """Calculates summary metric (sum, mean, min, max, median, count)."""
    series = df[column]
    if operation in ["sum"]:
        return float(series.sum())
    elif operation in ["mean", "average"]:
        return float(series.mean())
    elif operation in ["median"]:
        return float(series.median())
    elif operation in ["min"]:
        return float(series.min()) if pd.api.types.is_numeric_dtype(series) else str(series.min())
    elif operation in ["max"]:
        return float(series.max()) if pd.api.types.is_numeric_dtype(series) else str(series.max())
    elif operation in ["count"]:
        return int(series.count())
    return None

def get_ranking(df, group_col, metric_col, highest=True):
    """Finds top or bottom category/item based on sum of metric."""
    if not group_col or not metric_col or group_col not in df.columns or metric_col not in df.columns:
        return None
    
    grouped = df.groupby(group_col)[metric_col].sum()
    if grouped.empty:
        return None
        
    target_item = grouped.idxmax() if highest else grouped.idxmin()
    target_val = float(grouped.max() if highest else grouped.min())
    return {"name": str(target_item), "value": target_val}

def calculate_group_breakdown(df, metric_col, group_col, operation="sum", limit=10):
    """Calculates grouped metrics and generates a Chart.js structure."""
    if operation in ["mean", "average"]:
        grouped = df.groupby(group_col)[metric_col].mean()
    elif operation == "count":
        grouped = df.groupby(group_col)[metric_col].count()
    else:
        grouped = df.groupby(group_col)[metric_col].sum()

    grouped = grouped.round(2).sort_values(ascending=False).head(limit)
    labels = [str(k) for k in grouped.index]
    values = [float(v) for v in grouped.values]

    # Select chart type dynamically based on label count
    chart_type = "pie" if len(labels) <= 4 else "bar"
    
    chart_payload = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [{
                "label": f"{operation.capitalize()} of {metric_col}",
                "data": values,
                "backgroundColor": [
                    "#3b82f6", "#10b981", "#f59e0b", "#ef4444", 
                    "#8b5cf6", "#ec4899", "#14b8a6", "#6366f1"
                ]
            }]
        },
        "options": {
            "responsive": True,
            "plugins": {"legend": {"display": chart_type == "pie"}}
        }
    }

    return grouped.to_dict(), chart_payload

def calculate_time_trend(df, metric_col, date_col, operation="sum"):
    """Calculates temporal trends and produces a Chart.js line graph payload."""
    temp_df = df.copy()
    temp_df['YearMonth'] = pd.to_datetime(temp_df[date_col]).dt.to_period('M')
    
    if operation in ["mean", "average"]:
        monthly = temp_df.groupby('YearMonth')[metric_col].mean()
    else:
        monthly = temp_df.groupby('YearMonth')[metric_col].sum()

    monthly = monthly.round(2)
    labels = [str(k) for k in monthly.index]
    values = [float(v) for v in monthly.values]

    chart_payload = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": f"Monthly {operation.capitalize()} of {metric_col}",
                "data": values,
                "borderColor": "#3b82f6",
                "backgroundColor": "rgba(59, 130, 246, 0.1)",
                "fill": True,
                "tension": 0.3
            }]
        },
        "options": {
            "responsive": True,
            "plugins": {"legend": {"display": True}}
        }
    }

    return monthly.to_dict(), chart_payload

def analyze_sales_drop(df, date_col, sales_col, target_month_str, product_col=None, region_col=None, category_col=None):
    """Compares target month against previous month to analyze sales drop drivers."""
    if not date_col or not sales_col or not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        return "Date column is missing or improperly formatted to perform monthly drop analysis."

    temp_df = df.copy()
    temp_df['YearMonth'] = temp_df[date_col].dt.to_period('M')
    
    periods = sorted(temp_df['YearMonth'].unique())
    target_period = None
    
    for p in periods:
        p_str = str(p).lower()
        month_name = p.strftime('%B').lower()
        if target_month_str.lower() in p_str or target_month_str.lower() in month_name:
            target_period = p
            break

    if not target_period:
        return f"Could not find transaction data for '{target_month_str}'."
    
    idx = periods.index(target_period)
    if idx == 0:
        return f"Cannot analyze drop for {target_period} because there is no prior month data for comparison."
        
    prev_period = periods[idx - 1]
    curr_df = temp_df[temp_df['YearMonth'] == target_period]
    prev_df = temp_df[temp_df['YearMonth'] == prev_period]
    
    curr_sales = curr_df[sales_col].sum()
    prev_sales = prev_df[sales_col].sum()
    
    diff = curr_sales - prev_sales
    pct_change = ((curr_sales - prev_sales) / prev_sales) * 100 if prev_sales > 0 else 0
    
    if diff >= 0:
        return f"Sales did not drop in {target_period}. They actually increased by {abs(pct_change):.1f}% compared to {prev_period}."
    
    insights = []
    for col_name, label in [(category_col, 'category'), (region_col, 'region'), (product_col, 'product')]:
        if col_name and col_name in df.columns:
            prev_grp = prev_df.groupby(col_name)[sales_col].sum()
            curr_grp = curr_df.groupby(col_name)[sales_col].sum()
            
            combined = pd.DataFrame({'prev': prev_grp, 'curr': curr_grp}).fillna(0)
            combined['drop'] = combined['curr'] - combined['prev']
            
            biggest_drop_item = combined['drop'].idxmin()
            biggest_drop_val = abs(combined['drop'].min())
            
            if biggest_drop_val > 0:
                insights.append(f"the **{biggest_drop_item}** {label} (decline of ${biggest_drop_val:,.2f})")

    explanation = (
        f"Sales dropped by **{abs(pct_change):.1f}%** in **{target_period}** compared to **{prev_period}** "
        f"(Total decrease: **${abs(diff):.2f}**).\n\n"
        f"**Key Drivers:** Based on available data, the decline was primarily driven by "
    )
    
    explanation += ", ".join(insights) + "." if insights else "general lower volume across all categories."
    return explanation