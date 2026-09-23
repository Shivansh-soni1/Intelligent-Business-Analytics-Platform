# Intelligent Business Analytics Platform 🚀

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Pandas](https://img.shields.io/badge/Pandas-2.2%2B-darkgreen.svg)](https://pandas.pydata.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Autonomous, Dataset-Agnostic AI Data Analyst, Automated Data Quality Engine, Business KPI Tracker, and Proactive Alert System.**

---

## 📖 Overview

The **Intelligent Business Analytics Platform** transforms raw, unstructured, or dirty CSV datasets into structured business intelligence. Non-technical stakeholders can chat with their data in plain English, view interactive visual charts, configure multi-timeframe KPI targets, and receive automated email alerts when business performance deviates from plan—all with zero manual data engineering.

---

## ✨ Key Features

- **🌐 100% Dataset-Agnostic Ingestion**: Upload any CSV dataset (E-Commerce, Finance, Healthcare, Logistics, SaaS). The system automatically detects data types and profiles schema attributes without pre-configured database migrations.
- **🛡️ Automated Data Validation & Cleaning**:
  - Automatically identifies missing entries, duplicate rows, broken dates, and corrupted currency numbers (`₹`, `$`, `15K`, `1.2M`).
  - Standardizes dates to ISO `YYYY-MM-DD` and sanitizes numerics.
  - Generates a **0–100% Data Quality Score** and Before vs. After audit log.
- **💬 Conversational AI Analyst**:
  - Ask questions in plain English (*"Show top 5 products by revenue"*, *"What is our cancellation rate by region?"*).
  - Translates queries into deterministic Pandas operations (40+ built-in aggregations, quadrant analysis, profit margins, MoM growth).
  - **Zero `eval()`**: Execution is safe, deterministic, and free of code-injection vulnerabilities.
- **📊 Dynamic Visualizations**:
  - Auto-selects the optimal Chart.js chart (Bar, Line, Scatter, Pie, Doughnut, Radar) based on query semantics.
- **🎯 Time-Aware KPI Target Tracking**:
  - Define custom targets (`SUM`, `AVERAGE`, `COUNT`, `MIN`, `MAX`, `MEDIAN`, `RATE`) with custom date windows.
  - Dynamically calculates:
    $$\text{Expected Progress \%} = \frac{\text{Days Passed}}{\text{Total Days}} \times 100$$
    $$\text{Performance Gap} = \text{Achievement \%} - \text{Expected Progress \%}$$
  - Classifies health status: `EXCEEDED`, `ON TRACK`, `AT RISK`, or `CRITICAL`.
- **🔔 Smart Alerts & Anti-Spam Cooldown**:
  - Triggers alerts when KPIs breach acceptable tolerance levels.
  - Sends styled HTML email reports with actual vs. target comparison cards.
  - Enforces a **24-hour anti-spam cooldown** to suppress repetitive notifications.
- **🔄 Dynamic CSV File Monitoring & Auto-Sync**:
  - Two-tier change detection ($O(1)$ `mtime` check + chunked 64KB SHA-256 hash).
  - Automatically re-cleans modified or appended CSV files and updates database records with **zero record duplication**.
  - Supports webhook synchronization (`POST /api/datasets/<id>/sync`) for Cloud Storage (AWS S3, Google Cloud Storage) integration.

---

## 🏛️ System Architecture

```
 CSV Upload / Disk Update
            ↓
  [ services/data_loader.py ]  ──▶  Dynamic Schema Classification
            ↓
  [ services/data_cleaner.py ] ──▶  Quality Score & Before/After Report
            ↓
  [ services/db_service.py ]   ──▶  Dataset-Agnostic SQLite Storage
            ↓
  ┌───────────────────────────────┴───────────────────────────────┐
  ▼                                                               ▼
[ Conversational AI Chat ]                                  [ KPI Engine ]
• 40+ Pandas Operations                                    • Time-based Progress %
• Multi-Turn Memory                                        • Performance Gap
• Dynamic Chart.js                                         • Status (On Track / At Risk)
                                                                  ↓
                                                            [ Alert Engine ]
                                                           • 24h Cooldown Window
                                                           • HTML Email Dispatch
```

---

## 📂 Project Structure

```text
├── app.py                           # Flask REST API and route handlers
├── services/
│   ├── csv_monitor.py               # File change detection & atomic re-sync engine
│   ├── data_cleaner.py              # Automated data validation & cleaning pipeline
│   ├── data_loader.py               # CSV ingestion & dynamic schema profiling
│   ├── db_service.py                # Dataset-agnostic SQLite database layer
│   ├── kpi_engine.py                # Mathematical KPI engine & time-based progress
│   ├── alert_engine.py              # Alert decision rules & cooldown logic
│   ├── email_service.py             # HTML email generator & SMTP mock handler
│   ├── scheduler_service.py         # Unified background daemon monitor thread
│   ├── query_processor.py           # Natural language query parser & Pandas executor
│   └── chat_memory.py               # Multi-turn conversation manager
├── templates/
│   ├── index.html                   # Unified SaaS platform dashboard
│   └── chat.html                    # Chat interface component
├── static/
│   ├── css/style.css                # Dark-themed SaaS interface styling
│   └── js/
│       ├── chat.js                  # Chat client & Chart.js rendering
│       └── kpi.js                   # KPI modals, target evaluation & sync triggers
├── tests/
│   ├── test_kpi_alert_platform.py   # Core platform regression test suite
│   └── test_dynamic_csv_monitoring.py # Dynamic CSV monitoring test suite
├── uploads/                         # Temporary storage for uploaded datasets
├── requirements.txt                 # Python package dependencies
├── .env.example                     # Environment configuration template
└── README.md                        # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Clone the Repository
```bash
git clone https://github.com/Shivansh-soni1/Intelligent-Business-Analytics-Platform.git
cd Intelligent-Business-Analytics-Platform
```

### 3. Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your API key:
```bash
cp .env.example .env
```
Edit `.env`:
```env
LLM_API_KEY=your_groq_api_key_here
LLM_MODEL=llama-3.3-70b-versatile
EMAIL_ENABLED=false # Set to true to enable live SMTP dispatch
```

### 6. Run the Application
```bash
python app.py
```
Open your browser at **`http://localhost:5000`**.

---

## 🧪 Running Automated Tests

Run the test suites to verify functionality:

```bash
# Run Dynamic CSV Monitoring tests
python -m unittest tests/test_dynamic_csv_monitoring.py

# Run Core KPI & Platform Regression tests
python -m unittest tests/test_kpi_alert_platform.py
```

---

## 🛡️ License

Distributed under the MIT License. See `LICENSE` for more information.
