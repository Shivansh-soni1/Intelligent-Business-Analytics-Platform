import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
from services.db_service import db_service

class KPIEngine:
    """Enterprise KPI Calculation and Time-Based Monitoring Engine.
    
    Operates strictly via deterministic Pandas calculations (zero eval()).
    Computes:
    - Actual Value vs. Target Value
    - Variance & Variance %
    - Achievement %
    - Elapsed Time vs. Expected Progress %
    - Performance Gap (Actual Progress - Expected Progress)
    - Status Classification (EXCEEDED, ON TRACK, AT RISK, CRITICAL)
    """

    ALLOWED_CALCULATIONS = {
        "SUM", "AVERAGE", "MEAN", "COUNT", "MIN", "MAX", "MEDIAN", "RATE", "PERCENTAGE"
    }

    def evaluate_kpi(
        self,
        kpi: Dict[str, Any],
        df: pd.DataFrame,
        as_of_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Calculates performance metrics for a single KPI against a DataFrame."""
        if df is None or df.empty:
            raise ValueError("Cannot evaluate KPI against an empty dataset.")

        metric_col = kpi["metric_column"]
        if metric_col not in df.columns:
            raise KeyError(f"Metric column '{metric_col}' not found in current dataset.")

        working_df = df.copy()

        # -------------------------------------------------------------
        # 1. OPTIONAL DATE RANGE FILTERING
        # -------------------------------------------------------------
        start_date_str = kpi.get("start_date")
        end_date_str = kpi.get("end_date")

        start_dt = None
        end_dt = None
        if start_date_str:
            try:
                start_dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                pass

        # If date filtering is possible, look for a suitable date column
        if start_dt or end_dt:
            date_col = next((c for c in working_df.columns if 'date' in c.lower() or 'time' in c.lower() or 'day' in c.lower()), None)
            if date_col:
                dt_series = pd.to_datetime(working_df[date_col], errors='coerce').dt.date
                if start_dt:
                    working_df = working_df[dt_series >= start_dt]
                if end_dt:
                    working_df = working_df[dt_series <= end_dt]

        if working_df.empty:
            actual_val = 0.0
        else:
            # -------------------------------------------------------------
            # 2. DETERMINISTIC AGGREGATION VIA PANDAS
            # -------------------------------------------------------------
            calc_type = kpi.get("calculation", "SUM").upper()
            series = working_df[metric_col]

            # Ensure series is numeric if applying math
            if not pd.api.types.is_numeric_dtype(series) and calc_type != "COUNT":
                series = pd.to_numeric(series, errors='coerce').fillna(0.0)

            if calc_type == "SUM":
                actual_val = float(series.sum())
            elif calc_type in ("AVERAGE", "MEAN"):
                actual_val = float(series.mean())
            elif calc_type == "MEDIAN":
                actual_val = float(series.median())
            elif calc_type == "MIN":
                actual_val = float(series.min())
            elif calc_type == "MAX":
                actual_val = float(series.max())
            elif calc_type == "COUNT":
                actual_val = float(series.count())
            elif calc_type in ("RATE", "PERCENTAGE"):
                # Average rate or percentage
                actual_val = float(series.mean())
            else:
                actual_val = float(series.sum())

        target_val = float(kpi["target_value"])
        actual_val = round(actual_val, 2)
        variance = round(actual_val - target_val, 2)
        variance_pct = round((variance / target_val * 100.0), 2) if target_val != 0 else 0.0
        achievement_pct = round((actual_val / target_val * 100.0), 2) if target_val != 0 else 0.0

        # -------------------------------------------------------------
        # 3. TIME-BASED MONITORING (ELAPSED VS. EXPECTED PROGRESS)
        # -------------------------------------------------------------
        current_date = as_of_date or datetime.utcnow().date()
        if start_dt and end_dt and end_dt > start_dt:
            days_passed = max(0, (current_date - start_dt).days)
            total_days = max(1, (end_dt - start_dt).days)
            expected_progress_pct = round(min(100.0, max(0.0, (days_passed / total_days) * 100.0)), 2)
        else:
            expected_progress_pct = 100.0

        actual_progress_pct = achievement_pct
        performance_gap = round(actual_progress_pct - expected_progress_pct, 2)

        # -------------------------------------------------------------
        # 4. KPI STATUS ENGINE
        # -------------------------------------------------------------
        threshold_pct = float(kpi.get("alert_threshold_pct", 10.0))
        
        if achievement_pct >= 100.0:
            status = "EXCEEDED"
        elif performance_gap >= 0.0 or achievement_pct >= (100.0 - threshold_pct):
            status = "ON TRACK"
        elif performance_gap >= -15.0 or achievement_pct >= 70.0:
            status = "AT RISK"
        else:
            status = "CRITICAL"

        snapshot = {
            "kpi_id": kpi["id"],
            "kpi_name": kpi.get("kpi_name", metric_col),
            "metric_column": metric_col,
            "calculation": kpi.get("calculation", "SUM"),
            "actual_value": actual_val,
            "target_value": target_val,
            "variance": variance,
            "variance_pct": variance_pct,
            "achievement_pct": achievement_pct,
            "expected_progress_pct": expected_progress_pct,
            "actual_progress_pct": actual_progress_pct,
            "performance_gap": performance_gap,
            "status": status,
            "recipients": kpi.get("recipients", "")
        }

        # Save historical snapshot to DB
        snapshot_id = db_service.save_kpi_snapshot(snapshot)
        snapshot["snapshot_id"] = snapshot_id

        return snapshot

    def evaluate_all(
        self,
        df: pd.DataFrame,
        dataset_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Evaluates all active configured KPIs against the current DataFrame."""
        kpis = db_service.get_kpis(dataset_id=dataset_id, active_only=True)
        results = []
        for kpi in kpis:
            try:
                res = self.evaluate_kpi(kpi, df)
                results.append(res)
            except Exception as e:
                # Still record failed evaluation gracefully
                results.append({
                    "kpi_id": kpi["id"],
                    "kpi_name": kpi.get("kpi_name", ""),
                    "error": str(e),
                    "status": "ERROR"
                })
        return results

# Singleton instance
kpi_engine = KPIEngine()

