import os
import re
import difflib
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List, Optional

# Standard allowed file extensions
ALLOWED_EXTENSIONS = {'csv', 'txt'}

# Semantic / Synonym Knowledge Base
# IMPORTANT: This is ONLY a reference knowledge base, NOT a required schema.
# Datasets can have any subset of these or completely different columns.
SEMANTIC_DICTIONARY = {
    "sales": ["sales", "revenue", "turnover", "gross_sales", "net_sales", "amount", "sales_amount", "total_sales", "income", "earnings"],
    "profit": ["profit", "net_profit", "gross_profit", "earnings", "net_income", "margin", "gain", "operating_profit"],
    "profit_margin": ["profit_margin", "margin", "net_margin", "operating_margin", "gross_margin", "margin_percentage"],
    "salary": ["salary", "compensation", "wage", "wages", "pay", "stipend", "remuneration", "base_pay", "total_compensation"],
    "quantity": ["quantity", "qty", "volume", "units", "units_sold", "count", "items", "number_of_items"],
    "cost": ["cost", "expense", "expenses", "unit_cost", "total_cost", "shipping_cost", "cogs", "expenditure", "spend", "spending"],
    "price": ["price", "unit_price", "rate", "cost_per_unit", "mrp", "selling_price"],
    "discount": ["discount", "rebate", "deduction", "discount_amount", "discount_percent", "discount_rate"],
    "target": ["target", "target_sales", "target_profit", "goal", "budget", "quota", "forecast", "projected"],
    "delivery": ["delivery_days", "delivery_time", "lead_time", "shipping_time", "transit_time", "days_to_deliver"],
    "rating": ["rating", "score", "review_score", "satisfaction_score", "feedback_score"],
    "date": ["date", "order_date", "transaction_date", "created_at", "timestamp", "invoice_date", "day", "time"],
    "product": ["product", "item", "sku", "article", "merchandise", "good"],
    "category": ["category", "segment", "type", "class", "group", "genre", "family"],
    "region": ["region", "area", "zone", "territory", "location", "district", "sector"],
    "customer": ["customer", "client", "buyer", "shopper", "consumer", "patron", "user", "account"],
    "employee": ["employee", "staff", "worker", "personnel", "team_member"],
    "department": ["department", "dept", "division", "team", "unit", "branch"],
    "city": ["city", "town", "municipality", "metro"],
    "country": ["country", "nation", "state", "province"],
    "brand": ["brand", "manufacturer", "make", "vendor"],
    "channel": ["channel", "sales_channel", "distribution_channel", "platform"],
    "marketing": ["marketing_spend", "ad_spend", "advertising", "marketing_cost"],
    "stock": ["stock", "stock_level", "inventory", "inventory_level", "available_stock", "quantity_on_hand"],
    "experience": ["experience", "experience_years", "tenure", "years_of_experience"],
    "return": ["is_returned", "returned", "return_date", "returns", "return_rate"],
    "status": ["status", "state", "condition", "stage"]
}

# 8 Domain Reference Keywords (Optional guide for domain detection)
DOMAIN_SEMANTICS = {
    "Sales / Retail": {
        "keywords": ["sales", "revenue", "profit", "discount", "quantity", "unit_price", "store", "product", "region", "category", "transaction", "invoice"],
        "metrics": ["Sales", "Revenue", "Profit", "Quantity", "Unit_Price", "Discount"],
        "dimensions": ["Product", "Category", "Region", "Store", "Customer_Segment"]
    },
    "Employee / HR": {
        "keywords": ["salary", "employee", "department", "job_role", "attrition", "joining_date", "experience", "performance_rating", "compensation", "bonus", "incentive"],
        "metrics": ["Salary", "Bonus", "Total_Compensation", "Experience_Years", "Performance_Rating"],
        "dimensions": ["Department", "Job_Role", "Employment_Type", "Location", "Gender"]
    },
    "Customer / E-Commerce": {
        "keywords": ["customer", "order", "lifetime_value", "clv", "churn", "spending", "average_order_value", "payment_method", "delivery_status", "cart"],
        "metrics": ["Total_Spending", "Average_Order_Value", "Customer_Lifetime_Value", "Quantity"],
        "dimensions": ["Customer_Type", "Customer_Segment", "Payment_Method", "Order_Status", "City"]
    },
    "Finance": {
        "keywords": ["budget", "actual_spend", "expense", "income", "cost_center", "revenue", "loss", "financial_year", "account", "forecast"],
        "metrics": ["Revenue", "Income", "Expense", "Cost", "Profit", "Budget", "Actual_Spend"],
        "dimensions": ["Department", "Business_Unit", "Cost_Center", "Expense_Category", "Revenue_Source"]
    },
    "Marketing": {
        "keywords": ["campaign", "lead", "ctr", "cpc", "cpm", "impressions", "clicks", "conversions", "reach", "ad_spend", "roi"],
        "metrics": ["Spend", "Budget", "Impressions", "Clicks", "Conversions", "Leads", "Revenue", "CTR", "CPC"],
        "dimensions": ["Campaign_Name", "Campaign_Type", "Channel", "Platform", "Source"]
    },
    "Inventory / Supply Chain": {
        "keywords": ["stock", "warehouse", "sku", "supplier", "reorder_level", "safety_stock", "shipment", "delivery_time", "unit_cost", "inventory_value"],
        "metrics": ["Current_Stock", "Available_Stock", "Reorder_Level", "Unit_Cost", "Inventory_Value", "Shipping_Cost"],
        "dimensions": ["Product", "Category", "Warehouse", "Supplier", "Transport_Mode", "Carrier"]
    },
    "Healthcare": {
        "keywords": ["patient", "doctor", "hospital", "disease", "diagnosis", "treatment_cost", "admission", "discharge", "length_of_stay", "insurance"],
        "metrics": ["Age", "Treatment_Cost", "Medicine_Cost", "Insurance_Amount", "Total_Bill", "Length_of_Stay"],
        "dimensions": ["Gender", "Blood_Group", "Disease", "Diagnosis", "Hospital_Name", "Doctor_Name"]
    },
    "Student / Education": {
        "keywords": ["student", "marks", "score", "gpa", "cgpa", "attendance", "course", "subject", "grade", "semester", "roll_number"],
        "metrics": ["Marks", "Score", "Percentage", "GPA", "CGPA", "Attendance_Percentage"],
        "dimensions": ["Course", "Department", "Subject", "Class", "Section", "Grade"]
    }
}

# Regex to detect identifier columns (with or without underscores/case variations)
ID_PATTERN = re.compile(
    r'(?:^|[_\s]|(?<=[a-z]))(id|code|no|num|number|key|pk|uuid|hash|ticket|invoice|sku|policy|ssn|roll|guid)s?$',
    re.IGNORECASE
)

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_text(text: str) -> str:
    """Strips all whitespace, underscores, and special characters to lowercase."""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text).lower())

def is_identifier_column(col_name: str, series: pd.Series, total_rows: int) -> bool:
    """
    Detects if a column is an ID or primary key based on naming patterns and cardinality.
    Ensures columns like ID, Customer_ID, Employee_ID, Order_ID, Student_ID, Transaction_ID
    are not treated as business metrics.
    """
    clean_name = str(col_name).strip()
    norm_name = normalize_text(clean_name)
    
    # Direct check on exact / normalized names
    common_id_names = {
        'id', 'code', 'key', 'pk', 'uuid', 'guid', 'sku', 'ssn', 'hash', 'ticket',
        'customerid', 'orderid', 'employeeid', 'studentid', 'transactionid',
        'recordid', 'rowid', 'userid', 'accountid', 'productid', 'invoiceid'
    }
    if norm_name in common_id_names:
        return True
    
    # Regex match on patterns (e.g. customer_id, order_no, employee_num)
    if ID_PATTERN.search(clean_name):
        return True

    # High cardinality check for unique identifiers
    if total_rows > 1 and series.nunique() == total_rows:
        if pd.api.types.is_string_dtype(series) or pd.api.types.is_integer_dtype(series):
            if any(term in norm_name for term in ['id', 'num', 'code', 'key', 'roll', 'ref', 'index']):
                return True
                
    return False

def classify_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Classifies DataFrame columns dynamically based strictly on actual data and names.
    Returns both plural and short keys to ensure zero KeyError exceptions.
    """
    total_rows = len(df)
    
    identifiers: List[str] = []
    numerics: List[str] = []
    targets: List[str] = []
    kpis: List[str] = []
    categoricals: List[str] = []
    dates: List[str] = []
    booleans: List[str] = []
    texts: List[str] = []

    for col in df.columns:
        series = df[col]

        # 1. Identifier Check (Evaluated first to prevent numeric IDs from becoming business metrics)
        if is_identifier_column(col, series, total_rows):
            identifiers.append(col)
            continue

        # 2. Boolean Check
        if pd.api.types.is_bool_dtype(series) or (
            total_rows > 0 and series.dropna().isin([0, 1, True, False, "Yes", "No", "yes", "no"]).all() and series.nunique() <= 2
        ):
            booleans.append(col)
            continue

        # 3. Date Check
        if pd.api.types.is_datetime64_any_dtype(series):
            dates.append(col)
            continue
        elif series.dtype == 'object' or pd.api.types.is_string_dtype(series):
            if any(term in str(col).lower() for term in ['date', 'time', 'year', 'month', 'day', 'created', 'updated', 'joined', 'shipped', 'timestamp']):
                sample = series.dropna().head(20)
                if not sample.empty:
                    try:
                        parsed = pd.to_datetime(sample, format='mixed', errors='coerce')
                        if parsed.notnull().sum() / len(sample) > 0.8:
                            dates.append(col)
                            continue
                    except Exception:
                        pass

        # 4. Target & Budget Column Check
        col_lower = str(col).lower()
        if pd.api.types.is_numeric_dtype(series) and any(term in col_lower for term in ['target', 'goal', 'budget', 'quota', 'forecast', 'projected']):
            targets.append(col)
            numerics.append(col)
            continue

        # 5. KPI / Ratio / Rate Column Check
        if pd.api.types.is_numeric_dtype(series) and any(term in col_lower for term in ['margin', 'rate', 'ratio', 'percent', 'pct']):
            kpis.append(col)
            numerics.append(col)
            continue

        # 6. Standard Numeric Check
        if pd.api.types.is_numeric_dtype(series):
            numerics.append(col)
            continue

        # 7. Categorical vs Long Text Check
        unique_ratio = series.nunique() / max(total_rows, 1)
        if unique_ratio < 0.5 or series.nunique() <= 50:
            categoricals.append(col)
        else:
            texts.append(col)

    # Safe double-keying: provides both plural and short keys
    return {
        "identifier_columns": identifiers,
        "numeric_columns": numerics,
        "target_columns": targets,
        "kpi_columns": kpis,
        "categorical_columns": categoricals,
        "date_columns": dates,
        "text_columns": texts,
        "boolean_columns": booleans,
        "identifier_cols": identifiers,
        "numeric_cols": numerics,
        "target_cols": targets,
        "kpi_cols": kpis,
        "categorical_cols": categoricals,
        "date_cols": dates,
        "text_cols": texts,
        "boolean_cols": booleans
    }

def find_best_column_match(
    target_name: str,
    available_cols: List[str],
    semantic_dict: Optional[Dict[str, List[str]]] = None
) -> str:
    """
    Dynamically resolves a target term to an actual DataFrame column using:
    1. Exact match (case-insensitive)
    2. Normalized match (ignoring whitespace, underscores, special characters)
    3. Synonym match (via knowledge base dictionary, ONLY if the column actually exists in CSV)
    4. Partial / substring match
    5. Fuzzy match (difflib)
    
    Returns the exact matching column name as found in available_cols, or empty string if no match.
    NEVER creates or invents fake columns.
    """
    if not target_name or not available_cols:
        return ""

    target_str = str(target_name).strip()
    target_lower = target_str.lower()
    target_norm = normalize_text(target_str)
    
    available_cols_list = list(available_cols)
    norm_map = {normalize_text(c): c for c in available_cols_list}

    # 1. Exact match (case-insensitive)
    for col in available_cols_list:
        if str(col).strip().lower() == target_lower:
            return col

    # 2. Normalized match (e.g., 'customer_id' matches 'CustomerID' or 'Customer ID')
    if target_norm in norm_map:
        return norm_map[target_norm]

    # 3. Synonym matching via knowledge base
    # NOTE: The dictionary is only a knowledge base. Mappings are ONLY used if a matching column exists.
    dictionary = semantic_dict if semantic_dict is not None else SEMANTIC_DICTIONARY
    target_concepts = []
    
    # Check if target is a concept key or in synonyms
    for concept, synonyms in dictionary.items():
        syn_norms = [normalize_text(s) for s in synonyms]
        if target_norm == normalize_text(concept) or target_norm in syn_norms:
            target_concepts.append(concept)

    # Search for an available column that matches any synonym of the target concept
    for concept in target_concepts:
        for syn in dictionary.get(concept, []):
            syn_norm = normalize_text(syn)
            if syn_norm in norm_map:
                return norm_map[syn_norm]
            # Partial match on synonym
            for col in available_cols_list:
                col_norm = normalize_text(col)
                if len(syn_norm) >= 4 and (syn_norm in col_norm or col_norm in syn_norm):
                    return col

    # 4. Partial / Substring match (min 3 characters to avoid noisy 1-2 char false positives)
    if len(target_norm) >= 3:
        for col in available_cols_list:
            col_norm = normalize_text(col)
            if target_norm in col_norm or col_norm in target_norm:
                return col

    # 5. Fuzzy match (e.g. typos like 'prodcut' -> 'Product', 'qunatity' -> 'Quantity')
    if len(target_norm) >= 3:
        close_norms = difflib.get_close_matches(target_norm, list(norm_map.keys()), n=1, cutoff=0.75)
        if close_norms:
            return norm_map[close_norms[0]]

    return ""

def get_detected_semantic_mappings(available_cols: List[str]) -> Dict[str, str]:
    """
    Identifies which semantic concepts from the knowledge base ACTUALLY exist in the uploaded CSV.
    Missing concepts are simply omitted. Never creates fake columns.
    """
    detected = {}
    for concept in SEMANTIC_DICTIONARY.keys():
        match = find_best_column_match(concept, available_cols)
        if match:
            detected[concept] = match
    return detected

def detect_domains(df: pd.DataFrame, classified_cols: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Detects primary & secondary dataset domains dynamically with confidence scores.
    Supports ANY domain. Defaults to 'General Analytics' gracefully if unknown.
    """
    all_col_text = " ".join([str(c).lower() for c in df.columns])
    cat_cols = classified_cols.get("categorical_cols", classified_cols.get("categorical_columns", []))
    
    domain_scores = {}
    for domain, spec in DOMAIN_SEMANTICS.items():
        score = 0
        for kw in spec.get("keywords", []):
            if kw in all_col_text:
                score += 2
            # Check a tiny sample of text columns safely
            for text_col in cat_cols[:2]:
                if text_col in df.columns and len(df) > 0:
                    try:
                        sample = df[text_col].dropna().head(10).astype(str)
                        if sample.str.contains(kw, case=False, na=False).any():
                            score += 1
                    except Exception:
                        pass

        if score > 0:
            domain_scores[domain] = score

    if not domain_scores:
        return {
            "primary_domain": "General Analytics",
            "secondary_domains": [],
            "domain_confidence": 0.50
        }

    sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
    max_score = sorted_domains[0][1]
    confidence = min(round(max_score / 10.0, 2), 0.99)
    if confidence < 0.4:
        confidence = 0.55

    primary = sorted_domains[0][0]
    secondaries = [d[0] for d in sorted_domains[1:3] if d[1] >= 2]

    return {
        "primary_domain": primary,
        "secondary_domains": secondaries,
        "domain_confidence": confidence
    }

def perform_data_quality_audit(df: pd.DataFrame, classified_cols: Dict[str, List[str]]) -> Dict[str, Any]:
    """Performs comprehensive data quality audits safely without assuming any fixed columns."""
    total_rows = len(df)
    missing_dict = df.isnull().sum().to_dict()
    missing_cols = {col: int(cnt) for col, cnt in missing_dict.items() if cnt > 0}
    
    duplicate_rows = int(df.duplicated().sum()) if total_rows > 0 else 0
    
    duplicate_ids = {}
    id_cols = classified_cols.get("identifier_columns", classified_cols.get("identifier_cols", []))
    for id_col in id_cols:
        if id_col in df.columns and total_rows > 0:
            dups = int(df[id_col].duplicated().sum())
            if dups > 0:
                duplicate_ids[id_col] = dups

    negative_value_warnings = []
    num_cols = classified_cols.get("numeric_columns", classified_cols.get("numeric_cols", []))
    for num_col in num_cols:
        if num_col in df.columns and total_rows > 0:
            if any(kw in str(num_col).lower() for kw in ['sales', 'revenue', 'price', 'cost', 'age', 'quantity', 'salary', 'marks', 'count']):
                try:
                    neg_count = int((df[num_col] < 0).sum())
                    if neg_count > 0:
                        negative_value_warnings.append(f"Column '{num_col}' contains {neg_count} negative value(s).")
                except Exception:
                    pass

    constant_cols = [col for col in df.columns if total_rows > 0 and df[col].nunique() == 1]
    cat_cols = classified_cols.get("categorical_columns", classified_cols.get("categorical_cols", []))
    high_cardinality = [col for col in cat_cols if col in df.columns and total_rows > 0 and df[col].nunique() > 30]

    return {
        "total_missing_values": int(df.isnull().sum().sum()),
        "missing_by_column": missing_cols,
        "duplicate_rows": duplicate_rows,
        "duplicate_identifiers": duplicate_ids,
        "negative_value_warnings": negative_value_warnings,
        "constant_columns": constant_cols,
        "high_cardinality_columns": high_cardinality,
        "quality_score": max(0, round(100 - (len(missing_cols)*5 + duplicate_rows*2), 1))
    }

def generate_universal_questions(
    df: pd.DataFrame,
    classified_cols: Dict[str, List[str]],
    domain_info: Optional[Dict[str, Any]] = None
) -> List[str]:
    """
    Generates suggested questions ONLY from columns that actually exist in the current DataFrame.
    NEVER mentions 'salary', 'profit', or any term unless that column actually exists.
    """
    questions: List[str] = []
    metrics = [c for c in classified_cols.get("numeric_columns", classified_cols.get("numeric_cols", [])) if c in df.columns]
    dims = [c for c in classified_cols.get("categorical_columns", classified_cols.get("categorical_cols", [])) if c in df.columns]
    dates = [c for c in classified_cols.get("date_columns", classified_cols.get("date_cols", [])) if c in df.columns]
    ids = [c for c in classified_cols.get("identifier_columns", classified_cols.get("identifier_cols", [])) if c in df.columns]

    # 1. Total & Average Aggregation Questions (Using actual metric columns)
    if metrics:
        top_metric = metrics[0]
        questions.append(f"What is the total {top_metric}?")
        if len(metrics) > 1:
            questions.append(f"What is the average {metrics[1]}?")
        else:
            questions.append(f"What is the average {top_metric}?")

    # 2. Group Breakdown Questions (Using actual metric and dimension columns)
    if metrics and dims:
        questions.append(f"What is the average {metrics[0]} by {dims[0]}?")
        questions.append(f"Which {dims[0]} has the highest {metrics[0]}?")
        if len(dims) > 1:
            questions.append(f"Show {metrics[0]} by {dims[1]}.")
        questions.append(f"Show the top 5 {dims[0]} by total {metrics[0]}.")
    elif dims and not metrics:
        questions.append(f"What is the record count by {dims[0]}?")
        if len(dims) > 1:
            questions.append(f"Which {dims[1]} has the most occurrences?")

    # 3. Unique Count Questions (Using actual identifier or dimension columns)
    if ids:
        questions.append(f"How many unique {ids[0]} are there?")
    elif dims:
        questions.append(f"How many unique {dims[0]} are there?")

    # 4. Time Trend Questions (Using actual date and metric columns)
    if dates and metrics:
        questions.append(f"Show {metrics[0]} trend over time.")

    # 5. Data Quality Questions (Always applicable)
    questions.append("Give me a data quality summary of the dataset.")
    questions.append("Are there any missing values or duplicate records?")

    return questions[:8]

def process_csv(filepath: str, max_row_limit: int = 200000) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Loads CSV dataset safely, performs dynamic profiling, domain detection, and quality auditing.
    Supports datasets with 5, 20, 100, or 500+ columns from ANY domain.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found at path: {filepath}")

    # File size validation (Chunk loading safety for large CSVs)
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if file_size_mb > 150:
        df = pd.read_csv(filepath, nrows=max_row_limit)
    else:
        df = pd.read_csv(filepath)

    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. Classify Columns Dynamically
    classified = classify_columns(df)
    
    # Auto-convert verified date columns to datetime objects
    for d_col in classified.get("date_columns", []):
        if d_col in df.columns:
            try:
                df[d_col] = pd.to_datetime(df[d_col], errors='coerce')
            except Exception:
                pass

    # 2. Detect Domain Gracefully
    domain_info = detect_domains(df, classified)

    # 3. Audit Data Quality Safely
    quality_audit = perform_data_quality_audit(df, classified)

    # 4. Generate Dynamic Questions ONLY from actual columns
    suggested_questions = generate_universal_questions(df, classified, domain_info)

    # 5. Identify detected semantic mappings (only those that actually exist)
    detected_semantics = get_detected_semantic_mappings(list(df.columns))

    profile = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
        "identifier_cols": classified.get("identifier_columns", []),
        "numeric_cols": classified.get("numeric_columns", []),
        "target_cols": classified.get("target_columns", []),
        "kpi_cols": classified.get("kpi_columns", []),
        "categorical_cols": classified.get("categorical_columns", []),
        "date_cols": classified.get("date_columns", []),
        "text_cols": classified.get("text_columns", []),
        "boolean_cols": classified.get("boolean_columns", []),
        "detected_semantics": detected_semantics,
        "domain_info": domain_info,
        "quality_audit": quality_audit,
        "suggested_questions": suggested_questions
    }

    summary = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
        "sample_data": df.head(100).fillna("").to_dict(orient='records'),
        "domain": domain_info.get("primary_domain", "General Analytics"),
        "suggested_questions": suggested_questions,
        "profile": profile
    }

    return df, summary