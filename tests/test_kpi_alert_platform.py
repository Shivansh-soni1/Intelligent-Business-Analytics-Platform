import unittest
import os
import tempfile
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date

from services.data_cleaner import DataCleaner
from services.db_service import DatabaseService
from services.kpi_engine import KPIEngine
from services.alert_engine import AlertEngine
from services.email_service import EmailService
from services.scheduler_service import SchedulerService
from services.query_processor import handle_question

class TestKPIAlertPlatform(unittest.TestCase):
    """Automated test suite for Data Quality, KPI Engine, Time-Based Monitoring,
    Alert Decisions, Anti-Spam Cooldown, and AI KPI Grounding.
    """

    def setUp(self):
        # Create isolated temporary database for test suite
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_file.close()
        self.db = DatabaseService(db_path=self.temp_db_file.name)
        self.cleaner = DataCleaner()
        self.kpi_engine = KPIEngine()
        self.email_service = EmailService()
        self.email_service.email_enabled = False # Guarantee mock mode

    def tearDown(self):
        if os.path.exists(self.temp_db_file.name):
            try:
                os.remove(self.temp_db_file.name)
            except Exception:
                pass

    # -------------------------------------------------------------
    # 1. DATA VALIDATION & CLEANING TESTS
    # -------------------------------------------------------------
    def test_duplicate_row_removal(self):
        raw_data = pd.DataFrame({
            "Order_ID": [101, 102, 101, 103],
            "Product": ["Laptop", "Mouse", "Laptop", "Keyboard"],
            "Sales": [1200.0, 25.0, 1200.0, 75.0]
        })
        clean_df, report = self.cleaner.validate_and_clean(raw_data)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertEqual(len(clean_df), 3)

    def test_currency_and_suffixed_number_sanitization(self):
        raw_data = pd.DataFrame({
            "Product": ["Widget A", "Widget B", "Widget C", "Widget D"],
            "Price": ["₹50,000", "$120.50", "15K", "1.2M"]
        })
        clean_df, report = self.cleaner.validate_and_clean(raw_data)
        self.assertGreater(report["numeric_strings_sanitized"], 0)
        self.assertTrue(pd.api.types.is_numeric_dtype(clean_df["Price"]))
        self.assertAlmostEqual(clean_df["Price"].iloc[0], 50000.0)
        self.assertAlmostEqual(clean_df["Price"].iloc[1], 120.50)
        self.assertAlmostEqual(clean_df["Price"].iloc[2], 15000.0)
        self.assertAlmostEqual(clean_df["Price"].iloc[3], 1200000.0)

    def test_date_standardization_and_unparseable_detection(self):
        raw_data = pd.DataFrame({
            "Order_Date": ["2026/09/01", "01-09-2026", "invalid_date", "2026-09-05"]
        })
        clean_df, report = self.cleaner.validate_and_clean(raw_data)
        self.assertIn("invalid_dates_fixed", report)
        self.assertEqual(report["invalid_dates_fixed"], 1)
        self.assertEqual(clean_df["Order_Date"].iloc[0], "2026-09-01")

    def test_missing_values_resolution_strategies(self):
        raw_data = pd.DataFrame({
            "Category": ["Electronics", None, "Books"],
            "Discount": [10.0, None, 5.0],
            "Units": [100.0, None, 300.0],
            "Is_Active": [True, None, False]
        })
        clean_df, report = self.cleaner.validate_and_clean(raw_data)
        self.assertGreater(report["missing_values_fixed"], 0)
        # Category null filled with 'Unknown'
        self.assertEqual(clean_df["Category"].iloc[1], "Unknown")
        # Discount (zero-friendly) filled with 0.0
        self.assertEqual(clean_df["Discount"].iloc[1], 0.0)
        # Units filled with median (200.0)
        self.assertEqual(clean_df["Units"].iloc[1], 200.0)
        # Boolean filled with False
        self.assertEqual(clean_df["Is_Active"].iloc[1], False)

    def test_chronological_anomaly_detection(self):
        raw_data = pd.DataFrame({
            "Order_Date": ["2026-09-05", "2026-09-01"],
            "Delivery_Date": ["2026-09-01", "2026-09-03"] # First row: Order (09-05) > Delivery (09-01)!
        })
        _, report = self.cleaner.validate_and_clean(raw_data)
        self.assertEqual(report["chronological_anomalies"], 1)

    def test_quality_score_computation(self):
        # Clean dataframe should score 100%
        clean_data = pd.DataFrame({"A": [1, 2, 3], "B": ["X", "Y", "Z"]})
        _, report = self.cleaner.validate_and_clean(clean_data)
        self.assertEqual(report["quality_score"], 100.0)

    # -------------------------------------------------------------
    # 2. DATABASE PERSISTENCE TESTS
    # -------------------------------------------------------------
    def test_dataset_save_and_reconstruction(self):
        df = pd.DataFrame({"ID": [1, 2], "Val": [10.5, 20.5]})
        self.db.save_dataset(
            dataset_id="test_ds_1",
            name="test.csv",
            filename="test.csv",
            row_count=2,
            col_count=2,
            quality_score=98.5,
            quality_report={"quality_score": 98.5},
            schema_profile={"numeric_cols": ["Val"]},
            clean_df=df
        )

        latest = self.db.get_latest_dataset()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["id"], "test_ds_1")

        reconstructed_df = self.db.get_clean_records_df("test_ds_1")
        self.assertEqual(len(reconstructed_df), 2)
        self.assertAlmostEqual(float(reconstructed_df["Val"].iloc[0]), 10.5)

    def test_kpi_crud_operations(self):
        kpi_data = {
            "kpi_name": "Target Revenue",
            "metric_column": "Revenue",
            "calculation": "SUM",
            "target_value": 100000.0,
            "period": "Monthly",
            "recipients": "test@example.com"
        }
        kpi_id = self.db.save_kpi(kpi_data)
        self.assertTrue(kpi_id.startswith("kpi_"))

        fetched = self.db.get_kpi(kpi_id)
        self.assertEqual(fetched["kpi_name"], "Target Revenue")
        self.assertAlmostEqual(fetched["target_value"], 100000.0)

        # Delete
        self.assertTrue(self.db.delete_kpi(kpi_id))
        self.assertIsNone(self.db.get_kpi(kpi_id))

    # -------------------------------------------------------------
    # 3. KPI ENGINE & TIME-BASED PROGRESS TESTS
    # -------------------------------------------------------------
    def test_kpi_calculation_and_variance(self):
        df = pd.DataFrame({"Sales": [100.0, 200.0, 300.0, 400.0]})
        kpi = {
            "id": "kpi_test_sales",
            "kpi_name": "Monthly Sales",
            "metric_column": "Sales",
            "calculation": "SUM",
            "target_value": 1200.0,
            "alert_threshold_pct": 10.0
        }
        # Actual SUM = 1000.0, Target = 1200.0
        snapshot = self.kpi_engine.evaluate_kpi(kpi, df)
        self.assertEqual(snapshot["actual_value"], 1000.0)
        self.assertEqual(snapshot["variance"], -200.0)
        self.assertAlmostEqual(snapshot["achievement_pct"], 83.33, places=1)

    def test_time_based_elapsed_progress_and_performance_gap(self):
        df = pd.DataFrame({"Sales": [300000.0]})
        # 30-day period; current date is day 15 (expected progress = 50%)
        start_d = date(2026, 9, 1)
        end_d = date(2026, 9, 30)
        as_of = date(2026, 9, 16) # 15 days passed out of 29

        kpi = {
            "id": "kpi_time_test",
            "kpi_name": "Monthly Target",
            "metric_column": "Sales",
            "calculation": "SUM",
            "target_value": 1000000.0, # Actual 300k is 30% achievement
            "start_date": start_d.strftime("%Y-%m-%d"),
            "end_date": end_d.strftime("%Y-%m-%d")
        }

        snapshot = self.kpi_engine.evaluate_kpi(kpi, df, as_of_date=as_of)
        self.assertAlmostEqual(snapshot["achievement_pct"], 30.0)
        self.assertAlmostEqual(snapshot["expected_progress_pct"], 51.72, places=1)
        # Performance gap is ~ 30 - 51.72 = -21.72% (Critical!)
        self.assertLess(snapshot["performance_gap"], -20.0)
        self.assertEqual(snapshot["status"], "CRITICAL")

    def test_kpi_status_classifications(self):
        # 1. EXCEEDED
        df_exceeded = pd.DataFrame({"Sales": [1500.0]})
        kpi_exceeded = {"id": "k1", "metric_column": "Sales", "calculation": "SUM", "target_value": 1000.0}
        s1 = self.kpi_engine.evaluate_kpi(kpi_exceeded, df_exceeded)
        self.assertEqual(s1["status"], "EXCEEDED")

        # 2. ON TRACK
        df_track = pd.DataFrame({"Sales": [950.0]})
        kpi_track = {"id": "k2", "metric_column": "Sales", "calculation": "SUM", "target_value": 1000.0, "alert_threshold_pct": 10.0}
        s2 = self.kpi_engine.evaluate_kpi(kpi_track, df_track)
        self.assertEqual(s2["status"], "ON TRACK")

        # 3. AT RISK
        df_risk = pd.DataFrame({"Sales": [750.0]})
        kpi_risk = {"id": "k3", "metric_column": "Sales", "calculation": "SUM", "target_value": 1000.0}
        s3 = self.kpi_engine.evaluate_kpi(kpi_risk, df_risk)
        self.assertEqual(s3["status"], "AT RISK")

    # -------------------------------------------------------------
    # 4. ALERT DECISION & COOLDOWN ANTI-SPAM TESTS
    # -------------------------------------------------------------
    def test_alert_generation_and_cooldown_prevention(self):
        alert_engine = AlertEngine()
        
        critical_snapshot = {
            "kpi_id": "kpi_cooldown_demo",
            "kpi_name": "Revenue Demo",
            "status": "CRITICAL",
            "actual_value": 20000.0,
            "target_value": 100000.0,
            "achievement_pct": 20.0,
            "expected_progress_pct": 60.0,
            "performance_gap": -40.0,
            "variance": -80000.0,
            "recipients": "boss@example.com"
        }

        # 1. First trigger: Should trigger alert and send (mock) email
        decision_1 = alert_engine.evaluate_and_notify(critical_snapshot, cooldown_hours=24)
        self.assertTrue(decision_1["alert_triggered"])
        self.assertEqual(decision_1["severity"], "CRITICAL")
        self.assertTrue(decision_1["email_sent"])
        self.assertFalse(decision_1["cooldown_active"])

        # 2. Immediate second trigger: Should trigger alert logic but suppress email due to active cooldown
        decision_2 = alert_engine.evaluate_and_notify(critical_snapshot, cooldown_hours=24)
        self.assertTrue(decision_2["alert_triggered"])
        self.assertTrue(decision_2["cooldown_active"])
        self.assertFalse(decision_2["email_sent"])
        self.assertIn("Suppressed", decision_2["email_error"])

    # -------------------------------------------------------------
    # 5. EMAIL TEMPLATE TESTS
    # -------------------------------------------------------------
    def test_html_email_template_builder(self):
        payload = {
            "kpi_name": "Quarterly Margin",
            "severity": "CRITICAL",
            "actual_value": 45000.0,
            "target_value": 100000.0,
            "achievement_pct": 45.0,
            "expected_progress_pct": 75.0,
            "performance_gap": -30.0,
            "message": "Performance gap of -30.0% breached critical threshold."
        }
        html = self.email_service.build_html_alert(payload)
        self.assertIn("Quarterly Margin", html)
        self.assertIn("CRITICAL BREACH", html)
        self.assertIn("45,000.00", html)
        self.assertIn("-30.0%", html)

    # -------------------------------------------------------------
    # 6. AI KPI INSIGHTS & INQUIRY TESTS
    # -------------------------------------------------------------
    def test_ai_query_recognizes_kpi_status(self):
        # Save a critical KPI and snapshot in the active db
        from services.db_service import db_service
        kpi_id = db_service.save_kpi({
            "kpi_name": "Test Regional Revenue",
            "metric_column": "Sales",
            "calculation": "SUM",
            "target_value": 500000.0,
            "status": "ACTIVE"
        })
        db_service.save_kpi_snapshot({
            "kpi_id": kpi_id,
            "actual_value": 150000.0,
            "target_value": 500000.0,
            "achievement_pct": 30.0,
            "expected_progress_pct": 70.0,
            "performance_gap": -40.0,
            "status": "CRITICAL"
        })

        test_df = pd.DataFrame({"Sales": [150000.0]})
        result = handle_question("Which KPIs are currently critical?", test_df, profile={"columns": ["Sales"]})
        self.assertIn("answer", result)
        self.assertIsNotNone(result["answer"])

if __name__ == "__main__":
    unittest.main()

