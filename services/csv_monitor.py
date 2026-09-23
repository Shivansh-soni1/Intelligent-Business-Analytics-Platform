import os
import hashlib
from typing import Tuple, Optional, Dict, Any
import pandas as pd

from services.data_loader import process_csv
from services.data_cleaner import data_cleaner
from services.db_service import db_service

class CSVMonitor:
    """Dynamic CSV Change Detection and Automated Re-Processing Engine.
    
    Provides:
    - High-efficiency mtime check ($O(1)$) paired with chunked SHA-256 verification
    - Automated re-validation, sanitization, and deduplication
    - Atomic database update without creating duplicate records
    """

    def __init__(self, db_service_instance=None):
        self._db_service = db_service_instance

    @property
    def db(self):
        if self._db_service is not None:
            return self._db_service
        from services.db_service import db_service
        return db_service

    @staticmethod
    def compute_file_hash(filepath: str) -> str:
        """Calculates SHA-256 hash of a file using 64KB stream chunks."""
        if not filepath or not os.path.exists(filepath):
            return ""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception:
            return ""

    @staticmethod
    def get_file_mtime(filepath: str) -> float:
        """Returns the file modification epoch timestamp."""
        if not filepath or not os.path.exists(filepath):
            return 0.0
        try:
            return float(os.path.getmtime(filepath))
        except Exception:
            return 0.0

    def has_file_changed(
        self,
        filepath: str,
        recorded_mtime: Optional[float] = None,
        recorded_hash: Optional[str] = None
    ) -> Tuple[bool, float, str]:
        """Checks if a CSV file on disk has changed in content.
        
        Returns: (has_changed, current_mtime, current_hash)
        """
        if not filepath or not os.path.exists(filepath):
            return False, 0.0, ""

        current_mtime = self.get_file_mtime(filepath)
        recorded_mtime = float(recorded_mtime or 0.0)
        recorded_hash = str(recorded_hash or "")

        # Fast path: If mtime has not changed at all, content has definitely not changed
        if recorded_mtime > 0 and abs(current_mtime - recorded_mtime) < 0.001:
            return False, recorded_mtime, recorded_hash

        # Mtime changed or recorded_mtime was 0 -> compute SHA-256 content hash
        current_hash = self.compute_file_hash(filepath)
        if not current_hash:
            return False, current_mtime, recorded_hash

        # If hash changed, content is genuinely modified
        if current_hash != recorded_hash:
            return True, current_mtime, current_hash

        # Mtime changed (e.g. file touched) but content is identical
        return False, current_mtime, recorded_hash

    def sync_dataset(self, dataset_record: Dict[str, Any]) -> Dict[str, Any]:
        """Re-reads, validates, cleans, and updates database for an updated CSV.
        Guarantees zero duplicate records.
        """
        dataset_id = dataset_record["id"]
        filepath = dataset_record.get("filepath", "")

        if not filepath or not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV file not found on disk at: '{filepath}'")

        # 1. Re-read raw CSV with dynamic schema detection
        raw_df, summary = process_csv(filepath)
        profile = summary.get("profile", {})

        # 2. Automated Validation & Cleaning Engine
        clean_df, quality_report = data_cleaner.validate_and_clean(raw_df, profile)

        # 3. Compute new file metadata
        new_mtime = self.get_file_mtime(filepath)
        new_hash = self.compute_file_hash(filepath)

        # 4. Atomically update dataset and replace clean records (Zero Duplicates)
        self.db.update_dataset_sync(
            dataset_id=dataset_id,
            file_hash=new_hash,
            last_mtime=new_mtime,
            row_count=len(clean_df),
            col_count=len(clean_df.columns),
            quality_score=quality_report.get("quality_score", 100.0),
            quality_report=quality_report,
            clean_df=clean_df
        )

        return {
            "dataset_id": dataset_id,
            "filepath": filepath,
            "row_count": len(clean_df),
            "col_count": len(clean_df.columns),
            "quality_score": quality_report.get("quality_score", 100.0),
            "quality_report": quality_report,
            "clean_df": clean_df,
            "summary": summary,
            "new_hash": new_hash,
            "new_mtime": new_mtime
        }

# Singleton instance
csv_monitor = CSVMonitor()

