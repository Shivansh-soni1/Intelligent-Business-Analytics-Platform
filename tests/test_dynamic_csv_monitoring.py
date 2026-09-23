import unittest
import os
import tempfile
import time
import pandas as pd
from datetime import datetime, date

from services.csv_monitor import CSVMonitor
from services.db_service import DatabaseService
from services.kpi_engine import KPIEngine
from services.alert_engine import AlertEngine
from services.email_service import EmailService
from services.scheduler_service import SchedulerService

class TestDynamicCSVMonitoring(unittest.TestCase):
    """Automated test suite verifying dynamic CSV change detection, automated re-cleaning,
    KPI recalculation, and alert cooldowns.
    """

    def setUp(self):
        # Create isolated temporary directory for test CSVs and database
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "test_analytics.db")
        self.db = DatabaseService(db_path=self.db_path)
        self.csv_monitor = CSVMonitor(db_service_instance=self.db)
        self.kpi_engine = KPIEngine()
        self.alert_engine = AlertEngine()
        self.email_service = EmailService()
        self.email_service.email_enabled = False # Mock mode

    def tearDown(self):
        try:
            self.test_dir.cleanup()
        except Exception:
            pass

    def _create_temp_csv(self, filename: str, df: pd.DataFrame) -> str:
        filepath = os.path.join(self.test_dir.name, filename)
        df.to_csv(filepath, index=False)
        return filepath

    # -------------------------------------------------------------
    # TEST 1: CSV UPDATED WITH NEW ROWS
    # -------------------------------------------------------------
    def test_csv_updated_with_new_rows(self):
        # Initial CSV with 3 rows
        initial_df = pd.DataFrame({
            "Order_ID": [101, 102, 103],
            "Sales": [100.0, 200.0, 300.0],
            "Order_Date": ["2026-11-01", "2026-11-02", "2026-11-03"]
        })
        filepath = self._create_temp_csv("test_orders.csv", initial_df)
        
        # Save initial dataset
        dataset_id = "ds_new_rows"
        initial_hash = self.csv_monitor.compute_file_hash(filepath)
        initial_mtime = self.csv_monitor.get_file_mtime(filepath)
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="test_orders.csv",
            filename="test_orders.csv",
            row_count=3,
            col_count=3,
            quality_score=100.0,
            quality_report={"quality_score": 100.0},
            schema_profile={"numeric_cols": ["Sales"], "date_cols": ["Order_Date"]},
            clean_df=initial_df,
            filepath=filepath,
            file_hash=initial_hash,
            last_mtime=initial_mtime,
            auto_monitor=1
        )

        # Set up a KPI for Sales
        kpi_id = self.db.save_kpi({
            "dataset_id": dataset_id,
            "kpi_name": "Quarterly Sales Target",
            "metric_column": "Sales",
            "calculation": "SUM",
            "target_value": 1000.0
        })
        snap1 = self.kpi_engine.evaluate_kpi(self.db.get_kpi(kpi_id), initial_df)
        self.assertEqual(snap1["actual_value"], 600.0)

        # Append 2 new rows to CSV
        time.sleep(0.05) # Ensure mtime changes
        updated_df = pd.DataFrame({
            "Order_ID": [101, 102, 103, 104, 105],
            "Sales": [100.0, 200.0, 300.0, 250.0, 250.0],
            "Order_Date": ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
        })
        updated_df.to_csv(filepath, index=False)

        # Change detection
        has_changed, new_mtime, new_hash = self.csv_monitor.has_file_changed(filepath, initial_mtime, initial_hash)
        self.assertTrue(has_changed)
        self.assertNotEqual(new_hash, initial_hash)

        # Sync dataset
        ds_record = self.db.get_dataset(dataset_id)
        sync_result = self.csv_monitor.sync_dataset(ds_record)
        self.assertEqual(sync_result["row_count"], 5)

        # Recalculate KPI with synced data
        snap2 = self.kpi_engine.evaluate_kpi(self.db.get_kpi(kpi_id), sync_result["clean_df"])
        self.assertEqual(snap2["actual_value"], 1100.0) # 600 + 250 + 250
        self.assertEqual(snap2["status"], "EXCEEDED")

    # -------------------------------------------------------------
    # TEST 2: CSV UPDATED WITH MODIFIED EXISTING ROWS
    # -------------------------------------------------------------
    def test_csv_updated_with_modified_existing_rows(self):
        initial_df = pd.DataFrame({
            "Order_ID": [1, 2],
            "Amount": [50.0, 50.0]
        })
        filepath = self._create_temp_csv("modified.csv", initial_df)
        initial_hash = self.csv_monitor.compute_file_hash(filepath)
        initial_mtime = self.csv_monitor.get_file_mtime(filepath)

        dataset_id = "ds_modified"
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="modified.csv",
            filename="modified.csv",
            row_count=2,
            col_count=2,
            quality_score=100.0,
            quality_report={},
            schema_profile={"numeric_cols": ["Amount"]},
            clean_df=initial_df,
            filepath=filepath,
            file_hash=initial_hash,
            last_mtime=initial_mtime,
            auto_monitor=1
        )

        # Modify values without changing row count
        time.sleep(0.05)
        modified_df = pd.DataFrame({
            "Order_ID": [1, 2],
            "Amount": [500.0, 500.0] # 10x increase
        })
        modified_df.to_csv(filepath, index=False)

        has_changed, _, new_hash = self.csv_monitor.has_file_changed(filepath, initial_mtime, initial_hash)
        self.assertTrue(has_changed)
        self.assertNotEqual(new_hash, initial_hash)

        # Sync and verify DB records
        sync_res = self.csv_monitor.sync_dataset(self.db.get_dataset(dataset_id))
        reconstructed = self.db.get_clean_records_df(dataset_id)
        self.assertEqual(float(reconstructed["Amount"].sum()), 1000.0)

    # -------------------------------------------------------------
    # TEST 3: CSV UNCHANGED
    # -------------------------------------------------------------
    def test_csv_unchanged_skips_processing(self):
        df = pd.DataFrame({"X": [1, 2, 3]})
        filepath = self._create_temp_csv("unchanged.csv", df)
        file_hash = self.csv_monitor.compute_file_hash(filepath)
        file_mtime = self.csv_monitor.get_file_mtime(filepath)

        has_changed, mtime, h = self.csv_monitor.has_file_changed(filepath, file_mtime, file_hash)
        self.assertFalse(has_changed)
        self.assertEqual(h, file_hash)

    # -------------------------------------------------------------
    # TEST 4: DUPLICATE ROWS IN UPDATED FILE
    # -------------------------------------------------------------
    def test_duplicate_rows_in_update_cleaned_without_db_duplicates(self):
        initial_df = pd.DataFrame({"ID": [1, 2], "Metric": [10.0, 20.0]})
        filepath = self._create_temp_csv("dups.csv", initial_df)
        dataset_id = "ds_dups"
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="dups.csv",
            filename="dups.csv",
            row_count=2,
            col_count=2,
            quality_score=100.0,
            quality_report={},
            schema_profile={"numeric_cols": ["Metric"]},
            clean_df=initial_df,
            filepath=filepath,
            file_hash=self.csv_monitor.compute_file_hash(filepath),
            last_mtime=self.csv_monitor.get_file_mtime(filepath),
            auto_monitor=1
        )

        # Update CSV with duplicate rows
        time.sleep(0.05)
        updated_with_dups = pd.DataFrame({
            "ID": [1, 2, 3, 3, 3], # 3 duplicate rows for ID 3
            "Metric": [10.0, 20.0, 30.0, 30.0, 30.0]
        })
        updated_with_dups.to_csv(filepath, index=False)

        sync_result = self.csv_monitor.sync_dataset(self.db.get_dataset(dataset_id))
        # Should drop exact duplicates: only 3 unique rows remain
        self.assertEqual(sync_result["row_count"], 3)
        self.assertEqual(sync_result["quality_report"]["duplicates_removed"], 2)

        # Verify clean_records in DB has exactly 3 rows
        db_records = self.db.get_clean_records_df(dataset_id)
        self.assertEqual(len(db_records), 3)

    # -------------------------------------------------------------
    # TEST 5: KPI PERIOD REACHED AFTER NEW DATA ARRIVES
    # -------------------------------------------------------------
    def test_kpi_period_reached_after_new_data_arrives(self):
        # Initial dataset only has December 2026 data
        dec_df = pd.DataFrame({
            "Order_Date": ["2026-12-10", "2026-12-20"],
            "Revenue": [5000.0, 5000.0]
        })
        filepath = self._create_temp_csv("period_test.csv", dec_df)
        dataset_id = "ds_period"
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="period_test.csv",
            filename="period_test.csv",
            row_count=2,
            col_count=2,
            quality_score=100.0,
            quality_report={},
            schema_profile={"numeric_cols": ["Revenue"], "date_cols": ["Order_Date"]},
            clean_df=dec_df,
            filepath=filepath,
            file_hash=self.csv_monitor.compute_file_hash(filepath),
            last_mtime=self.csv_monitor.get_file_mtime(filepath),
            auto_monitor=1
        )

        # Create KPI specifically for January 2027: 2027-01-01 to 2027-01-31
        kpi_jan = {
            "id": "kpi_jan_target",
            "dataset_id": dataset_id,
            "kpi_name": "January 2027 Revenue",
            "metric_column": "Revenue",
            "calculation": "SUM",
            "target_value": 20000.0,
            "start_date": "2027-01-01",
            "end_date": "2027-01-31"
        }
        self.db.save_kpi(kpi_jan)

        # Initial evaluation: Actual is 0.0 because January 2027 has not occurred in data
        init_snap = self.kpi_engine.evaluate_kpi(self.db.get_kpi("kpi_jan_target"), dec_df)
        self.assertEqual(init_snap["actual_value"], 0.0)

        # Later, CSV is updated with January 2027 data
        time.sleep(0.05)
        expanded_df = pd.DataFrame({
            "Order_Date": ["2026-12-10", "2026-12-20", "2027-01-05", "2027-01-15"],
            "Revenue": [5000.0, 5000.0, 12000.0, 8000.0]
        })
        expanded_df.to_csv(filepath, index=False)

        # Sync dataset
        sync_res = self.csv_monitor.sync_dataset(self.db.get_dataset(dataset_id))
        
        # Recalculate KPI for Jan 2027
        new_snap = self.kpi_engine.evaluate_kpi(self.db.get_kpi("kpi_jan_target"), sync_res["clean_df"])
        # Only January rows (12000 + 8000 = 20000) are counted!
        self.assertEqual(new_snap["actual_value"], 20000.0)
        self.assertEqual(new_snap["achievement_pct"], 100.0)
        self.assertEqual(new_snap["status"], "EXCEEDED")

    # -------------------------------------------------------------
    # TEST 6: KPI RECALCULATION ACCURACY
    # -------------------------------------------------------------
    def test_kpi_recalculation_accuracy(self):
        df = pd.DataFrame({"Units": [10.0, 20.0, 30.0]})
        kpi = {
            "id": "k_acc",
            "kpi_name": "Units Goal",
            "metric_column": "Units",
            "calculation": "SUM",
            "target_value": 100.0
        }
        snap = self.kpi_engine.evaluate_kpi(kpi, df)
        self.assertEqual(snap["actual_value"], 60.0)
        self.assertEqual(snap["variance"], -40.0)
        self.assertEqual(snap["achievement_pct"], 60.0)

    # -------------------------------------------------------------
    # TEST 7: ALERT TRIGGERED AFTER CSV UPDATE
    # -------------------------------------------------------------
    def test_alert_triggered_after_csv_update(self):
        # Initial high-margin data
        df1 = pd.DataFrame({"Profit": [50000.0]})
        filepath = self._create_temp_csv("alert_test.csv", df1)
        dataset_id = "ds_alert"
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="alert_test.csv",
            filename="alert_test.csv",
            row_count=1,
            col_count=1,
            quality_score=100.0,
            quality_report={},
            schema_profile={"numeric_cols": ["Profit"]},
            clean_df=df1,
            filepath=filepath,
            file_hash=self.csv_monitor.compute_file_hash(filepath),
            last_mtime=self.csv_monitor.get_file_mtime(filepath),
            auto_monitor=1
        )

        kpi_id = self.db.save_kpi({
            "dataset_id": dataset_id,
            "kpi_name": "Net Profit Margin",
            "metric_column": "Profit",
            "calculation": "SUM",
            "target_value": 100000.0,
            "recipients": "finance@example.com"
        })

        # Update CSV with negative profit transaction, dropping total profit to 10k
        time.sleep(0.05)
        df2 = pd.DataFrame({"Profit": [50000.0, -40000.0]})
        df2.to_csv(filepath, index=False)

        sync_res = self.csv_monitor.sync_dataset(self.db.get_dataset(dataset_id))
        snap = self.kpi_engine.evaluate_kpi(self.db.get_kpi(kpi_id), sync_res["clean_df"])
        self.assertEqual(snap["actual_value"], 10000.0)
        self.assertEqual(snap["status"], "CRITICAL") # 10% achievement < 70%

        # Alert Engine Evaluation
        alert_res = self.alert_engine.evaluate_and_notify(snap)
        self.assertTrue(alert_res["alert_triggered"])
        self.assertEqual(alert_res["severity"], "CRITICAL")
        self.assertTrue(alert_res["email_sent"]) # Mock email sent

    # -------------------------------------------------------------
    # TEST 8: ALERT COOLDOWN PREVENTING DUPLICATE EMAILS
    # -------------------------------------------------------------
    def test_alert_cooldown_prevents_duplicate_emails_after_sync(self):
        snapshot = {
            "kpi_id": "kpi_cd_test",
            "kpi_name": "Revenue Guardrail",
            "status": "CRITICAL",
            "actual_value": 5000.0,
            "target_value": 50000.0,
            "achievement_pct": 10.0,
            "performance_gap": -90.0,
            "recipients": "manager@example.com"
        }

        # First alert: dispatches email
        res1 = self.alert_engine.evaluate_and_notify(snapshot, cooldown_hours=24)
        self.assertTrue(res1["alert_triggered"])
        self.assertTrue(res1["email_sent"])
        self.assertFalse(res1["cooldown_active"])

        # Second alert immediately after: suppressed by cooldown
        res2 = self.alert_engine.evaluate_and_notify(snapshot, cooldown_hours=24)
        self.assertTrue(res2["alert_triggered"])
        self.assertTrue(res2["cooldown_active"])
        self.assertFalse(res2["email_sent"])

    # -------------------------------------------------------------
    # TEST 9: MULTIPLE KPIS AFFECTED BY SAME CSV UPDATE
    # -------------------------------------------------------------
    def test_multiple_kpis_affected_by_same_csv_update(self):
        initial_df = pd.DataFrame({
            "Sales": [100.0],
            "Units": [5.0]
        })
        filepath = self._create_temp_csv("multi_kpi.csv", initial_df)
        dataset_id = "ds_multi"
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="multi_kpi.csv",
            filename="multi_kpi.csv",
            row_count=1,
            col_count=2,
            quality_score=100.0,
            quality_report={},
            schema_profile={"numeric_cols": ["Sales", "Units"]},
            clean_df=initial_df,
            filepath=filepath,
            file_hash=self.csv_monitor.compute_file_hash(filepath),
            last_mtime=self.csv_monitor.get_file_mtime(filepath),
            auto_monitor=1
        )

        k1 = self.db.save_kpi({"dataset_id": dataset_id, "kpi_name": "K1", "metric_column": "Sales", "calculation": "SUM", "target_value": 500.0})
        k2 = self.db.save_kpi({"dataset_id": dataset_id, "kpi_name": "K2", "metric_column": "Units", "calculation": "SUM", "target_value": 20.0})

        # Update CSV
        time.sleep(0.05)
        updated_df = pd.DataFrame({
            "Sales": [100.0, 400.0],
            "Units": [5.0, 15.0]
        })
        updated_df.to_csv(filepath, index=False)

        sync_res = self.csv_monitor.sync_dataset(self.db.get_dataset(dataset_id))
        
        # Evaluate both KPIs against new clean data
        s1 = self.kpi_engine.evaluate_kpi(self.db.get_kpi(k1), sync_res["clean_df"])
        s2 = self.kpi_engine.evaluate_kpi(self.db.get_kpi(k2), sync_res["clean_df"])

        self.assertEqual(s1["actual_value"], 500.0)
        self.assertEqual(s1["status"], "EXCEEDED")
        self.assertEqual(s2["actual_value"], 20.0)
        self.assertEqual(s2["status"], "EXCEEDED")

    # -------------------------------------------------------------
    # TEST 10: DATASET-AGNOSTIC SCHEMA
    # -------------------------------------------------------------
    def test_dataset_agnostic_columns(self):
        # Healthcare/Hospital domain columns
        df = pd.DataFrame({
            "Patient_ID": ["P1", "P2"],
            "Wait_Time_Minutes": [45.0, 15.0],
            "Clinic_Room": [101, 102]
        })
        filepath = self._create_temp_csv("healthcare.csv", df)
        dataset_id = "ds_health"
        self.db.save_dataset(
            dataset_id=dataset_id,
            name="healthcare.csv",
            filename="healthcare.csv",
            row_count=2,
            col_count=3,
            quality_score=100.0,
            quality_report={},
            schema_profile={"numeric_cols": ["Wait_Time_Minutes"]},
            clean_df=df,
            filepath=filepath,
            file_hash=self.csv_monitor.compute_file_hash(filepath),
            last_mtime=self.csv_monitor.get_file_mtime(filepath),
            auto_monitor=1
        )

        kpi_health = {
            "dataset_id": dataset_id,
            "kpi_name": "Average Wait Time",
            "metric_column": "Wait_Time_Minutes",
            "calculation": "AVERAGE",
            "target_value": 30.0
        }
        k_id = self.db.save_kpi(kpi_health)
        snap = self.kpi_engine.evaluate_kpi(self.db.get_kpi(k_id), df)
        self.assertEqual(snap["actual_value"], 30.0)
        self.assertEqual(snap["status"], "EXCEEDED")

if __name__ == "__main__":
    unittest.main()

