import os
import sys

# Ensure chatbot root is in Python module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import pytest
except ImportError:
    class _MockPytest:
        @staticmethod
        def fixture(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
    pytest = _MockPytest()

import pandas as pd
import numpy as np

# Ensure UTF-8 output encoding for console execution
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from services.data_loader import process_csv
from services.query_processor import handle_question, reset_session
from services.pandas_executor import PandasExecutor

DATASET_PATH = os.path.join(os.path.dirname(__file__), "..", "uploads", "comprehensive_analytics_dataset.csv")

@pytest.fixture(scope="module")
def loaded_dataset():
    """Loads and profiles the comprehensive analytics dataset once for all tests."""
    df, summary = process_csv(DATASET_PATH)
    profile = summary["profile"]
    return df, profile

# ==============================================================================
# 1. BASIC QUESTIONS (10 Tests)
# ==============================================================================

def test_01_basic_sum(loaded_dataset):
    """Q1: What is the total sales?"""
    df, profile = loaded_dataset
    q = "What is the total sales?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Sales"].sum()
    assert resp["answer"], "Answer must not be empty"
    # Format check: e.g. 1,058,993 or 1058993
    assert f"{expected:,.0f}"[:6] in resp["answer"].replace(",", "") or f"{int(expected)}"[:6] in resp["answer"].replace(",", "")

def test_02_basic_mean(loaded_dataset):
    """Q2: What is the average unit price?"""
    df, profile = loaded_dataset
    q = "What is the average unit price?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Unit_Price"].mean()
    assert resp["answer"]
    assert f"{expected:.1f}" in resp["answer"] or f"{int(expected)}" in resp["answer"]

def test_03_basic_min(loaded_dataset):
    """Q3: What is the minimum discount percentage?"""
    df, profile = loaded_dataset
    q = "What is the minimum discount percentage?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Discount_Percent"].min()
    assert resp["answer"]
    assert str(int(expected)) in resp["answer"]

def test_04_basic_max(loaded_dataset):
    """Q4: What is the maximum quantity ordered?"""
    df, profile = loaded_dataset
    q = "What is the maximum quantity ordered?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Quantity"].max()
    assert resp["answer"]
    assert str(int(expected)) in resp["answer"]

def test_05_basic_count(loaded_dataset):
    """Q5: How many total orders are there?"""
    df, profile = loaded_dataset
    q = "How many total orders are there?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = len(df)
    assert resp["answer"]
    assert f"{expected:,}" in resp["answer"] or str(expected) in resp["answer"]

def test_06_basic_nunique(loaded_dataset):
    """Q6: How many unique customers are there?"""
    df, profile = loaded_dataset
    q = "How many unique customers are there?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Customer_ID"].nunique()
    assert resp["answer"]
    assert str(expected) in resp["answer"]

def test_07_basic_median(loaded_dataset):
    """Q7: What is the median salary?"""
    df, profile = loaded_dataset
    q = "What is the median salary?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Salary"].median()
    assert resp["answer"]
    assert f"{expected:,.0f}"[:5] in resp["answer"].replace(",", "") or f"{int(expected)}"[:5] in resp["answer"].replace(",", "")

def test_08_basic_std(loaded_dataset):
    """Q8: What is the standard deviation of sales?"""
    df, profile = loaded_dataset
    q = "What is the standard deviation of sales?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Sales"].std()
    assert resp["answer"]
    assert f"{int(expected)}"[:3] in resp["answer"].replace(",", "")

def test_09_basic_distinct_values(loaded_dataset):
    """Q9: What are the distinct categories?"""
    df, profile = loaded_dataset
    q = "What are the distinct categories?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    cats = df["Category"].unique()
    assert resp["answer"]
    # Check that at least two categories are mentioned
    found = sum(1 for c in cats if str(c).lower() in resp["answer"].lower())
    assert found >= 2

def test_10_basic_variance(loaded_dataset):
    """Q10: What is the variance of marketing spend?"""
    df, profile = loaded_dataset
    q = "What is the variance of marketing spend?"
    resp = handle_question(q, df, profile, session_id="suite_basic")
    expected = df["Marketing_Spend"].var()
    assert resp["answer"]
    assert f"{int(expected)}"[:3] in resp["answer"].replace(",", "")

# ==============================================================================
# 2. INTERMEDIATE QUESTIONS (10 Tests)
# ==============================================================================

def test_11_intermediate_single_filter(loaded_dataset):
    """Q11: What is the total sales in North region?"""
    df, profile = loaded_dataset
    q = "What is the total sales in North region?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    expected = df[df["Region"] == "North"]["Sales"].sum()
    assert resp["answer"]
    assert f"{int(expected)}"[:5] in resp["answer"].replace(",", "")

def test_12_intermediate_group_by(loaded_dataset):
    """Q12: What is the total profit by Category?"""
    df, profile = loaded_dataset
    q = "What is the total profit by Category?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    assert resp["answer"]
    top_cat = df.groupby("Category")["Profit"].sum().idxmax()
    assert top_cat.lower() in resp["answer"].lower()

def test_13_intermediate_top_n(loaded_dataset):
    """Q13: Show the top 5 products by sales"""
    df, profile = loaded_dataset
    q = "Show the top 5 products by sales"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    assert resp["answer"]
    top_product = df.groupby("Product")["Sales"].sum().idxmax()
    assert top_product.lower() in resp["answer"].lower()

def test_14_intermediate_bottom_n(loaded_dataset):
    """Q14: Show the bottom 3 departments by salary"""
    df, profile = loaded_dataset
    q = "Show the bottom 3 departments by salary"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    assert resp["answer"]
    bottom_dept = df.groupby("Department")["Salary"].mean().idxmin()
    assert bottom_dept.lower() in resp["answer"].lower()

def test_15_intermediate_profit_margin(loaded_dataset):
    """Q15: What is the overall profit margin?"""
    df, profile = loaded_dataset
    q = "What is the overall profit margin?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    expected = (df["Profit"].sum() / df["Sales"].sum()) * 100.0
    assert resp["answer"]
    assert f"{expected:.1f}" in resp["answer"] or f"{int(expected)}" in resp["answer"]

def test_16_intermediate_ratio(loaded_dataset):
    """Q16: What is the ratio of sales to marketing spend?"""
    df, profile = loaded_dataset
    q = "What is the ratio of sales to marketing spend?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    expected = df["Sales"].sum() / df["Marketing_Spend"].sum()
    assert resp["answer"]
    assert f"{expected:.1f}" in resp["answer"] or f"{int(expected)}" in resp["answer"]

def test_17_intermediate_subtraction(loaded_dataset):
    """Q17: What is the difference between total sales and total cost?"""
    df, profile = loaded_dataset
    q = "What is the difference between total sales and total cost?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    expected = df["Sales"].sum() - df["Total_Cost"].sum()
    assert resp["answer"]
    assert f"{int(expected)}"[:4] in resp["answer"].replace(",", "")

def test_18_intermediate_aov(loaded_dataset):
    """Q18: What is the average order value?"""
    df, profile = loaded_dataset
    q = "What is the average order value?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    order_col = "Order_ID" if "Order_ID" in df.columns else None
    expected = df["Sales"].sum() / (df[order_col].nunique() if order_col else len(df))
    assert resp["answer"]
    assert f"{int(expected)}"[:3] in resp["answer"].replace(",", "")

def test_19_intermediate_percentage_difference(loaded_dataset):
    """Q19: What is the percentage difference between sales and cost?"""
    df, profile = loaded_dataset
    q = "What is the percentage difference between sales and cost?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    expected = ((df["Sales"].sum() - df["Total_Cost"].sum()) / df["Total_Cost"].sum()) * 100.0
    assert resp["answer"]
    assert f"{int(expected)}"[:2] in resp["answer"]

def test_20_intermediate_date_filter(loaded_dataset):
    """Q20: What is the total sales for orders after 2024-01-01?"""
    df, profile = loaded_dataset
    q = "What is the total sales for orders after 2024-01-01?"
    resp = handle_question(q, df, profile, session_id="suite_inter")
    expected = df[pd.to_datetime(df["Order_Date"]) > "2024-01-01"]["Sales"].sum()
    assert resp["answer"]
    assert f"{int(expected)}"[:4] in resp["answer"].replace(",", "")

# ==============================================================================
# 3. ADVANCED QUESTIONS (10 Tests)
# ==============================================================================

def test_21_advanced_correlation(loaded_dataset):
    """Q21: What is the correlation between marketing spend and sales?"""
    df, profile = loaded_dataset
    q = "What is the correlation between marketing spend and sales?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    expected = df["Marketing_Spend"].corr(df["Sales"])
    assert resp["answer"]
    assert f"{expected:.2f}" in resp["answer"] or f"{expected:.1f}" in resp["answer"]

def test_22_advanced_covariance(loaded_dataset):
    """Q22: What is the covariance between sales and profit?"""
    df, profile = loaded_dataset
    q = "What is the covariance between sales and profit?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    expected = df["Sales"].cov(df["Profit"])
    assert resp["answer"]
    assert f"{int(expected)}"[:4] in resp["answer"].replace(",", "")

def test_23_advanced_outliers(loaded_dataset):
    """Q23: Are there any outliers in sales?"""
    df, profile = loaded_dataset
    q = "Are there any outliers in sales?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    assert resp["answer"]
    assert "outlier" in resp["answer"].lower() or "bound" in resp["answer"].lower() or "none" in resp["answer"].lower()

def test_24_advanced_distribution(loaded_dataset):
    """Q24: Show the distribution summary of sales"""
    df, profile = loaded_dataset
    q = "Show the distribution summary of sales"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    assert resp["answer"]
    assert "mean" in resp["answer"].lower() or "median" in resp["answer"].lower()

def test_25_advanced_actual_vs_target(loaded_dataset):
    """Q25: Compare actual sales versus target sales"""
    df, profile = loaded_dataset
    q = "Compare actual sales versus target sales"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    assert resp["answer"]
    assert "actual" in resp["answer"].lower() or "target" in resp["answer"].lower() or "variance" in resp["answer"].lower()

def test_26_advanced_return_rate(loaded_dataset):
    """Q26: What is the return rate of orders?"""
    df, profile = loaded_dataset
    q = "What is the return rate of orders?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    expected = (df["Is_Returned"].sum() / len(df)) * 100.0
    assert resp["answer"]
    assert f"{expected:.1f}" in resp["answer"] or f"{int(expected)}" in resp["answer"]

def test_27_advanced_cancellation_rate(loaded_dataset):
    """Q27: What is the cancellation rate?"""
    df, profile = loaded_dataset
    q = "What is the cancellation rate?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    expected = ((df["Order_Status"].astype(str).str.lower() == "cancelled").sum() / len(df)) * 100.0
    assert resp["answer"]
    assert f"{expected:.1f}" in resp["answer"] or f"{int(expected)}" in resp["answer"]

def test_28_advanced_delivery_rate(loaded_dataset):
    """Q28: What is the delivery rate?"""
    df, profile = loaded_dataset
    q = "What is the delivery rate?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    expected = ((df["Order_Status"].astype(str).str.lower() == "delivered").sum() / len(df)) * 100.0
    assert resp["answer"]
    assert f"{expected:.1f}" in resp["answer"] or f"{int(expected)}" in resp["answer"]

def test_29_advanced_partitioned_top_n(loaded_dataset):
    """Q29: Show the top 3 products inside each region"""
    df, profile = loaded_dataset
    q = "Show the top 3 products inside each region"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    assert resp["answer"]
    assert any(reg in resp["answer"] for reg in ["North", "Central", "East", "West", "South"])

def test_30_advanced_percentile(loaded_dataset):
    """Q30: What is the 90th percentile of sales?"""
    df, profile = loaded_dataset
    q = "What is the 90th percentile of sales?"
    resp = handle_question(q, df, profile, session_id="suite_adv")
    expected = df["Sales"].quantile(0.90)
    assert resp["answer"]
    assert f"{int(expected)}"[:3] in resp["answer"].replace(",", "")

# ==============================================================================
# 4. MULTI-STEP QUESTIONS (10 Tests)
# ==============================================================================

def test_31_multistep_filtered_aggregation(loaded_dataset):
    """Q31: What is the total sales of Electronics in the North region?"""
    df, profile = loaded_dataset
    q = "What is the total sales of Electronics in the North region?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    filtered = df[(df["Category"] == "Electronics") & (df["Region"] == "North")]["Sales"].sum()
    assert resp["answer"]
    assert f"{int(filtered)}"[:4] in resp["answer"].replace(",", "")

def test_32_multistep_top_n_contribution(loaded_dataset):
    """Q32: What percentage of total sales comes from the top 3 products?"""
    df, profile = loaded_dataset
    q = "What percentage of total sales comes from the top 3 products?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    top3_sum = df.groupby("Product")["Sales"].sum().nlargest(3).sum()
    pct = (top3_sum / df["Sales"].sum()) * 100.0
    assert resp["answer"]
    assert f"{pct:.1f}" in resp["answer"] or f"{int(pct)}" in resp["answer"]

def test_33_multistep_highest_profit_region_margin(loaded_dataset):
    """Q33: Which region has the highest profit and what is its profit margin?"""
    df, profile = loaded_dataset
    q = "Which region has the highest profit and what is its profit margin?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    top_region = df.groupby("Region")["Profit"].sum().idxmax()
    assert resp["answer"]
    assert top_region.lower() in resp["answer"].lower()

def test_34_multistep_extreme_combination(loaded_dataset):
    """Q34: Which product has the highest sales but lowest profit margin?"""
    df, profile = loaded_dataset
    q = "Which product has the highest sales but lowest profit margin?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    assert resp["answer"]
    best_sales_item = df.groupby("Product")["Sales"].sum().idxmax()
    assert best_sales_item.lower() in resp["answer"].lower()

def test_35_multistep_difference_between_groups(loaded_dataset):
    """Q35: Compare sales between North and South and show the percentage difference"""
    df, profile = loaded_dataset
    q = "Compare sales between North and South and show the percentage difference"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    assert resp["answer"]
    assert "north" in resp["answer"].lower()
    assert "south" in resp["answer"].lower()

def test_36_multistep_filtered_subgroup_highest(loaded_dataset):
    """Q36: Which department has the highest average salary for employees with experience greater than 5 years?"""
    df, profile = loaded_dataset
    q = "Which department has the highest average salary for employees with experience greater than 5 years?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    assert resp["answer"]
    expected_dept = df[df["Experience_Years"] > 5].groupby("Department")["Salary"].mean().idxmax()
    assert expected_dept.lower() in resp["answer"].lower()

def test_37_multistep_above_average_filter(loaded_dataset):
    """Q37: Which customers purchased more than the average customer spending?"""
    df, profile = loaded_dataset
    q = "Which customers purchased more than the average customer spending?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    assert resp["answer"]
    assert "customer" in resp["answer"].lower() or "qualifying" in resp["answer"].lower() or "average" in resp["answer"].lower()

def test_38_multistep_cross_metric_niche(loaded_dataset):
    """Q38: Which products have above average sales and below average profit margin?"""
    df, profile = loaded_dataset
    q = "Which products have above average sales and below average profit margin?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    assert resp["answer"]
    assert "product" in resp["answer"].lower() or "sales" in resp["answer"].lower()

def test_39_multistep_category_contribution(loaded_dataset):
    """Q39: Which category contributes the most to total profit?"""
    df, profile = loaded_dataset
    q = "Which category contributes the most to total profit?"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    top_cat = df.groupby("Category")["Profit"].sum().idxmax()
    assert resp["answer"]
    assert top_cat.lower() in resp["answer"].lower()

def test_40_multistep_top_regions_revenue_contribution(loaded_dataset):
    """Q40: Show top 5 regions by revenue and their percentage contribution"""
    df, profile = loaded_dataset
    q = "Show top 5 regions by revenue and their percentage contribution"
    resp = handle_question(q, df, profile, session_id="suite_multi")
    assert resp["answer"]
    assert any(reg.lower() in resp["answer"].lower() for reg in ["north", "south", "east", "west", "central"])

# ==============================================================================
# 5. TIME, STATISTICAL & CONTEXTUAL QUESTIONS (10 Tests)
# ==============================================================================

def test_41_time_monthly_trend(loaded_dataset):
    """Q41: Show the monthly sales trend"""
    df, profile = loaded_dataset
    q = "Show the monthly sales trend"
    resp = handle_question(q, df, profile, session_id="suite_time")
    assert resp["answer"]
    assert "2024" in resp["answer"] or "2025" in resp["answer"] or "sales" in resp["answer"].lower()

def test_42_time_yearly_trend(loaded_dataset):
    """Q42: Show the yearly sales trend"""
    df, profile = loaded_dataset
    q = "Show the yearly sales trend"
    resp = handle_question(q, df, profile, session_id="suite_time")
    assert resp["answer"]
    assert "2024" in resp["answer"] or "2025" in resp["answer"]

def test_43_time_yoy_growth(loaded_dataset):
    """Q43: What is the year over year sales growth?"""
    df, profile = loaded_dataset
    q = "What is the year over year sales growth?"
    resp = handle_question(q, df, profile, session_id="suite_time")
    assert resp["answer"]
    assert "growth" in resp["answer"].lower() or "%" in resp["answer"] or "year" in resp["answer"].lower()

def test_44_time_mom_highest_growth(loaded_dataset):
    """Q44: Which month had the highest sales growth?"""
    df, profile = loaded_dataset
    q = "Which month had the highest sales growth?"
    resp = handle_question(q, df, profile, session_id="suite_time")
    assert resp["answer"]
    assert "growth" in resp["answer"].lower() or "2024" in resp["answer"] or "2025" in resp["answer"]

def test_45_time_moving_average(loaded_dataset):
    """Q45: Show the 3-month moving average of sales"""
    df, profile = loaded_dataset
    q = "Show the 3-month moving average of sales"
    resp = handle_question(q, df, profile, session_id="suite_time")
    assert resp["answer"]
    assert "average" in resp["answer"].lower() or "sales" in resp["answer"].lower()

def test_46_time_cumulative_sales(loaded_dataset):
    """Q46: What is the cumulative total of sales over time?"""
    df, profile = loaded_dataset
    q = "What is the cumulative total of sales over time?"
    resp = handle_question(q, df, profile, session_id="suite_time")
    assert resp["answer"]
    assert "cumulative" in resp["answer"].lower() or "total" in resp["answer"].lower() or "sales" in resp["answer"].lower()

def test_47_48_contextual_turns(loaded_dataset):
    """Q47 & Q48: Contextual Multi-Turn Conversation"""
    df, profile = loaded_dataset
    session_id = "suite_context_test"
    reset_session(session_id)

    # Turn 1: Which region has the highest sales?
    q1 = "Which region has the highest sales?"
    r1 = handle_question(q1, df, profile, session_id=session_id)
    top_region = df.groupby("Region")["Sales"].sum().idxmax()
    assert r1["answer"]
    assert top_region.lower() in r1["answer"].lower()

    # Turn 2: What about its profit? (Follow-up resolving 'its' to the top region)
    q2 = "What about its profit?"
    r2 = handle_question(q2, df, profile, session_id=session_id)
    expected_profit = df[df["Region"] == top_region]["Profit"].sum()
    assert r2["answer"]
    assert f"{int(expected_profit)}"[:4] in r2["answer"].replace(",", "") or top_region.lower() in r2["answer"].lower()

def test_49_missing_column_graceful_guidance(loaded_dataset):
    """Q49: Missing Column / Impossible Query: What is the average customer churn rate?"""
    df, profile = loaded_dataset
    q = "What is the average customer churn rate?"
    resp = handle_question(q, df, profile, session_id="suite_guidance")
    assert resp["answer"]
    assert "churn" in resp["answer"].lower()
    assert "available" in resp["answer"].lower() or "couldn't find" in resp["answer"].lower()

def test_50_typo_tolerance(loaded_dataset):
    """Q50: Typo Tolerance: What is the total slaes by regoin?"""
    df, profile = loaded_dataset
    q = "What is the total slaes by regoin?"
    resp = handle_question(q, df, profile, session_id="suite_typo")
    assert resp["answer"]
    assert any(reg.lower() in resp["answer"].lower() for reg in ["north", "south", "east", "west", "central"])

# ==============================================================================
# STANDALONE CLI TEST RUNNER
# ==============================================================================

if __name__ == "__main__":
    if "--live" not in sys.argv:
        os.environ["FAST_TEST"] = "1"

    print("=" * 70)
    print("RUNNING COMPREHENSIVE 50-QUESTION VALIDATION SUITE")
    print("=" * 70)

    df_main, summary_main = process_csv(DATASET_PATH)
    profile_main = summary_main["profile"]

    all_tests = [
        # Basic
        ("Q01: Total sales (Sum)", test_01_basic_sum),
        ("Q02: Average unit price (Mean)", test_02_basic_mean),
        ("Q03: Minimum discount percentage (Min)", test_03_basic_min),
        ("Q04: Maximum quantity ordered (Max)", test_04_basic_max),
        ("Q05: Total order count (Count)", test_05_basic_count),
        ("Q06: Unique customers (Nunique)", test_06_basic_nunique),
        ("Q07: Median salary (Median)", test_07_basic_median),
        ("Q08: Standard deviation of sales (Std)", test_08_basic_std),
        ("Q09: Distinct categories (Distinct)", test_09_basic_distinct_values),
        ("Q10: Variance of marketing spend (Variance)", test_10_basic_variance),
        # Intermediate
        ("Q11: Total sales in North (Filter)", test_11_intermediate_single_filter),
        ("Q12: Profit by Category (GroupBy)", test_12_intermediate_group_by),
        ("Q13: Top 5 products by sales (Top N)", test_13_intermediate_top_n),
        ("Q14: Bottom 3 departments by salary (Bottom N)", test_14_intermediate_bottom_n),
        ("Q15: Overall profit margin (KPI)", test_15_intermediate_profit_margin),
        ("Q16: Ratio of sales to marketing (Ratio)", test_16_intermediate_ratio),
        ("Q17: Sales minus Cost (Difference)", test_17_intermediate_subtraction),
        ("Q18: Average order value (AOV)", test_18_intermediate_aov),
        ("Q19: Percentage markup (Pct Difference)", test_19_intermediate_percentage_difference),
        ("Q20: Sales after 2024-01-01 (Date Filter)", test_20_intermediate_date_filter),
        # Advanced
        ("Q21: Correlation marketing vs sales (Corr)", test_21_advanced_correlation),
        ("Q22: Covariance sales vs profit (Cov)", test_22_advanced_covariance),
        ("Q23: Sales outlier detection (Outliers)", test_23_advanced_outliers),
        ("Q24: Sales distribution summary (Distribution)", test_24_advanced_distribution),
        ("Q25: Actual vs target sales (Comparison)", test_25_advanced_actual_vs_target),
        ("Q26: Order return rate (Return Rate)", test_26_advanced_return_rate),
        ("Q27: Order cancellation rate (Cancel Rate)", test_27_advanced_cancellation_rate),
        ("Q28: Order delivery rate (Delivery Rate)", test_28_advanced_delivery_rate),
        ("Q29: Top 3 products inside each region (Partitioned)", test_29_advanced_partitioned_top_n),
        ("Q30: 90th percentile of sales (Quantile)", test_30_advanced_percentile),
        # Multi-Step
        ("Q31: Electronics sales in North (Multi-filter)", test_31_multistep_filtered_aggregation),
        ("Q32: Top 3 products % contribution (Top N Contrib)", test_32_multistep_top_n_contribution),
        ("Q33: Region highest profit & margin (Extreme 1)", test_33_multistep_highest_profit_region_margin),
        ("Q34: Highest sales lowest margin product (Extreme 2)", test_34_multistep_extreme_combination),
        ("Q35: North vs South sales difference (Group Diff)", test_35_multistep_difference_between_groups),
        ("Q36: Dept highest avg salary exp>5 (Filtered Subgroup)", test_36_multistep_filtered_subgroup_highest),
        ("Q37: Customers spending > average (Above Avg)", test_37_multistep_above_average_filter),
        ("Q38: Above avg sales below avg margin (Niche)", test_38_multistep_cross_metric_niche),
        ("Q39: Category contributing most to profit (Contribution)", test_39_multistep_category_contribution),
        ("Q40: Top 5 regions revenue & % contribution (Rank+Contrib)", test_40_multistep_top_regions_revenue_contribution),
        # Time / Statistical / Contextual
        ("Q41: Monthly sales trend (Trend)", test_41_time_monthly_trend),
        ("Q42: Yearly sales trend (Yearly)", test_42_time_yearly_trend),
        ("Q43: Year-over-year sales growth (YoY)", test_43_time_yoy_growth),
        ("Q44: Highest sales growth month (Growth)", test_44_time_mom_highest_growth),
        ("Q45: 3-month moving average (Moving Avg)", test_45_time_moving_average),
        ("Q46: Cumulative sales total (CumSum)", test_46_time_cumulative_sales),
        ("Q47-48: Contextual Multi-Turn (Pronoun 'its')", test_47_48_contextual_turns),
        ("Q49: Missing column guidance (Guidance)", test_49_missing_column_graceful_guidance),
        ("Q50: Typo tolerance 'slaes by regoin' (Typo)", test_50_typo_tolerance),
    ]

    passed = 0
    failed = 0
    fixture = (df_main, profile_main)

    for name, test_fn in all_tests:
        try:
            test_fn(fixture)
            print(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name} -> Error: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"TEST RESULTS: {passed} PASSED | {failed} FAILED | TOTAL: {len(all_tests)}")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
