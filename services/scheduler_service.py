import os
import time
import threading
import logging
from typing import Dict, Any, Optional, Callable, List
import pandas as pd
from services.db_service import db_service
from services.kpi_engine import kpi_engine
from services.alert_engine import alert_engine
from services.csv_monitor import csv_monitor

logger = logging.getLogger("SchedulerService")

class SchedulerService:
    """Enterprise Background Monitoring Scheduler with Dynamic CSV Change Detection.
    
    Modular architecture:
    - Automatically detects CSV content modifications on disk (mtime + SHA-256 hash)
    - Re-reads, validates, cleans, and updates DB with zero duplicate records
    - Recalculates all affected active KPIs
    - Evaluates performance gaps, threshold breaches, and status transitions
    - Dispatches alerts while strictly enforcing anti-spam cooldowns
    """

    def __init__(self, interval_seconds: int = 300):
        self.interval_seconds = interval_seconds
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.last_run_time: Optional[str] = None
        self.last_run_summary: Dict[str, Any] = {}
        self.cached_df: Optional[pd.DataFrame] = None
        self.on_data_updated: Optional[Callable[[str, pd.DataFrame, Dict], None]] = None

    def set_active_dataframe(self, df: pd.DataFrame):
        """Sets or updates the current active DataFrame in memory for scheduler checks."""
        self.cached_df = df

    def register_update_callback(self, callback: Callable[[str, pd.DataFrame, Dict], None]):
        """Registers a callback invoked when a monitored CSV is updated on disk."""
        self.on_data_updated = callback

    def check_and_sync_all_csvs(self) -> List[Dict[str, Any]]:
        """Checks all monitored datasets for file modifications and syncs changed datasets."""
        monitored_datasets = db_service.get_monitored_datasets()
        sync_results = []

        for ds in monitored_datasets:
            filepath = ds.get("filepath", "")
            if not filepath or not os.path.exists(filepath):
                continue

            recorded_mtime = ds.get("last_mtime")
            recorded_hash = ds.get("file_hash")

            has_changed, current_mtime, current_hash = csv_monitor.has_file_changed(
                filepath=filepath,
                recorded_mtime=recorded_mtime,
                recorded_hash=recorded_hash
            )

            if has_changed:
                logger.info(f"Detected CSV change in '{filepath}' for dataset {ds['id']}. Re-cleaning and syncing...")
                try:
                    result = csv_monitor.sync_dataset(ds)
                    sync_results.append({
                        "dataset_id": ds["id"],
                        "filepath": filepath,
                        "updated": True,
                        "row_count": result["row_count"],
                        "col_count": result["col_count"],
                        "quality_score": result["quality_score"]
                    })
                    # Update local cache
                    self.cached_df = result["clean_df"]
                    
                    # Notify application listeners (e.g. app session store)
                    if self.on_data_updated:
                        self.on_data_updated(ds["id"], result["clean_df"], result["quality_report"])

                except Exception as e:
                    logger.error(f"Failed to sync modified CSV '{filepath}': {e}")
                    sync_results.append({
                        "dataset_id": ds["id"],
                        "filepath": filepath,
                        "updated": False,
                        "error": str(e)
                    })
        return sync_results

    def run_cycle(self) -> Dict[str, Any]:
        """Executes one full cycle: detects CSV updates, syncs DB, and evaluates KPIs."""
        # -------------------------------------------------------------
        # 1. DYNAMIC CSV CHANGE DETECTION & SYNCHRONIZATION
        # -------------------------------------------------------------
        sync_events = self.check_and_sync_all_csvs()
        csvs_updated = len([s for s in sync_events if s.get("updated")])

        # -------------------------------------------------------------
        # 2. FETCH CURRENT CLEAN DATAFRAME
        # -------------------------------------------------------------
        df = self.cached_df
        if df is None or df.empty:
            latest_dataset = db_service.get_latest_dataset()
            if latest_dataset:
                df = db_service.get_clean_records_df(latest_dataset["id"])
                self.cached_df = df

        if df is None or df.empty:
            return {
                "status": "SKIPPED",
                "message": "No active dataset available for monitoring.",
                "evaluated_kpis": 0,
                "csvs_updated": csvs_updated
            }

        # -------------------------------------------------------------
        # 3. EVALUATE ACTIVE KPIS
        # -------------------------------------------------------------
        active_kpis = db_service.get_kpis(active_only=True)
        if not active_kpis:
            return {
                "status": "SKIPPED",
                "message": "No active KPIs configured.",
                "evaluated_kpis": 0,
                "csvs_updated": csvs_updated
            }

        results = []
        alerts_triggered = 0
        emails_sent = 0

        for kpi in active_kpis:
            try:
                # Recalculate KPI against fresh clean DataFrame
                snapshot = kpi_engine.evaluate_kpi(kpi, df)
                
                # Evaluate alert conditions and anti-spam cooldown
                alert_decision = alert_engine.evaluate_and_notify(snapshot)
                
                if alert_decision.get("alert_triggered"):
                    alerts_triggered += 1
                if alert_decision.get("email_sent"):
                    emails_sent += 1

                results.append({
                    "kpi_id": kpi["id"],
                    "kpi_name": kpi.get("kpi_name"),
                    "status": snapshot.get("status"),
                    "gap": snapshot.get("performance_gap"),
                    "achievement_pct": snapshot.get("achievement_pct"),
                    "alert": alert_decision
                })
            except Exception as e:
                logger.error(f"Error evaluating KPI {kpi.get('id')}: {str(e)}")
                results.append({
                    "kpi_id": kpi.get("id"),
                    "kpi_name": kpi.get("kpi_name"),
                    "error": str(e)
                })

        summary = {
            "status": "COMPLETED",
            "evaluated_kpis": len(results),
            "csvs_updated": csvs_updated,
            "sync_events": sync_events,
            "alerts_triggered": alerts_triggered,
            "emails_sent": emails_sent,
            "results": results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.last_run_time = summary["timestamp"]
        self.last_run_summary = summary
        return summary

    def _loop(self):
        """Internal daemon loop for native thread execution."""
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Scheduler execution cycle failed: {str(e)}")
            
            self._stop_event.wait(self.interval_seconds)

    def start(self, interval_seconds: Optional[int] = None):
        """Starts the background monitoring scheduler."""
        if interval_seconds:
            self.interval_seconds = interval_seconds

        if self.is_running:
            return

        self._stop_event.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="KPIMonitorThread")
        self._thread.start()
        logger.info(f"Background KPI & CSV monitoring scheduler started (interval: {self.interval_seconds}s).")

    def stop(self):
        """Stops the background scheduler."""
        if not self.is_running:
            return
        self._stop_event.set()
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Background KPI & CSV monitoring scheduler stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and metrics of the scheduler."""
        monitored = db_service.get_monitored_datasets()
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "last_run_time": self.last_run_time,
            "last_run_summary": self.last_run_summary,
            "monitored_datasets_count": len(monitored),
            "monitored_files": [d.get("filepath") for d in monitored if d.get("filepath")]
        }

# Singleton instance
scheduler_service = SchedulerService(interval_seconds=300)
