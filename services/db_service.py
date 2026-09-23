import os
import json
import sqlite3
import uuid
import pandas as pd
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analytics_platform.db")

class DatabaseService:
    """Flexible, Dataset-Agnostic SQLite Database Layer.
    
    Supports:
    - Dynamic dataset storage (metadata + JSON records)
    - KPI & Target configurations (with custom formulas and date periods)
    - Historical performance snapshots (actual vs target, expected progress, gap)
    - Alert audit trail with deduplication / cooldown checks
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initializes database tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Datasets Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    row_count INTEGER,
                    col_count INTEGER,
                    quality_score REAL,
                    quality_report_json TEXT,
                    schema_profile_json TEXT,
                    filepath TEXT,
                    file_hash TEXT,
                    last_mtime REAL,
                    auto_monitor INTEGER DEFAULT 1
                )
            """)

            # Safe column migration for existing databases
            for col_name, col_type in [
                ("filepath", "TEXT"),
                ("file_hash", "TEXT"),
                ("last_mtime", "REAL"),
                ("auto_monitor", "INTEGER DEFAULT 1")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE datasets ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # 2. Dynamic Clean Records Table (JSON per row for flexible schemas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clean_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    row_index INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_dataset ON clean_records(dataset_id)")

            # 3. KPI Definitions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kpi_definitions (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    kpi_name TEXT NOT NULL,
                    metric_column TEXT NOT NULL,
                    calculation TEXT NOT NULL,
                    target_value REAL NOT NULL,
                    period TEXT DEFAULT 'Monthly',
                    start_date TEXT,
                    end_date TEXT,
                    alert_threshold_pct REAL DEFAULT 10.0,
                    recipients TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE SET NULL
                )
            """)

            # 4. KPI Snapshots / Historical Runs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kpi_snapshots (
                    id TEXT PRIMARY KEY,
                    kpi_id TEXT NOT NULL,
                    snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actual_value REAL,
                    target_value REAL,
                    variance REAL,
                    variance_pct REAL,
                    achievement_pct REAL,
                    expected_progress_pct REAL,
                    actual_progress_pct REAL,
                    performance_gap REAL,
                    status TEXT,
                    FOREIGN KEY (kpi_id) REFERENCES kpi_definitions(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_kpi ON kpi_snapshots(kpi_id)")

            # 5. Alert History Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_history (
                    id TEXT PRIMARY KEY,
                    kpi_id TEXT NOT NULL,
                    kpi_name TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    actual_value REAL,
                    target_value REAL,
                    variance REAL,
                    performance_gap REAL,
                    message TEXT,
                    recipients TEXT,
                    email_sent INTEGER DEFAULT 0,
                    email_error TEXT,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (kpi_id) REFERENCES kpi_definitions(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_kpi ON alert_history(kpi_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON alert_history(triggered_at)")
            
            conn.commit()

    # -------------------------------------------------------------
    # DATASET OPERATIONS
    # -------------------------------------------------------------
    def save_dataset(
        self,
        dataset_id: str,
        name: str,
        filename: str,
        row_count: int,
        col_count: int,
        quality_score: float,
        quality_report: Dict[str, Any],
        schema_profile: Dict[str, Any],
        clean_df: Optional[pd.DataFrame] = None,
        filepath: Optional[str] = None,
        file_hash: Optional[str] = None,
        last_mtime: Optional[float] = None,
        auto_monitor: int = 1
    ) -> str:
        """Stores dataset metadata and optional cleaned records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO datasets 
                (id, name, filename, uploaded_at, row_count, col_count, quality_score, quality_report_json, schema_profile_json, filepath, file_hash, last_mtime, auto_monitor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dataset_id,
                name,
                filename,
                datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                row_count,
                col_count,
                quality_score,
                json.dumps(quality_report),
                json.dumps(schema_profile),
                filepath or "",
                file_hash or "",
                float(last_mtime or 0.0),
                int(auto_monitor)
            ))

            if clean_df is not None and not clean_df.empty:
                # Remove previous records for this dataset
                cursor.execute("DELETE FROM clean_records WHERE dataset_id = ?", (dataset_id,))
                
                # Bulk insert records in JSON
                records = clean_df.to_dict(orient='records')
                insert_batch = [
                    (dataset_id, idx, json.dumps(rec, default=str))
                    for idx, rec in enumerate(records)
                ]
                cursor.executemany("""
                    INSERT INTO clean_records (dataset_id, row_index, record_json)
                    VALUES (?, ?, ?)
                """, insert_batch)

            conn.commit()
        return dataset_id

    def update_dataset_sync(
        self,
        dataset_id: str,
        file_hash: str,
        last_mtime: float,
        row_count: int,
        col_count: int,
        quality_score: float,
        quality_report: Dict[str, Any],
        clean_df: Optional[pd.DataFrame] = None
    ) -> bool:
        """Atomically updates dataset metadata and cleanly replaces clean_records on CSV updates (Zero Duplicates)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE datasets
                SET file_hash = ?, last_mtime = ?, row_count = ?, col_count = ?,
                    quality_score = ?, quality_report_json = ?
                WHERE id = ?
            """, (
                file_hash,
                float(last_mtime),
                row_count,
                col_count,
                quality_score,
                json.dumps(quality_report),
                dataset_id
            ))

            if clean_df is not None and not clean_df.empty:
                # Remove previous records for this dataset to avoid duplicate rows
                cursor.execute("DELETE FROM clean_records WHERE dataset_id = ?", (dataset_id,))
                
                records = clean_df.to_dict(orient='records')
                insert_batch = [
                    (dataset_id, idx, json.dumps(rec, default=str))
                    for idx, rec in enumerate(records)
                ]
                cursor.executemany("""
                    INSERT INTO clean_records (dataset_id, row_index, record_json)
                    VALUES (?, ?, ?)
                """, insert_batch)

            conn.commit()
            return True

    def get_monitored_datasets(self) -> List[Dict[str, Any]]:
        """Retrieves all datasets configured for auto-monitoring that have an existing file path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM datasets 
                WHERE auto_monitor = 1 AND filepath IS NOT NULL AND filepath != ''
                ORDER BY uploaded_at DESC
            """)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["quality_report"] = json.loads(item.get("quality_report_json") or "{}")
                item["schema_profile"] = json.loads(item.get("schema_profile_json") or "{}")
                results.append(item)
            return results

    def set_dataset_auto_monitor(self, dataset_id: str, enabled: bool) -> bool:
        """Enables or disables auto-monitoring for a specific dataset."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE datasets SET auto_monitor = ? WHERE id = ?", (1 if enabled else 0, dataset_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_latest_dataset(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recently uploaded dataset metadata."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets ORDER BY uploaded_at DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["quality_report"] = json.loads(res.get("quality_report_json") or "{}")
            res["schema_profile"] = json.loads(res.get("schema_profile_json") or "{}")
            return res

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves dataset metadata by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["quality_report"] = json.loads(res.get("quality_report_json") or "{}")
            res["schema_profile"] = json.loads(res.get("schema_profile_json") or "{}")
            return res

    def get_clean_records_df(self, dataset_id: str) -> Optional[pd.DataFrame]:
        """Reconstructs a clean pandas DataFrame from stored JSON records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT record_json FROM clean_records WHERE dataset_id = ? ORDER BY row_index ASC", (dataset_id,))
            rows = cursor.fetchall()
            if not rows:
                return None
            data = [json.loads(r["record_json"]) for r in rows]
            return pd.DataFrame(data)

    # -------------------------------------------------------------
    # KPI / TARGET DEFINITION OPERATIONS
    # -------------------------------------------------------------
    def save_kpi(self, kpi_data: Dict[str, Any]) -> str:
        """Inserts or updates a KPI target definition."""
        kpi_id = kpi_data.get("id") or f"kpi_{uuid.uuid4().hex[:8]}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO kpi_definitions 
                (id, dataset_id, kpi_name, metric_column, calculation, target_value, period, start_date, end_date, alert_threshold_pct, recipients, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kpi_id,
                kpi_data.get("dataset_id"),
                kpi_data["kpi_name"],
                kpi_data["metric_column"],
                kpi_data.get("calculation", "SUM").upper(),
                float(kpi_data["target_value"]),
                kpi_data.get("period", "Monthly"),
                kpi_data.get("start_date"),
                kpi_data.get("end_date"),
                float(kpi_data.get("alert_threshold_pct", 10.0)),
                kpi_data.get("recipients", ""),
                kpi_data.get("status", "ACTIVE")
            ))
            conn.commit()
        return kpi_id

    def get_kpis(self, dataset_id: Optional[str] = None, active_only: bool = False) -> List[Dict[str, Any]]:
        """Retrieves list of configured KPIs with their latest snapshot status."""
        query = """
            SELECT k.*, 
                   s.actual_value, s.achievement_pct, s.expected_progress_pct, 
                   s.actual_progress_pct, s.performance_gap, s.status as latest_status,
                   s.snapshot_time as last_evaluated_at
            FROM kpi_definitions k
            LEFT JOIN (
                SELECT *, ROW_NUMBER() OVER(PARTITION BY kpi_id ORDER BY snapshot_time DESC) as rn
                FROM kpi_snapshots
            ) s ON k.id = s.kpi_id AND s.rn = 1
            WHERE 1=1
        """
        params = []
        if dataset_id:
            query += " AND (k.dataset_id = ? OR k.dataset_id IS NULL)"
            params.append(dataset_id)
        if active_only:
            query += " AND k.status = 'ACTIVE'"

        query += " ORDER BY k.created_at DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_kpi(self, kpi_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single KPI by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM kpi_definitions WHERE id = ?", (kpi_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_kpi(self, kpi_id: str) -> bool:
        """Deletes a KPI and associated snapshots/alerts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM kpi_definitions WHERE id = ?", (kpi_id,))
            cursor.execute("DELETE FROM kpi_snapshots WHERE kpi_id = ?", (kpi_id,))
            cursor.execute("DELETE FROM alert_history WHERE kpi_id = ?", (kpi_id,))
            conn.commit()
            return cursor.rowcount > 0

    # -------------------------------------------------------------
    # KPI SNAPSHOT OPERATIONS
    # -------------------------------------------------------------
    def save_kpi_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """Records an evaluation snapshot for a KPI."""
        snapshot_id = snapshot.get("id") or f"snp_{uuid.uuid4().hex[:8]}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO kpi_snapshots
                (id, kpi_id, snapshot_time, actual_value, target_value, variance, variance_pct, achievement_pct, expected_progress_pct, actual_progress_pct, performance_gap, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_id,
                snapshot["kpi_id"],
                datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                snapshot.get("actual_value"),
                snapshot.get("target_value"),
                snapshot.get("variance"),
                snapshot.get("variance_pct"),
                snapshot.get("achievement_pct"),
                snapshot.get("expected_progress_pct"),
                snapshot.get("actual_progress_pct"),
                snapshot.get("performance_gap"),
                snapshot.get("status")
            ))
            conn.commit()
        return snapshot_id

    def get_kpi_snapshots(self, kpi_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieves historical snapshots for a specific KPI."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM kpi_snapshots 
                WHERE kpi_id = ? 
                ORDER BY snapshot_time DESC 
                LIMIT ?
            """, (kpi_id, limit))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # ALERT HISTORY & DEDUPLICATION / COOLDOWN
    # -------------------------------------------------------------
    def save_alert(self, alert_data: Dict[str, Any]) -> str:
        """Records a triggered alert."""
        alert_id = alert_data.get("id") or f"alt_{uuid.uuid4().hex[:8]}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alert_history
                (id, kpi_id, kpi_name, alert_type, severity, actual_value, target_value, variance, performance_gap, message, recipients, email_sent, email_error, triggered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert_id,
                alert_data["kpi_id"],
                alert_data["kpi_name"],
                alert_data["alert_type"],
                alert_data["severity"],
                alert_data.get("actual_value"),
                alert_data.get("target_value"),
                alert_data.get("variance"),
                alert_data.get("performance_gap"),
                alert_data.get("message"),
                alert_data.get("recipients"),
                1 if alert_data.get("email_sent") else 0,
                alert_data.get("email_error"),
                datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()
        return alert_id

    def is_alert_on_cooldown(self, kpi_id: str, alert_type: str, severity: str, cooldown_hours: int = 24) -> bool:
        """Checks if an identical alert was already sent within the cooldown window."""
        cutoff = (datetime.utcnow() - timedelta(hours=cooldown_hours)).strftime('%Y-%m-%d %H:%M:%S')
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM alert_history
                WHERE kpi_id = ? AND alert_type = ? AND severity = ? AND triggered_at >= ?
            """, (kpi_id, alert_type, severity, cutoff))
            row = cursor.fetchone()
            return row["cnt"] > 0 if row else False

    def get_alert_history(
        self,
        limit: int = 100,
        severity: Optional[str] = None,
        kpi_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves historical alerts with optional filters."""
        query = "SELECT * FROM alert_history WHERE 1=1"
        params = []
        if severity and severity.upper() != "ALL":
            query += " AND severity = ?"
            params.append(severity.upper())
        if kpi_id:
            query += " AND kpi_id = ?"
            params.append(kpi_id)
        
        query += " ORDER BY triggered_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # DASHBOARD AGGREGATED SUMMARY
    # -------------------------------------------------------------
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Calculates aggregated metrics for the dedicated KPI Dashboard."""
        kpis = self.get_kpis()
        total_kpis = len(kpis)
        on_track = sum(1 for k in kpis if k.get("latest_status") == "ON TRACK")
        at_risk = sum(1 for k in kpis if k.get("latest_status") == "AT RISK")
        critical = sum(1 for k in kpis if k.get("latest_status") == "CRITICAL")
        exceeded = sum(1 for k in kpis if k.get("latest_status") == "EXCEEDED")
        unmonitored = sum(1 for k in kpis if not k.get("latest_status"))

        alerts = self.get_alert_history(limit=5)

        return {
            "total_kpis": total_kpis,
            "on_track": on_track,
            "at_risk": at_risk,
            "critical": critical,
            "exceeded": exceeded,
            "unmonitored": unmonitored,
            "recent_alerts": alerts,
            "kpis": kpis
        }

# Singleton instance
db_service = DatabaseService()

