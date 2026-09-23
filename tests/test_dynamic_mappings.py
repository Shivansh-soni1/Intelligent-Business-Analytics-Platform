import os
import io
import pandas as pd
import pytest

from services.data_loader import (
    process_csv,
    classify_columns,
    find_best_column_match,
    generate_universal_questions,
    SEMANTIC_DICTIONARY
)
from services.pandas_executor import PandasExecutor
from services.query_processor import handle_question

def test_missing_business_columns_profiling(tmp_path):
    """
    Test that an uploaded CSV with only Customer_ID, Order_Date, Product, Quantity, Sales
    profiles normally without throwing KeyError: 'profit', KeyError: 'salary', KeyError: 'categorical_cols'.
    """
    csv_content = """Customer_ID,Order_Date,Product,Quantity,Sales
C101,2026-01-10,Laptop,2,2400.0
C102,2026-01-11,Mouse,5,125.0
C103,2026-01-12,Keyboard,3,225.0
"""
    test_file = tmp_path / "test_sales.csv"
    test_file.write_text(csv_content)

    df, summary = process_csv(str(test_file))
    profile = summary["profile"]

    # 1. Verify schema detection
    assert "Sales" in profile.get("numeric_cols", [])
    assert "Quantity" in profile.get("numeric_cols", [])
    assert "Product" in profile.get("categorical_cols", [])
    assert "Order_Date" in profile.get("date_cols", [])
    assert "Customer_ID" in profile.get("identifier_cols", [])

    # 2. Verify identifier is NOT in numeric cols
    assert "Customer_ID" not in profile.get("numeric_cols", [])

    # 3. Verify missing business columns are NOT created or present
    assert "Profit" not in df.columns
    assert "Salary" not in df.columns
    assert "profit" not in df.columns
    assert "salary" not in df.columns

    # 4. Verify suggested questions ONLY contain columns that exist
    suggested = summary["suggested_questions"]
    assert len(suggested) > 0
    for q in suggested:
        q_lower = q.lower()
        assert "salary" not in q_lower, f"Suggested question contained salary: {q}"
        assert "profit" not in q_lower, f"Suggested question contained profit: {q}"

    # 5. Verify query for missing column 'profit' returns graceful guidance without crashing
    resp_profit = handle_question("What is the total profit?", df, profile)
    assert "profit" in resp_profit["answer"].lower()
    assert "available numeric columns" in resp_profit["answer"].lower()
    assert "Sales" in resp_profit["answer"]

    # 6. Verify query for missing column 'salary' returns graceful guidance without crashing
    resp_salary = handle_question("What is the average salary?", df, profile)
    assert "salary" in resp_salary["answer"].lower()
    assert "available numeric columns" in resp_salary["answer"].lower()

def test_dynamic_column_matching():
    """
    Test exact, normalized, synonym, substring, and fuzzy matching.
    """
    cols = ["Customer_ID", "Order_Date", "Product", "Quantity", "Sales"]

    # 1. Exact match
    assert find_best_column_match("Sales", cols) == "Sales"
    assert find_best_column_match("sales", cols) == "Sales"

    # 2. Normalized match
    assert find_best_column_match("customer id", cols) == "Customer_ID"
    assert find_best_column_match("customer_id", cols) == "Customer_ID"
    assert find_best_column_match("orderdate", cols) == "Order_Date"

    # 3. Synonym match (via knowledge base, only because matching column exists)
    assert find_best_column_match("revenue", cols) == "Sales"
    assert find_best_column_match("turnover", cols) == "Sales"
    assert find_best_column_match("units", cols) == "Quantity"
    assert find_best_column_match("items", cols) == "Quantity"

    # 4. Synonym match for missing concept returns empty (NEVER invents fake column)
    assert find_best_column_match("profit", cols) == ""
    assert find_best_column_match("salary", cols) == ""
    assert find_best_column_match("wage", cols) == ""

    # 5. Fuzzy match
    assert find_best_column_match("prodcut", cols) == "Product"
    assert find_best_column_match("qunatity", cols) == "Quantity"

def test_identifier_column_classification():
    """
    Test that identifier columns (CustomerID, Order_ID, EmployeeID, Student_ID, Transaction_ID)
    are classified as identifiers and never as numeric metrics.
    """
    df = pd.DataFrame({
        "Customer_ID": [1001, 1002, 1003],
        "OrderID": [501, 502, 503],
        "Employee_ID": [201, 202, 203],
        "Student_Id": [301, 302, 303],
        "TransactionID": [901, 902, 903],
        "Sales": [150.0, 200.0, 350.0]
    })
    classified = classify_columns(df)

    # Identifiers
    id_cols = classified.get("identifier_cols", [])
    assert "Customer_ID" in id_cols
    assert "OrderID" in id_cols
    assert "Employee_ID" in id_cols
    assert "Student_Id" in id_cols
    assert "TransactionID" in id_cols

    # Numerics must ONLY contain Sales
    num_cols = classified.get("numeric_cols", [])
    assert "Sales" in num_cols
    assert "Customer_ID" not in num_cols
    assert "OrderID" not in num_cols
    assert "Employee_ID" not in num_cols
    assert "Student_Id" not in num_cols
    assert "TransactionID" not in num_cols

def test_arbitrary_domain_dataset(tmp_path):
    """
    Test dataset from a non-business domain (IoT Sensor data).
    """
    csv_content = """Device_ID,Timestamp,Sensor_Type,Reading,Status
D1,2026-01-01 10:00:00,Temperature,24.5,Active
D2,2026-01-01 10:05:00,Temperature,25.1,Active
D3,2026-01-01 10:10:00,Humidity,60.2,Active
"""
    test_file = tmp_path / "sensor_data.csv"
    test_file.write_text(csv_content)

    df, summary = process_csv(str(test_file))
    profile = summary["profile"]

    assert "Reading" in profile.get("numeric_cols", [])
    assert "Sensor_Type" in profile.get("categorical_cols", [])
    assert "Device_ID" in profile.get("identifier_cols", [])

    # Suggested questions must only reference actual columns
    for q in summary["suggested_questions"]:
        assert "sales" not in q.lower()
        assert "profit" not in q.lower()
        assert "salary" not in q.lower()

def test_large_dataset_support(tmp_path):
    """
    Test with a 500+ column dataset.
    """
    data = {"Record_ID": list(range(10))}
    for i in range(1, 501):
        data[f"Col_{i}"] = [i * 1.5] * 10
    
    df_large = pd.DataFrame(data)
    classified = classify_columns(df_large)
    
    assert len(classified.get("numeric_cols", [])) == 500
    assert "Record_ID" in classified.get("identifier_cols", [])

def test_safe_dictionary_access():
    """
    Test that passing empty or partial profile dictionary never raises KeyError.
    """
    executor = PandasExecutor()
    df = pd.DataFrame({"Score": [10, 20, 30]})

    # Empty profile
    plan = {"operation": "sum", "metric_column": "Score"}
    res = executor.execute(plan, df, {})
    assert res["success"] is True
    assert res["data"] == {"sum_Score": 60.0}

    # Missing column plan
    plan_missing = {"operation": "missing_column", "missing_entity": "profit"}
    res_missing = executor.execute(plan_missing, df, {})
    assert res_missing["success"] is False
    assert "profit" in res_missing["error"]

def test_empty_dataset():
    """
    Test that an empty DataFrame is handled gracefully.
    """
    executor = PandasExecutor()
    df_empty = pd.DataFrame()
    plan = {"operation": "sum", "metric_column": "Sales"}
    res = executor.execute(plan, df_empty, {})
    assert res["success"] is True
    assert "empty" in res["data"].lower()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

