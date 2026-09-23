import re
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime

class DataCleaner:
    """Enterprise Data Validation & Cleaning Engine.
    
    Performs dataset-agnostic validation, sanitization, and audit reporting:
    - Missing value resolution (smart zero/median for numerics, 'Unknown' for categories)
    - Duplicate row detection & removal
    - Currency and numeric string sanitization (₹, $, commas, K/M suffixes)
    - Date format standardization to YYYY-MM-DD
    - Whitespace trimming and empty string normalization
    - Cross-column chronological validation (e.g. Order <= Delivery <= Return)
    - Comprehensive Before vs. After Data Quality audit with 0-100% Quality Score.
    """

    @staticmethod
    def sanitize_numeric_value(val: Any) -> Tuple[Any, bool]:
        """Attempts to parse currency strings or suffixed numbers into clean floats.
        Returns: (parsed_value, was_sanitized_bool)
        """
        if pd.isna(val):
            return val, False
        if isinstance(val, (int, float, np.number)):
            return float(val), False
        
        s = str(val).strip()
        # Check if already purely numeric
        try:
            return float(s), False
        except ValueError:
            pass

        # Check for currency symbols, commas, and suffixes
        # e.g. ₹50,000, $120.50, 50K, 1.5M, 20%
        clean_s = re.sub(r'[₹$€£,\s]', '', s)
        multiplier = 1.0

        if clean_s.endswith(('%', 'pct')):
            clean_s = clean_s.rstrip('%pct')
        elif clean_s.endswith(('k', 'K')):
            clean_s = clean_s[:-1]
            multiplier = 1_000.0
        elif clean_s.endswith(('m', 'M')):
            clean_s = clean_s[:-1]
            multiplier = 1_000_000.0
        elif clean_s.endswith(('b', 'B')):
            clean_s = clean_s[:-1]
            multiplier = 1_000_000_000.0

        try:
            num = float(clean_s) * multiplier
            return num, True
        except (ValueError, TypeError):
            return val, False

    def validate_and_clean(
        self,
        df: pd.DataFrame,
        classified_cols: Optional[Dict[str, List[str]]] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Runs the complete validation, cleaning, and quality audit pipeline."""
        if df is None or df.empty:
            return df, {
                "total_rows_before": 0,
                "total_rows_after": 0,
                "total_cols": 0,
                "quality_score": 100.0,
                "operations_performed": ["Empty dataset received; no cleaning required."],
                "duplicates_removed": 0,
                "missing_values_fixed": 0,
                "invalid_dates_fixed": 0,
                "numeric_strings_sanitized": 0,
                "chronological_anomalies": 0,
                "column_stats": {}
            }

        # Working copy to preserve original df
        clean_df = df.copy()
        total_rows_before = len(clean_df)
        total_cols = len(clean_df.columns)
        operations = []
        column_stats = {}

        # If classified_cols is not provided, dynamically derive basic roles
        if not classified_cols:
            classified_cols = {
                "identifier_columns": [c for c in clean_df.columns if 'id' in c.lower() or 'code' in c.lower()],
                "numeric_columns": [c for c in clean_df.columns if pd.api.types.is_numeric_dtype(clean_df[c]) and 'id' not in c.lower()],
                "categorical_columns": [c for c in clean_df.columns if clean_df[c].dtype == 'object'],
                "date_columns": [c for c in clean_df.columns if 'date' in c.lower() or 'time' in c.lower() or 'day' in c.lower()],
                "boolean_columns": [c for c in clean_df.columns if pd.api.types.is_bool_dtype(clean_df[c])]
            }

        num_cols = set(classified_cols.get("numeric_columns", []))
        date_cols = set(classified_cols.get("date_columns", []))
        cat_cols = set(classified_cols.get("categorical_columns", []))
        id_cols = set(classified_cols.get("identifier_columns", []))
        bool_cols = set(classified_cols.get("boolean_columns", []))

        # Initial metrics before cleaning
        missing_before_total = int(clean_df.isna().sum().sum())
        duplicates_before = int(clean_df.duplicated().sum())

        # -------------------------------------------------------------
        # STEP 1: DUPLICATE ROW REMOVAL
        # -------------------------------------------------------------
        if duplicates_before > 0:
            clean_df = clean_df.drop_duplicates().reset_index(drop=True)
            operations.append(f"Removed {duplicates_before} exact duplicate row(s)")
        else:
            operations.append("No duplicate rows found")

        # -------------------------------------------------------------
        # STEP 2: TEXT SANITIZATION & WHITESPACE TRIMMING
        # -------------------------------------------------------------
        text_anomalies_fixed = 0
        for col in clean_df.columns:
            if clean_df[col].dtype == 'object':
                # Convert string representation of nulls to np.nan
                clean_mask = clean_df[col].astype(str).str.strip().str.lower().isin(
                    ['', 'nan', 'null', 'none', 'n/a', '#n/a', 'na', '?']
                )
                if clean_mask.any():
                    text_anomalies_fixed += int(clean_mask.sum())
                    clean_df.loc[clean_mask, col] = np.nan
                
                # Strip leading/trailing whitespace
                non_null_mask = clean_df[col].notna()
                clean_df.loc[non_null_mask, col] = clean_df.loc[non_null_mask, col].astype(str).str.strip()

        if text_anomalies_fixed > 0:
            operations.append(f"Normalized {text_anomalies_fixed} empty/whitespace string(s) to null")

        # -------------------------------------------------------------
        # STEP 3: CURRENCY & NUMERIC STRING SANITIZATION
        # -------------------------------------------------------------
        numeric_strings_sanitized = 0
        # Check candidate numeric columns that might be typed as object
        for col in list(clean_df.columns):
            if col in id_cols or col in date_cols:
                continue
            
            # Check if column has string representations of numbers (e.g. ₹50,000, 50K)
            if clean_df[col].dtype == 'object':
                sanitized_count = 0
                temp_vals = []
                for val in clean_df[col]:
                    new_val, was_sanitized = self.sanitize_numeric_value(val)
                    if was_sanitized:
                        sanitized_count += 1
                    temp_vals.append(new_val)
                
                # If more than 30% of non-nulls or any sanitized numbers exist
                non_nulls = [v for v in temp_vals if pd.notna(v)]
                numeric_count = sum(1 for v in non_nulls if isinstance(v, (int, float, np.number)))
                if non_nulls and (numeric_count / len(non_nulls) >= 0.7 or sanitized_count > 0):
                    clean_df[col] = pd.to_numeric(temp_vals, errors='coerce')
                    num_cols.add(col)
                    cat_cols.discard(col)
                    numeric_strings_sanitized += sanitized_count
                    if sanitized_count > 0:
                        operations.append(f"Sanitized {sanitized_count} currency/formatted values in '{col}' to clean numeric float")

        # -------------------------------------------------------------
        # STEP 4: DATE FORMAT STANDARDIZATION & INVALID DATE DETECTION
        # -------------------------------------------------------------
        invalid_dates_fixed = 0
        for col in list(clean_df.columns):
            if col in date_cols:
                missing_dates_before = clean_df[col].isna().sum()
                # Parse to datetime
                parsed_dates = pd.to_datetime(clean_df[col], errors='coerce')
                missing_dates_after = parsed_dates.isna().sum()
                
                invalid_dates_in_col = int(missing_dates_after - missing_dates_before)
                if invalid_dates_in_col > 0:
                    invalid_dates_fixed += invalid_dates_in_col
                    operations.append(f"Detected {invalid_dates_in_col} unparseable date(s) in '{col}' (marked as null)")
                
                # Standardize to YYYY-MM-DD string where valid
                clean_df[col] = parsed_dates.dt.strftime('%Y-%m-%d')
                operations.append(f"Standardized date formatting in '{col}' to YYYY-MM-DD")

        # -------------------------------------------------------------
        # STEP 5: CROSS-COLUMN CHRONOLOGICAL VALIDATION
        # -------------------------------------------------------------
        chronological_anomalies = 0
        active_date_cols = [c for c in clean_df.columns if c in date_cols]
        # Check chronological pairing (order <= delivery <= return)
        order_col = next((c for c in active_date_cols if 'order' in c.lower()), None)
        deliv_col = next((c for c in active_date_cols if 'deliv' in c.lower()), None)
        return_col = next((c for c in active_date_cols if 'return' in c.lower()), None)

        if order_col and deliv_col:
            o_dt = pd.to_datetime(clean_df[order_col], errors='coerce')
            d_dt = pd.to_datetime(clean_df[deliv_col], errors='coerce')
            invalid_pair = (o_dt.notna() & d_dt.notna() & (o_dt > d_dt))
            anomaly_cnt = int(invalid_pair.sum())
            if anomaly_cnt > 0:
                chronological_anomalies += anomaly_cnt
                operations.append(f"Detected {anomaly_cnt} chronological anomaly where '{order_col}' > '{deliv_col}'")

        if deliv_col and return_col:
            d_dt = pd.to_datetime(clean_df[deliv_col], errors='coerce')
            r_dt = pd.to_datetime(clean_df[return_col], errors='coerce')
            invalid_pair = (d_dt.notna() & r_dt.notna() & (d_dt > r_dt))
            anomaly_cnt = int(invalid_pair.sum())
            if anomaly_cnt > 0:
                chronological_anomalies += anomaly_cnt
                operations.append(f"Detected {anomaly_cnt} chronological anomaly where '{deliv_col}' > '{return_col}'")

        # -------------------------------------------------------------
        # STEP 6: SMART MISSING VALUE RESOLUTION
        # -------------------------------------------------------------
        missing_values_fixed = 0
        for col in clean_df.columns:
            null_count = int(clean_df[col].isna().sum())
            if null_count == 0:
                column_stats[col] = {
                    "missing_before": 0,
                    "missing_after": 0,
                    "dtype": str(clean_df[col].dtype),
                    "action": "Clean (No missing values)"
                }
                continue

            missing_values_fixed += null_count
            
            # Numeric column strategy
            if col in num_cols or pd.api.types.is_numeric_dtype(clean_df[col]):
                # Fill with 0 for quantity, discount, rate, cost, profit, bonus, tax
                zero_friendly = any(k in col.lower() for k in ['discount', 'tax', 'bonus', 'qty', 'quantity', 'fee', 'charge', 'return', 'cancel'])
                if zero_friendly:
                    clean_df[col] = clean_df[col].fillna(0.0)
                    column_stats[col] = {
                        "missing_before": null_count,
                        "missing_after": 0,
                        "dtype": str(clean_df[col].dtype),
                        "action": f"Filled {null_count} null(s) with 0.0"
                    }
                else:
                    median_val = clean_df[col].median()
                    fill_val = round(float(median_val), 2) if pd.notna(median_val) else 0.0
                    clean_df[col] = clean_df[col].fillna(fill_val)
                    column_stats[col] = {
                        "missing_before": null_count,
                        "missing_after": 0,
                        "dtype": str(clean_df[col].dtype),
                        "action": f"Filled {null_count} null(s) with median ({fill_val})"
                    }

            # Categorical/Text strategy
            elif col in cat_cols or clean_df[col].dtype == 'object':
                if col in date_cols:
                    # Do not invent fake dates! Keep NaT / blank
                    column_stats[col] = {
                        "missing_before": null_count,
                        "missing_after": null_count,
                        "dtype": str(clean_df[col].dtype),
                        "action": f"Preserved {null_count} missing date(s) (will not invent dates)"
                    }
                else:
                    clean_df[col] = clean_df[col].fillna("Unknown")
                    column_stats[col] = {
                        "missing_before": null_count,
                        "missing_after": 0,
                        "dtype": str(clean_df[col].dtype),
                        "action": f"Filled {null_count} null(s) with 'Unknown'"
                    }

            # Boolean strategy
            elif col in bool_cols or pd.api.types.is_bool_dtype(clean_df[col]):
                clean_df[col] = clean_df[col].fillna(False)
                column_stats[col] = {
                    "missing_before": null_count,
                    "missing_after": 0,
                    "dtype": str(clean_df[col].dtype),
                    "action": f"Filled {null_count} boolean null(s) with False"
                }
            else:
                clean_df[col] = clean_df[col].fillna("Unknown")
                column_stats[col] = {
                    "missing_before": null_count,
                    "missing_after": 0,
                    "dtype": str(clean_df[col].dtype),
                    "action": f"Filled {null_count} null(s) with 'Unknown'"
                }

        if missing_values_fixed > 0:
            operations.append(f"Resolved {missing_values_fixed} missing value(s) across {len(column_stats)} column(s)")

        # -------------------------------------------------------------
        # STEP 7: QUALITY SCORE CALCULATION
        # -------------------------------------------------------------
        total_cells = max(1, total_rows_before * total_cols)
        problematic_elements = (
            missing_before_total +
            (duplicates_before * total_cols) +
            invalid_dates_fixed +
            numeric_strings_sanitized +
            chronological_anomalies
        )
        
        # Penalized ratio scaled to 100
        error_ratio = problematic_elements / total_cells
        quality_score = max(0.0, min(100.0, round(100.0 - (error_ratio * 100.0), 1)))

        quality_report = {
            "total_rows_before": total_rows_before,
            "total_rows_after": len(clean_df),
            "total_cols": total_cols,
            "duplicates_removed": duplicates_before,
            "missing_values_fixed": missing_values_fixed,
            "invalid_dates_fixed": invalid_dates_fixed,
            "numeric_strings_sanitized": numeric_strings_sanitized,
            "chronological_anomalies": chronological_anomalies,
            "quality_score": quality_score,
            "operations_performed": operations,
            "column_stats": column_stats
        }

        return clean_df, quality_report

# Singleton instance
data_cleaner = DataCleaner()

