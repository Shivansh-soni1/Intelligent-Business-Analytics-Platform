import pandas as pd
import numpy as np
import re
from typing import Dict, Any, Tuple, List, Optional
from services.data_loader import find_best_column_match

class PandasExecutor:
    """
    Comprehensive, high-performance execution engine supporting 40+ analytical operations.
    Strictly avoids eval() or arbitrary code execution.
    Completely dataset-driven: never assumes fixed schemas or mandatory business columns.
    """

    ALLOWED_OPERATIONS = {
        # Basic
        "sum", "mean", "median", "min", "max", "count", "nunique", "distinct_values",
        # Grouping & Ranking
        "group_by", "top_n", "bottom_n", "filter", "sort", "ranking", "partitioned_top_n",
        # Mathematical
        "addition", "subtraction", "multiplication", "division", "percentage", "formula",
        "percentage_contribution", "percentage_difference", "difference", "ratio", "comparison",
        "difference_between_groups", "actual_vs_target",
        # Statistics
        "correlation", "covariance", "std", "variance", "percentile", "quartile",
        "outlier_detection", "distribution_analysis",
        # Time Analysis
        "trend", "daily_trend", "weekly_trend", "monthly_trend", "quarterly_trend", "yearly_trend",
        "growth_rate", "month_over_month", "year_over_year", "moving_average", "cumulative_sum", "cumulative_total",
        "period_comparison", "current_vs_previous_period",
        # Business KPIs
        "revenue", "profit", "profit_margin", "average_order_value", "conversion_rate", "ctr",
        "return_rate", "cancellation_rate", "delivery_rate", "customer_growth",
        "category_contribution", "regional_contribution",
        # Multi-Step Analytics
        "top_n_contribution", "above_average_filter", "extreme_combination",
        # System
        "data_quality", "missing_column"
    }

    def validate_plan(self, plan: Dict[str, Any], df: pd.DataFrame, profile: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates operations and resolves planned columns dynamically.
        Never crashes when an expected business column is absent.
        """
        op = plan.get("operation", "sum")
        if op not in self.ALLOWED_OPERATIONS:
            return False, f"Unsupported operation '{op}'."

        if op in ["data_quality", "missing_column"]:
            return True, ""

        cols = list(df.columns)
        num_cols = profile.get("numeric_cols", [])
        cat_cols = profile.get("categorical_cols", [])

        # Validate metric column for operations that require it
        metric = plan.get("metric_column")
        if metric:
            if metric not in cols:
                matched = find_best_column_match(metric, cols)
                if matched:
                    plan["metric_column"] = matched
                else:
                    num_str = " and ".join(num_cols) if len(num_cols) <= 2 else ", ".join(num_cols)
                    return False, f"I couldn't find a '{metric}'-related column in this dataset. Available numeric columns are {num_str or 'none'}."
        elif op in [
            "sum", "mean", "median", "std", "variance", "outlier_detection",
            "percentile", "quartile", "distribution_analysis", "moving_average",
            "cumulative_sum", "cumulative_total", "growth_rate", "month_over_month",
            "year_over_year", "percentage_contribution", "top_n_contribution"
        ]:
            if num_cols:
                plan["metric_column"] = num_cols[0]
            else:
                return False, f"This dataset does not have any numeric columns to perform a '{op}' calculation. Available columns are: {', '.join(cols[:6])}."

        # Validate group_by columns
        groups = plan.get("group_by") or []
        if isinstance(groups, str):
            groups = [groups]
            plan["group_by"] = groups

        for g in groups:
            if g not in cols:
                m = find_best_column_match(g, cols)
                if m:
                    idx = groups.index(g)
                    groups[idx] = m
                else:
                    cat_str = " and ".join(cat_cols) if len(cat_cols) <= 2 else ", ".join(cat_cols)
                    return False, f"I couldn't find the column '{g}' to group by in this dataset. Available categorical columns are {cat_str or 'none'}."

        return True, ""

    def execute(self, plan: Dict[str, Any], df: pd.DataFrame, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the verified analytical plan safely on the DataFrame."""
        if df.empty or len(df) == 0:
            return {"success": True, "data": "The uploaded dataset is empty (0 records).", "chart": None}

        op = plan.get("operation", "sum")

        # ----------------------------------------------------
        # ROUTE 0: Missing Column Notification (Rule 18 & 19)
        # ----------------------------------------------------
        if op == "missing_column":
            entity = plan.get("missing_entity") or "requested"
            num_cols = profile.get("numeric_cols", [])
            if num_cols:
                num_str = " and ".join(num_cols) if len(num_cols) <= 2 else ", ".join(num_cols)
                msg = f"I couldn't find a {entity}-related column in this dataset. Available numeric columns are {num_str}."
            else:
                all_cols = profile.get("columns", list(df.columns))
                msg = f"I couldn't find a {entity}-related column in this dataset. Available columns are {', '.join(all_cols[:6])}."
            return {"success": False, "is_user_guidance": True, "error": msg, "data": None, "chart": None}

        # Validate plan
        valid, err_msg = self.validate_plan(plan, df, profile)
        if not valid:
            return {"success": False, "is_user_guidance": True, "error": err_msg, "data": None, "chart": None}

        working_df = df.copy()

        # ----------------------------------------------------
        # 1. Apply Filters Safely
        # ----------------------------------------------------
        for f in plan.get("filters") or []:
            col = f.get("column")
            op_f = f.get("operator")
            val = f.get("value")
            
            if col not in working_df.columns:
                col = find_best_column_match(col, list(working_df.columns))
                
            if col and col in working_df.columns and val is not None:
                try:
                    clean_val = str(val).split(":")[0].strip().strip("'\"")
                    if op_f == "==":
                        working_df = working_df[working_df[col].astype(str).str.strip().str.lower() == clean_val.lower()]
                    elif op_f == "!=":
                        working_df = working_df[working_df[col].astype(str).str.strip().str.lower() != clean_val.lower()]
                    elif op_f in [">", "<", ">=", "<="]:
                        val_num = float(clean_val)
                        if op_f == ">": working_df = working_df[working_df[col] > val_num]
                        elif op_f == "<": working_df = working_df[working_df[col] < val_num]
                        elif op_f == ">=": working_df = working_df[working_df[col] >= val_num]
                        elif op_f == "<=": working_df = working_df[working_df[col] <= val_num]
                except Exception:
                    pass

        if working_df.empty:
            return {"success": True, "data": "No matching records found for the applied filters.", "chart": None}

        metric = plan.get("metric_column")
        if not metric and profile.get("numeric_cols"):
            metric = profile.get("numeric_cols")[0]

        # ----------------------------------------------------
        # ROUTE 1: Data Quality Audit
        # ----------------------------------------------------
        if op == "data_quality":
            audit = profile.get("quality_audit", {})
            return {"success": True, "data": audit, "chart": None}

        # ----------------------------------------------------
        # ROUTE 2: Distinct Values Listing
        # ----------------------------------------------------
        if op == "distinct_values":
            target_col = metric or (plan.get("group_by", [None])[0]) or (profile.get("categorical_cols", [working_df.columns[0]])[0])
            if target_col in working_df.columns:
                unique_vals = [str(x) for x in working_df[target_col].dropna().unique()[:30]]
                return {
                    "success": True,
                    "data": {
                        "column": target_col,
                        "distinct_count": int(working_df[target_col].nunique()),
                        "sample_distinct_values": unique_vals
                    },
                    "chart": None
                }

        # ----------------------------------------------------
        # ROUTE 3: Multi-Step: Top-N Percentage Contribution
        # (e.g. "What percentage of total sales comes from the top 3 products?")
        # ----------------------------------------------------
        if op == "top_n_contribution":
            g_col = plan.get("group_by", [None])[0] or (profile.get("categorical_cols", [None])[0])
            if g_col and g_col in working_df.columns and metric and metric in working_df.columns:
                n = plan.get("limit") or 3
                total_val = float(working_df[metric].sum())
                top_grouped = working_df.groupby(g_col)[metric].sum().sort_values(ascending=False).head(n)
                top_sum = float(top_grouped.sum())
                pct = round((top_sum / total_val * 100.0), 2) if total_val > 0 else 0.0
                
                res_dict = {
                    f"top_{n}_{g_col}": {str(k): round(float(v), 2) for k, v in top_grouped.items()},
                    f"top_{n}_total_{metric}": round(top_sum, 2),
                    f"overall_total_{metric}": round(total_val, 2),
                    "percentage_contribution": pct
                }
                chart_payload = self._build_chart("pie", {str(k): float(v) for k, v in top_grouped.items()}, f"Top {n} {g_col}", g_col)
                return {"success": True, "data": res_dict, "chart": chart_payload}

        # ----------------------------------------------------
        # ROUTE 4: Multi-Step: Above-Average Filter
        # (e.g. "Which customers purchased more than the average customer spending?")
        # ----------------------------------------------------
        if op == "above_average_filter":
            g_col = plan.get("group_by", [None])[0] or (profile.get("identifier_cols", [None])[0]) or (profile.get("categorical_cols", [None])[0])
            if g_col and g_col in working_df.columns and metric and metric in working_df.columns:
                grouped = working_df.groupby(g_col)[metric].sum()
                avg_spending = float(grouped.mean())
                qualifying = grouped[grouped > avg_spending].sort_values(ascending=False)
                
                res_dict = {
                    "entity": g_col,
                    "metric": metric,
                    "average_threshold": round(avg_spending, 2),
                    "qualifying_count": int(len(qualifying)),
                    "total_count": int(len(grouped)),
                    "top_qualifying_records": {str(k): round(float(v), 2) for k, v in qualifying.head(10).items()}
                }
                return {"success": True, "data": res_dict, "chart": None}

        # ----------------------------------------------------
        # ROUTE 5: Multi-Step: Extreme Combinations
        # (e.g. "Which product has highest sales but lowest profit margin?")
        # ----------------------------------------------------
        if op == "extreme_combination":
            g_col = plan.get("group_by", [None])[0] or "Product"
            if g_col not in working_df.columns:
                g_col = find_best_column_match(g_col, list(working_df.columns)) or (profile.get("categorical_cols", [None])[0])
                
            sales_col = find_best_column_match("sales", list(working_df.columns))
            profit_col = find_best_column_match("profit", list(working_df.columns))
            
            if g_col and sales_col and profit_col and g_col in working_df.columns:
                grouped = working_df.groupby(g_col).agg({sales_col: "sum", profit_col: "sum"})
                grouped["Profit_Margin"] = (grouped[profit_col] / grouped[sales_col].replace(0, np.nan)) * 100.0
                grouped = grouped.dropna(subset=["Profit_Margin"])
                
                best_sales_item = grouped[sales_col].idxmax()
                lowest_margin_item = grouped["Profit_Margin"].idxmin()
                
                # Cross check: Above avg sales and below avg margin
                mean_sales = grouped[sales_col].mean()
                mean_margin = grouped["Profit_Margin"].mean()
                niche = grouped[(grouped[sales_col] > mean_sales) & (grouped["Profit_Margin"] < mean_margin)]
                
                res_dict = {
                    "highest_sales_item": {
                        "name": str(best_sales_item),
                        "sales": round(float(grouped.loc[best_sales_item, sales_col]), 2),
                        "profit_margin": round(float(grouped.loc[best_sales_item, "Profit_Margin"]), 2)
                    },
                    "lowest_profit_margin_item": {
                        "name": str(lowest_margin_item),
                        "profit_margin": round(float(grouped.loc[lowest_margin_item, "Profit_Margin"]), 2),
                        "sales": round(float(grouped.loc[lowest_margin_item, sales_col]), 2)
                    },
                    "above_avg_sales_below_avg_margin_count": int(len(niche))
                }
                return {"success": True, "data": res_dict, "chart": None}

        # ----------------------------------------------------
        # ROUTE 6: Difference Between Groups / Comparison
        # (e.g. "Compare sales between North and South")
        # ----------------------------------------------------
        if op in ["difference_between_groups", "comparison"]:
            g_col = plan.get("group_by", [None])[0] or "Region"
            if g_col not in working_df.columns:
                g_col = find_best_column_match(g_col, list(working_df.columns))
                
            groups = plan.get("compare_groups") or []
            if not groups and plan.get("filters"):
                groups = [f.get("value") for f in plan.get("filters") if f.get("value")]
                
            if g_col and g_col in working_df.columns and metric and metric in working_df.columns:
                series_grp = working_df.groupby(g_col)[metric].sum().sort_values(ascending=False)
                if len(groups) >= 2:
                    g1_match = find_best_column_match(str(groups[0]), [str(k) for k in series_grp.index])
                    g2_match = find_best_column_match(str(groups[1]), [str(k) for k in series_grp.index])
                    g1, g2 = g1_match or groups[0], g2_match or groups[1]
                else:
                    g1, g2 = str(series_grp.index[0]), str(series_grp.index[1])
                    
                v1 = float(series_grp.get(g1, 0.0))
                v2 = float(series_grp.get(g2, 0.0))
                diff = round(v1 - v2, 2)
                pct_diff = round(((v1 - v2) / v2 * 100.0), 2) if v2 != 0 else 0.0
                
                res_dict = {
                    f"{g1}_{metric}": round(v1, 2),
                    f"{g2}_{metric}": round(v2, 2),
                    "absolute_difference": diff,
                    "percentage_difference": pct_diff
                }
                chart_payload = self._build_chart("bar", {g1: v1, g2: v2}, f"Comparison of {metric}", g_col)
                return {"success": True, "data": res_dict, "chart": chart_payload}

        # ----------------------------------------------------
        # ROUTE 7: Actual vs Target Comparison
        # ----------------------------------------------------
        if op == "actual_vs_target":
            actual_col = metric
            target_col = plan.get("comparison_column") or (profile.get("target_cols", [None])[0])
            if not target_col:
                target_col = find_best_column_match(f"target_{actual_col}", list(working_df.columns))
                
            if actual_col in working_df.columns and target_col and target_col in working_df.columns:
                act_sum = float(working_df[actual_col].sum())
                tgt_sum = float(working_df[target_col].sum())
                variance = round(act_sum - tgt_sum, 2)
                attainment = round((act_sum / tgt_sum * 100.0), 2) if tgt_sum != 0 else 0.0
                
                res_dict = {
                    f"actual_{actual_col}": round(act_sum, 2),
                    f"target_{actual_col}": round(tgt_sum, 2),
                    "variance": variance,
                    "attainment_percentage": attainment
                }
                return {"success": True, "data": res_dict, "chart": None}

        # ----------------------------------------------------
        # ROUTE 8: Business Rates (Return, Cancellation, Delivery Rate)
        # ----------------------------------------------------
        if op in ["return_rate", "cancellation_rate", "delivery_rate"]:
            total_orders = len(working_df)
            status_col = find_best_column_match("order_status", list(working_df.columns))
            
            if op == "return_rate":
                ret_col = find_best_column_match("is_returned", list(working_df.columns))
                if ret_col:
                    ret_cnt = int(working_df[ret_col].isin([True, 1, "True", "Yes"]).sum())
                elif status_col:
                    ret_cnt = int((working_df[status_col].astype(str).str.lower() == "returned").sum())
                else:
                    return {"success": False, "is_user_guidance": True, "error": "This dataset does not contain order return information (e.g. Is_Returned or Order_Status).", "data": None, "chart": None}
                rate = round((ret_cnt / total_orders * 100.0), 2)
                return {"success": True, "data": {"returned_orders": ret_cnt, "total_orders": total_orders, "return_rate_percentage": rate}, "chart": None}

            if op == "cancellation_rate":
                if status_col:
                    cancel_cnt = int((working_df[status_col].astype(str).str.lower() == "cancelled").sum())
                    rate = round((cancel_cnt / total_orders * 100.0), 2)
                    return {"success": True, "data": {"cancelled_orders": cancel_cnt, "total_orders": total_orders, "cancellation_rate_percentage": rate}, "chart": None}
                return {"success": False, "is_user_guidance": True, "error": "This dataset does not contain an Order_Status column to calculate cancellation rate.", "data": None, "chart": None}

            if op == "delivery_rate":
                if status_col:
                    deliv_cnt = int((working_df[status_col].astype(str).str.lower() == "delivered").sum())
                    rate = round((deliv_cnt / total_orders * 100.0), 2)
                    return {"success": True, "data": {"delivered_orders": deliv_cnt, "total_orders": total_orders, "delivery_rate_percentage": rate}, "chart": None}
                return {"success": False, "is_user_guidance": True, "error": "This dataset does not contain an Order_Status column to calculate delivery rate.", "data": None, "chart": None}

        # ----------------------------------------------------
        # ROUTE 9: Percentage Contribution
        # ----------------------------------------------------
        if op in ["percentage_contribution", "category_contribution", "regional_contribution"]:
            g_col = plan.get("group_by", [None])[0] or (profile.get("categorical_cols", [None])[0])
            if g_col and g_col in working_df.columns and metric and metric in working_df.columns:
                total_val = float(working_df[metric].sum())
                grouped = working_df.groupby(g_col)[metric].sum()
                contrib = (grouped / total_val * 100.0).round(2).sort_values(ascending=False)
                
                limit = plan.get("limit") or 10
                contrib = contrib.head(limit)
                
                data_dict = {str(k): float(v) for k, v in contrib.items()}
                chart_payload = self._build_chart("pie", data_dict, f"% Contribution of {metric}", g_col)
                return {
                    "success": True,
                    "data": {f"{k} (% of total {metric})": f"{v}%" for k, v in data_dict.items()},
                    "chart": chart_payload
                }

        # ----------------------------------------------------
        # ROUTE 10: Statistical & Distribution Analysis
        # ----------------------------------------------------
        if op == "distribution_analysis":
            if metric and metric in working_df.columns:
                series = working_df[metric].dropna()
                return {
                    "success": True,
                    "data": {
                        "metric": metric,
                        "mean": round(float(series.mean()), 2),
                        "median": round(float(series.median()), 2),
                        "std_dev": round(float(series.std()), 2),
                        "variance": round(float(series.var()), 2),
                        "min": round(float(series.min()), 2),
                        "25th_percentile": round(float(series.quantile(0.25)), 2),
                        "50th_percentile": round(float(series.quantile(0.50)), 2),
                        "75th_percentile": round(float(series.quantile(0.75)), 2),
                        "max": round(float(series.max()), 2),
                        "skewness": round(float(series.skew()), 2)
                    },
                    "chart": None
                }

        if op in ["correlation", "covariance"]:
            comp_col = plan.get("comparison_column")
            if not comp_col or comp_col not in working_df.columns:
                other_nums = [c for c in profile.get("numeric_cols", []) if c != metric and c in working_df.columns]
                if other_nums:
                    comp_col = other_nums[0]

            if metric and comp_col and metric in working_df.columns and comp_col in working_df.columns:
                if op == "correlation":
                    corr_val = float(working_df[metric].corr(working_df[comp_col]))
                    return {"success": True, "data": {f"correlation_{metric}_vs_{comp_col}": round(corr_val, 4)}, "chart": None}
                else:
                    cov_val = float(working_df[metric].cov(working_df[comp_col]))
                    return {"success": True, "data": {f"covariance_{metric}_and_{comp_col}": round(cov_val, 4)}, "chart": None}
            else:
                return {
                    "success": False,
                    "is_user_guidance": True,
                    "error": f"{op.capitalize()} requires at least two numeric columns. Available numeric columns: {', '.join(profile.get('numeric_cols', [])) or 'none'}.",
                    "data": None,
                    "chart": None
                }

        if op == "outlier_detection":
            if metric and metric in working_df.columns:
                series = working_df[metric].dropna()
                if len(series) > 0:
                    q1 = series.quantile(0.25)
                    q3 = series.quantile(0.75)
                    iqr = q3 - q1
                    lower_bound = q1 - 1.5 * iqr
                    upper_bound = q3 + 1.5 * iqr
                    outliers = working_df[(working_df[metric] < lower_bound) | (working_df[metric] > upper_bound)]
                    return {
                        "success": True,
                        "data": {
                            "metric": metric,
                            "outlier_count": int(len(outliers)),
                            "lower_bound": round(float(lower_bound), 2),
                            "upper_bound": round(float(upper_bound), 2),
                            "total_records": int(len(working_df))
                        },
                        "chart": None
                    }

        if op in ["std", "variance", "percentile", "quartile"]:
            if metric and metric in working_df.columns:
                series = working_df[metric].dropna()
                val = 0.0
                if op == "std": val = float(series.std())
                elif op == "variance": val = float(series.var())
                elif op in ["percentile", "quartile"]:
                    p = plan.get("percentile", 90)
                    if op == "quartile":
                        p = 75 if p == 90 else p
                    p_val = (p / 100.0) if p > 1 else p
                    val = float(series.quantile(p_val))
                return {"success": True, "data": {f"{op}_{metric}": round(val, 2)}, "chart": None}

        # ----------------------------------------------------
        # ROUTE 11: Time Series Analysis
        # ----------------------------------------------------
        time_ops = [
            "trend", "daily_trend", "weekly_trend", "monthly_trend", "quarterly_trend",
            "yearly_trend", "growth_rate", "month_over_month", "year_over_year",
            "moving_average", "cumulative_sum", "cumulative_total", "period_comparison", "current_vs_previous_period"
        ]
        if op in time_ops:
            date_col = plan.get("date_column") or (profile.get("date_cols", [None])[0])
            if not date_col or date_col not in working_df.columns:
                return {
                    "success": False,
                    "is_user_guidance": True,
                    "error": "This dataset does not contain any date or time columns to perform time series trend analysis.",
                    "data": None,
                    "chart": None
                }

            if not metric or metric not in working_df.columns:
                return {
                    "success": False,
                    "is_user_guidance": True,
                    "error": f"Time series trend requires a numeric metric column. Available numeric columns: {', '.join(profile.get('numeric_cols', []))}.",
                    "data": None,
                    "chart": None
                }

            working_df[date_col] = pd.to_datetime(working_df[date_col], errors='coerce')
            temp_df = working_df.dropna(subset=[date_col])
            
            # Auto-detect frequency
            date_grouping = plan.get("date_grouping")
            if not date_grouping:
                if op in ["yearly_trend", "year_over_year"]: date_grouping = "year"
                elif op in ["quarterly_trend"]: date_grouping = "quarter"
                elif op in ["daily_trend"]: date_grouping = "day"
                elif op in ["weekly_trend"]: date_grouping = "week"
                else: date_grouping = "month"

            freq_map = {"day": "D", "week": "W", "month": "ME", "quarter": "QE", "year": "YE"}
            fmt_map = {"day": "%Y-%m-%d", "week": "%Y-%U", "month": "%Y-%m", "quarter": "%Y-Q%q", "year": "%Y"}
            
            freq = freq_map.get(date_grouping, "ME")
            resampled = temp_df.set_index(date_col).resample(freq)[metric].sum().fillna(0)
            
            # Format index string
            if date_grouping == "year":
                resampled.index = resampled.index.strftime('%Y')
            elif date_grouping == "quarter":
                resampled.index = resampled.index.to_period('Q').astype(str)
            elif date_grouping == "day":
                resampled.index = resampled.index.strftime('%Y-%m-%d')
            else:
                resampled.index = resampled.index.strftime('%Y-%m')

            # Yearly / Period Comparison
            if op in ["period_comparison", "current_vs_previous_period"] or (op == "year_over_year" and date_grouping == "year"):
                pct_series = resampled.pct_change().fillna(0) * 100.0
                comp_data = {}
                for idx, val in resampled.items():
                    change = pct_series.get(idx, 0.0)
                    comp_data[str(idx)] = {
                        f"total_{metric}": round(float(val), 2),
                        "growth_rate_pct": round(float(change), 2)
                    }
                chart_payload = self._build_chart("bar", {str(k): float(v) for k, v in resampled.items()}, f"Yearly {metric}", "Year")
                return {"success": True, "data": comp_data, "chart": chart_payload}

            if op in ["growth_rate", "month_over_month", "year_over_year"]:
                growth_series = resampled.pct_change().fillna(0) * 100.0
                best_period = growth_series.idxmax()
                data_dict = {str(k): round(float(v), 2) for k, v in growth_series.items()}
                chart_payload = self._build_chart("line", data_dict, f"Growth Rate (%) of {metric}", date_col)
                return {
                    "success": True,
                    "data": {
                        "growth_rates_percentage": data_dict,
                        "highest_growth_period": str(best_period),
                        "highest_growth_value": round(float(growth_series.max()), 2)
                    },
                    "chart": chart_payload
                }
            elif op == "moving_average":
                w = plan.get("window", 3)
                resampled = resampled.rolling(window=w).mean().fillna(0)
            elif op in ["cumulative_sum", "cumulative_total"]:
                resampled = resampled.cumsum()

            data_dict = {str(k): round(float(v), 2) for k, v in resampled.items()}
            chart_payload = self._build_chart("line", data_dict, f"{op.replace('_', ' ').capitalize()} of {metric}", date_col)
            return {"success": True, "data": data_dict, "chart": chart_payload}

        # ----------------------------------------------------
        # ROUTE 12: Formulas & Business Metrics
        # ----------------------------------------------------
        if op in ["addition", "subtraction", "multiplication", "division", "percentage", "difference", "percentage_difference", "ratio"]:
            c1 = metric
            c2 = plan.get("comparison_column")
            if not c2 and len(profile.get("numeric_cols", [])) > 1:
                other_cols = [c for c in profile.get("numeric_cols", []) if c != c1]
                c2 = other_cols[0] if other_cols else None

            if c1 and c2 and c1 in working_df.columns and c2 in working_df.columns:
                v1 = float(working_df[c1].sum())
                v2 = float(working_df[c2].sum())
                res = 0.0
                if op == "addition": res = v1 + v2
                elif op in ["subtraction", "difference"]: res = v1 - v2
                elif op == "multiplication": res = v1 * v2
                elif op in ["division", "ratio"]: res = (v1 / v2) if v2 != 0 else 0.0
                elif op in ["percentage", "percentage_difference"]: res = ((v1 - v2) / v2 * 100.0) if v2 != 0 else 0.0

                return {"success": True, "data": {f"{op}_{c1}_and_{c2}": round(res, 2)}, "chart": None}

        # Business metric shortcut: profit_margin
        if op == "profit_margin":
            profit_col = find_best_column_match("profit", list(working_df.columns))
            sales_col = find_best_column_match("sales", list(working_df.columns))
            if profit_col and sales_col:
                s_sum = float(working_df[sales_col].sum())
                pm = (float(working_df[profit_col].sum()) / s_sum) * 100.0 if s_sum != 0 else 0.0
                return {
                    "success": True,
                    "data": {
                        "total_profit": round(float(working_df[profit_col].sum()), 2),
                        "total_sales": round(s_sum, 2),
                        "profit_margin_percentage": round(pm, 2)
                    },
                    "chart": None
                }

        # Business metric shortcut: average_order_value
        if op == "average_order_value":
            sales_col = find_best_column_match("sales", list(working_df.columns))
            order_col = find_best_column_match("order_id", list(working_df.columns))
            if sales_col:
                tot_sales = float(working_df[sales_col].sum())
                num_orders = float(working_df[order_col].nunique()) if order_col else float(len(working_df))
                aov = round(tot_sales / num_orders, 2) if num_orders > 0 else 0.0
                return {"success": True, "data": {"average_order_value": aov, "total_sales": round(tot_sales, 2), "total_orders": int(num_orders)}, "chart": None}

        # ----------------------------------------------------
        # ROUTE 13: Multi-Column Grouping / Top-N / Ranking / Partitioned Top-N
        # ----------------------------------------------------
        group_cols = plan.get("group_by") or []
        if isinstance(group_cols, str):
            group_cols = [group_cols]

        if group_cols or op in ["group_by", "top_n", "bottom_n", "ranking", "partitioned_top_n"]:
            g_cols = [c for c in group_cols if c in working_df.columns]
            if not g_cols and profile.get("categorical_cols"):
                g_cols = [profile.get("categorical_cols")[0]]

            if g_cols and metric and metric in working_df.columns:
                sub_op = "mean" if (op in ["mean"] or plan.get("aggregation") in ["mean", "average"] or "mean" in str(plan.get("sub_operation", "")) or "average" in str(plan.get("sub_operation", ""))) else "sum"
                ascending = (plan.get("sort") == "ascending") or (op == "bottom_n")
                limit = plan.get("limit") or 10

                # Partitioned / Nested Grouping (e.g. "top 3 products inside each region")
                if len(g_cols) >= 2 and (op in ["top_n", "ranking", "bottom_n", "partitioned_top_n"] or plan.get("per_group")):
                    grouped_df = working_df.groupby(g_cols)[metric].agg(sub_op).reset_index()
                    n_per_group = plan.get("limit") or 3
                    grouped_df = grouped_df.sort_values([g_cols[0], metric], ascending=[True, ascending])
                    partitioned = grouped_df.groupby(g_cols[0]).head(n_per_group)

                    data_dict = {}
                    for _, row in partitioned.iterrows():
                        key_str = f"{row[g_cols[0]]} → {row[g_cols[1]]}"
                        data_dict[key_str] = round(float(row[metric]), 2)

                    chart_payload = self._build_chart("bar", data_dict, f"{sub_op.capitalize()} of {metric}", f"{g_cols[0]} by {g_cols[1]}")
                    return {"success": True, "data": data_dict, "chart": chart_payload}

                grouped = working_df.groupby(g_cols)[metric].agg(sub_op)
                grouped = grouped.round(2).sort_values(ascending=ascending)
                grouped = grouped.head(limit)

                # Format result dict
                data_dict = {}
                for idx, val in grouped.items():
                    key_str = " - ".join(map(str, idx)) if isinstance(idx, tuple) else str(idx)
                    data_dict[key_str] = float(val)

                chart_type = "pie" if len(data_dict) <= 4 else "bar"
                chart_payload = self._build_chart(chart_type, data_dict, f"{sub_op.capitalize()} of {metric}", g_cols[0])
                return {"success": True, "data": data_dict, "chart": chart_payload}

        # ----------------------------------------------------
        # ROUTE 14: Single Metric Aggregations
        # ----------------------------------------------------
        if op == "count":
            if metric and metric in working_df.columns:
                val = int(working_df[metric].count())
            else:
                val = int(len(working_df))
            return {"success": True, "data": {f"count_{metric or 'records'}": val}, "chart": None}

        if op == "nunique":
            target = metric or (working_df.columns[0] if len(working_df.columns) > 0 else None)
            val = int(working_df[target].nunique()) if target else 0
            return {"success": True, "data": {f"unique_{target}": val}, "chart": None}

        if metric and metric in working_df.columns:
            series = working_df[metric]
            val = 0.0
            if op == "sum": val = float(series.sum())
            elif op == "mean": val = float(series.mean())
            elif op == "median": val = float(series.median())
            elif op == "min": val = float(series.min()) if pd.api.types.is_numeric_dtype(series) else str(series.min())
            elif op == "max": val = float(series.max()) if pd.api.types.is_numeric_dtype(series) else str(series.max())

            return {"success": True, "data": {f"{op}_{metric}": round(val, 2) if isinstance(val, float) else val}, "chart": None}

        # Fallback
        return {
            "success": False,
            "is_user_guidance": True,
            "error": f"Could not perform operation '{op}'. Available numeric columns: {', '.join(profile.get('numeric_cols', [])) or 'none'}.",
            "data": None,
            "chart": None
        }

    def _build_chart(self, chart_type: str, data_dict: dict, label: str, group_label: str) -> dict:
        labels = list(data_dict.keys())
        values = list(data_dict.values())
        return {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": f"{label} by {group_label}",
                    "data": values,
                    "backgroundColor": ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4"]
                }]
            },
            "options": {"responsive": True, "plugins": {"legend": {"display": chart_type == "pie"}}}
        }