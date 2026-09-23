import os
import uuid
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from services.data_loader import process_csv, allowed_file
from services.query_processor import handle_question, reset_session
from services.data_cleaner import data_cleaner
from services.db_service import db_service
from services.kpi_engine import kpi_engine
from services.alert_engine import alert_engine
from services.scheduler_service import scheduler_service
from services.csv_monitor import csv_monitor

app = Flask(__name__, template_folder='templates')
CORS(app)

UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Active Session Storage
SESSION_STORE = {
    "df": None,
    "profile": None,
    "quality_report": None,
    "active_dataset_id": None
}

# Auto-update session store when scheduler detects CSV modification
def on_csv_sync_callback(dataset_id, clean_df, quality_report):
    if SESSION_STORE.get("active_dataset_id") in (dataset_id, None):
        SESSION_STORE["df"] = clean_df
        SESSION_STORE["quality_report"] = quality_report
scheduler_service.register_update_callback(on_csv_sync_callback)

@app.route('/')
def index():
    df = SESSION_STORE.get("df")
    profile = SESSION_STORE.get("profile") or {}
    quality_report = SESSION_STORE.get("quality_report") or {}
    
    summary_data = {
        "row_count": len(df) if df is not None else 0,
        "col_count": len(df.columns) if df is not None else 0,
        "profile": profile,
        "quality_report": quality_report,
        "suggested_questions": profile.get("suggested_questions", [])
    }
    return render_template('index.html', summary=summary_data)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    session_id = request.form.get("session_id", "default_session")

    if file and allowed_file(file.filename):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        
        try:
            # 1. Process and classify dynamic schema
            raw_df, summary = process_csv(filepath)
            profile = summary.get("profile", {})

            # 2. Automated Validation & Cleaning Engine
            clean_df, quality_report = data_cleaner.validate_and_clean(raw_df, profile)
            
            # 3. Store clean data and quality audit in SQLite DB
            dataset_id = str(uuid.uuid4())[:8]
            initial_hash = csv_monitor.compute_file_hash(filepath)
            initial_mtime = csv_monitor.get_file_mtime(filepath)

            db_service.save_dataset(
                dataset_id=dataset_id,
                name=file.filename,
                filename=file.filename,
                row_count=len(clean_df),
                col_count=len(clean_df.columns),
                quality_score=quality_report.get("quality_score", 100.0),
                quality_report=quality_report,
                schema_profile=profile,
                clean_df=clean_df,
                filepath=filepath,
                file_hash=initial_hash,
                last_mtime=initial_mtime,
                auto_monitor=1
            )

            # 4. Update session storage & scheduler cache
            SESSION_STORE["df"] = clean_df
            SESSION_STORE["profile"] = profile
            SESSION_STORE["quality_report"] = quality_report
            SESSION_STORE["active_dataset_id"] = dataset_id
            
            summary["quality_report"] = quality_report
            summary["row_count"] = len(clean_df)
            summary["col_count"] = len(clean_df.columns)
            summary["dataset_id"] = dataset_id
            
            scheduler_service.set_active_dataframe(clean_df)
            
            # Reset conversation memory for the session on new dataset upload
            reset_session(session_id)

            return jsonify({
                "status": "success",
                "summary": summary,
                "quality_report": quality_report
            })
        except Exception as e:
            return jsonify({"error": f"Failed to parse dataset: {str(e)}"}), 500

    return jsonify({"error": "Invalid file format. Upload a CSV file."}), 400

@app.route('/api/query', methods=['POST'])
@app.route('/ask', methods=['POST'])
def query():
    if SESSION_STORE["df"] is None:
        # Fallback: check if latest dataset exists in DB
        latest = db_service.get_latest_dataset()
        if latest:
            reconstructed_df = db_service.get_clean_records_df(latest["id"])
            if reconstructed_df is not None and not reconstructed_df.empty:
                SESSION_STORE["df"] = reconstructed_df
                SESSION_STORE["profile"] = latest.get("schema_profile", {})
                SESSION_STORE["quality_report"] = latest.get("quality_report", {})
                SESSION_STORE["active_dataset_id"] = latest["id"]
        
        if SESSION_STORE["df"] is None:
            return jsonify({"error": "Please upload a CSV dataset first."}), 400

    data = request.get_json() or {}
    user_question = data.get("question", "").strip()
    session_id = data.get("session_id", "default_session")

    if not user_question:
        return jsonify({"error": "Question text cannot be empty."}), 400

    response = handle_question(
        question=user_question,
        df=SESSION_STORE["df"],
        profile=SESSION_STORE["profile"],
        session_id=session_id
    )
    return jsonify(response)

# -------------------------------------------------------------
# PHASE 2 & 3: DATA QUALITY REPORT API
# -------------------------------------------------------------
@app.route('/api/quality-report', methods=['GET'])
def get_quality_report():
    report = SESSION_STORE.get("quality_report")
    if not report:
        latest = db_service.get_latest_dataset()
        if latest:
            report = latest.get("quality_report")
    return jsonify(report or {"quality_score": 100.0, "operations_performed": []})

# -------------------------------------------------------------
# PHASE 4 & 5: TARGET / KPI MANAGEMENT API
# -------------------------------------------------------------
@app.route('/api/kpis', methods=['GET', 'POST'])
def manage_kpis():
    if request.method == 'GET':
        dataset_id = request.args.get("dataset_id")
        kpis = db_service.get_kpis(dataset_id=dataset_id)
        return jsonify(kpis)

    # POST: Create new KPI
    data = request.get_json() or {}
    kpi_name = data.get("kpi_name", "").strip()
    metric_col = data.get("metric_column", "").strip()
    target_val = data.get("target_value")

    if not kpi_name or not metric_col or target_val is None:
        return jsonify({"error": "kpi_name, metric_column, and target_value are required."}), 400

    kpi_payload = {
        "dataset_id": SESSION_STORE.get("active_dataset_id"),
        "kpi_name": kpi_name,
        "metric_column": metric_col,
        "calculation": data.get("calculation", "SUM"),
        "target_value": float(target_val),
        "period": data.get("period", "Monthly"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "alert_threshold_pct": float(data.get("alert_threshold_pct", 10.0)),
        "recipients": data.get("recipients", ""),
        "status": "ACTIVE"
    }

    kpi_id = db_service.save_kpi(kpi_payload)
    kpi_payload["id"] = kpi_id

    # Automatically evaluate immediately if dataset is active
    snapshot = None
    if SESSION_STORE["df"] is not None and metric_col in SESSION_STORE["df"].columns:
        try:
            snapshot = kpi_engine.evaluate_kpi(kpi_payload, SESSION_STORE["df"])
            alert_engine.evaluate_and_notify(snapshot)
        except Exception as e:
            app.logger.warning(f"Immediate evaluation failed: {e}")

    return jsonify({
        "status": "success",
        "kpi_id": kpi_id,
        "kpi": kpi_payload,
        "snapshot": snapshot
    })

@app.route('/api/kpis/<kpi_id>', methods=['DELETE'])
def delete_kpi(kpi_id):
    success = db_service.delete_kpi(kpi_id)
    if success:
        return jsonify({"status": "success", "message": f"KPI {kpi_id} deleted."})
    return jsonify({"error": "KPI not found."}), 404

# -------------------------------------------------------------
# PHASE 6, 7 & 8: KPI EVALUATION & ALERT EVALUATION API
# -------------------------------------------------------------
@app.route('/api/kpis/evaluate', methods=['POST'])
def evaluate_kpis():
    df = SESSION_STORE.get("df")
    if df is None:
        latest = db_service.get_latest_dataset()
        if latest:
            df = db_service.get_clean_records_df(latest["id"])
            SESSION_STORE["df"] = df

    if df is None:
        return jsonify({"error": "No active dataset available for evaluation."}), 400

    active_kpis = db_service.get_kpis(active_only=True)
    evaluated = []
    for kpi in active_kpis:
        try:
            snapshot = kpi_engine.evaluate_kpi(kpi, df)
            alert_result = alert_engine.evaluate_and_notify(snapshot)
            snapshot["alert_decision"] = alert_result
            evaluated.append(snapshot)
        except Exception as e:
            evaluated.append({
                "kpi_id": kpi["id"],
                "kpi_name": kpi.get("kpi_name"),
                "status": "ERROR",
                "error": str(e)
            })

    return jsonify({
        "status": "success",
        "evaluated_count": len(evaluated),
        "results": evaluated
    })

# -------------------------------------------------------------
# PHASE 9 & 12: ALERT HISTORY API
# -------------------------------------------------------------
@app.route('/api/alerts/history', methods=['GET'])
def get_alert_history():
    severity = request.args.get("severity")
    kpi_id = request.args.get("kpi_id")
    limit = int(request.args.get("limit", 100))
    alerts = db_service.get_alert_history(limit=limit, severity=severity, kpi_id=kpi_id)
    return jsonify(alerts)

# -------------------------------------------------------------
# PHASE 10 & 13: DEDICATED KPI DASHBOARD SUMMARY API
# -------------------------------------------------------------
@app.route('/api/dashboard/kpi-summary', methods=['GET'])
def get_kpi_dashboard_summary():
    summary = db_service.get_dashboard_summary()
    return jsonify(summary)

# -------------------------------------------------------------
# PHASE 15: BACKGROUND SCHEDULER API
# -------------------------------------------------------------
@app.route('/api/scheduler/status', methods=['GET'])
def get_scheduler_status():
    return jsonify(scheduler_service.get_status())

@app.route('/api/scheduler/toggle', methods=['POST'])
def toggle_scheduler():
    if scheduler_service.is_running:
        scheduler_service.stop()
        action = "stopped"
    else:
        scheduler_service.start()
        action = "started"
    return jsonify({"status": "success", "action": action, "scheduler": scheduler_service.get_status()})

# -------------------------------------------------------------
# DYNAMIC CSV MONITORING & SYNCHRONIZATION ENDPOINTS
# -------------------------------------------------------------
@app.route('/api/datasets/<dataset_id>/sync', methods=['POST'])
def sync_dataset_endpoint(dataset_id):
    """Manually or webhook-triggered sync for a dataset when its CSV is updated."""
    ds = db_service.get_dataset(dataset_id)
    if not ds:
        return jsonify({"error": "Dataset not found."}), 404
    
    filepath = ds.get("filepath", "")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": f"CSV file not found on disk at '{filepath}'."}), 400

    try:
        sync_result = csv_monitor.sync_dataset(ds)
        SESSION_STORE["df"] = sync_result["clean_df"]
        SESSION_STORE["quality_report"] = sync_result["quality_report"]
        scheduler_service.set_active_dataframe(sync_result["clean_df"])

        # Automatically recalculate all active KPIs
        evaluated = kpi_engine.evaluate_all(sync_result["clean_df"], dataset_id=dataset_id)
        alerts_triggered = 0
        for snap in evaluated:
            if isinstance(snap, dict) and snap.get("status") != "ERROR":
                alert_res = alert_engine.evaluate_and_notify(snap)
                if alert_res.get("alert_triggered"):
                    alerts_triggered += 1

        return jsonify({
            "status": "success",
            "sync": {
                "dataset_id": dataset_id,
                "row_count": sync_result["row_count"],
                "col_count": sync_result["col_count"],
                "quality_score": sync_result["quality_score"],
                "new_hash": sync_result["new_hash"]
            },
            "recalculated_kpis": len(evaluated),
            "alerts_triggered": alerts_triggered
        })
    except Exception as e:
        return jsonify({"error": f"Failed to sync dataset: {str(e)}"}), 500

@app.route('/api/datasets/<dataset_id>/monitor', methods=['POST'])
def toggle_dataset_monitoring(dataset_id):
    """Configures whether a dataset is actively monitored for CSV changes."""
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    success = db_service.set_dataset_auto_monitor(dataset_id, enabled)
    if success:
        return jsonify({"status": "success", "dataset_id": dataset_id, "auto_monitor": enabled})
    return jsonify({"error": "Dataset not found."}), 404

@app.route('/api/monitoring/status', methods=['GET'])
def get_monitoring_status():
    """Returns the current state of scheduler, monitored files, and last check timestamp."""
    return jsonify(scheduler_service.get_status())

@app.route('/api/monitoring/check-now', methods=['POST'])
def trigger_monitoring_check():
    """Triggers an immediate check for CSV modifications and KPI recalculation cycle."""
    summary = scheduler_service.run_cycle()
    return jsonify({"status": "success", "summary": summary})

if __name__ == '__main__':
    # Start scheduler daemon automatically on server boot
    scheduler_service.start(interval_seconds=300)
    app.run(debug=True, port=5000)