// ==========================================================================
// AI Data Analytics Platform - KPI & Alert Management Client Logic
// ==========================================================================

let activeAlertFilter = 'ALL';

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    loadQualityReport();
    loadKpisAndSummary();
    loadAlertHistory();
});

// -------------------------------------------------------------
// 1. DATA QUALITY REPORT VIEWER
// -------------------------------------------------------------
async function loadQualityReport() {
    try {
        const response = await fetch('/api/quality-report');
        if (!response.ok) return;
        const report = await response.json();
        renderQualityReport(report);
    } catch (e) {
        console.warn("Could not load quality report:", e);
    }
}

function renderQualityReport(report) {
    if (!report || report.total_rows_before === undefined) return;

    const score = report.quality_score !== undefined ? report.quality_score : 100.0;
    const circle = document.getElementById('qualityGaugeCircle');
    const scoreVal = document.getElementById('qualityScoreVal');
    const badge = document.getElementById('qualityHealthBadge');
    const desc = document.getElementById('qualityHealthDesc');

    if (circle) circle.style.setProperty('--score', score);
    if (scoreVal) scoreVal.textContent = `${score.toFixed(1)}%`;

    if (badge) {
        if (score >= 90) {
            badge.className = 'status-badge badge-on-track';
            badge.textContent = 'Excellent Health';
            if (desc) desc.textContent = 'Dataset is clean, consistent, and ready for high-accuracy autonomous analytics.';
        } else if (score >= 75) {
            badge.className = 'status-badge badge-at-risk';
            badge.textContent = 'Moderate Health';
            if (desc) desc.textContent = 'Dataset had missing values or formatting anomalies that were automatically sanitized.';
        } else {
            badge.className = 'status-badge badge-critical';
            badge.textContent = 'Needs Attention';
            if (desc) desc.textContent = 'Significant anomalies and missing elements were detected and corrected.';
        }
    }

    const setVal = (id, txt) => {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    };

    setVal('qRowsStat', `${report.total_rows_before || 0} → ${report.total_rows_after || 0}`);
    setVal('qDuplicatesStat', report.duplicates_removed || 0);
    setVal('qMissingStat', report.missing_values_fixed || 0);
    setVal('qDatesStat', report.invalid_dates_fixed || 0);
    setVal('qNumericStat', report.numeric_strings_sanitized || 0);
    setVal('qChronoStat', report.chronological_anomalies || 0);

    const list = document.getElementById('qualityOperationsList');
    if (list) {
        const ops = report.operations_performed || [];
        if (ops.length === 0) {
            list.innerHTML = `<li style="color: var(--text-muted); font-size: 0.9rem;">Dataset is pristine; zero cleaning interventions required.</li>`;
        } else {
            list.innerHTML = ops.map(op => `
                <li style="display: flex; align-items: center; gap: 8px; font-size: 0.9rem; color: var(--text-secondary);">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>${op}</span>
                </li>
            `).join('');
        }
    }
}

// -------------------------------------------------------------
// 2. KPI DASHBOARD & TARGET MONITORING
// -------------------------------------------------------------
async function loadKpisAndSummary() {
    try {
        const response = await fetch('/api/dashboard/kpi-summary');
        if (!response.ok) return;
        const data = await response.json();
        renderKpiSummaryCounters(data);
        renderKpiCards(data.kpis || []);
        populateMetricColumnDropdown(data.kpis);
    } catch (e) {
        console.warn("Could not load KPI summary:", e);
    }
}

function renderKpiSummaryCounters(data) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val !== undefined ? val : 0;
    };

    setVal('kpiTotalCount', data.total_kpis);
    setVal('kpiOnTrackCount', data.on_track);
    setVal('kpiAtRiskCount', data.at_risk);
    setVal('kpiCriticalCount', data.critical);
    setVal('kpiExceededCount', data.exceeded);
}

function renderKpiCards(kpis) {
    const container = document.getElementById('kpiCardsContainer');
    if (!container) return;

    if (!kpis || kpis.length === 0) {
        container.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 48px 20px; background: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: var(--radius-lg);">
                <p style="color: var(--text-muted); font-size: 0.95rem; margin-bottom: 12px;">No KPIs defined yet. Click <strong>+ Create Target KPI</strong> to configure your first business target.</p>
                <button class="btn-secondary" onclick="openKpiModal()">Create KPI Target</button>
            </div>
        `;
        return;
    }

    container.innerHTML = kpis.map(k => {
        const status = k.latest_status || 'PENDING';
        let badgeClass = 'badge-on-track';
        let progressFillColor = 'var(--success)';

        if (status === 'CRITICAL') {
            badgeClass = 'badge-critical';
            progressFillColor = 'var(--danger)';
        } else if (status === 'AT RISK') {
            badgeClass = 'badge-at-risk';
            progressFillColor = 'var(--warning)';
        } else if (status === 'EXCEEDED') {
            badgeClass = 'badge-exceeded';
            progressFillColor = 'var(--primary)';
        }

        const actual = k.actual_value !== undefined && k.actual_value !== null ? k.actual_value : 0;
        const target = k.target_value || 0;
        const achievement = k.achievement_pct !== undefined ? k.achievement_pct : 0;
        const expected = k.expected_progress_pct !== undefined ? k.expected_progress_pct : 100;
        const gap = k.performance_gap !== undefined ? k.performance_gap : 0;
        const progressWidth = Math.min(100, Math.max(0, achievement));

        return `
            <div class="kpi-monitor-card">
                <div>
                    <div class="kpi-header">
                        <div>
                            <div class="kpi-title">${k.kpi_name}</div>
                            <div class="kpi-metric-name">${k.calculation} of <strong>${k.metric_column}</strong> (${k.period || 'Monthly'})</div>
                        </div>
                        <span class="status-badge ${badgeClass}">${status}</span>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 8px;">
                        <div>
                            <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Actual / Target</div>
                            <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary);">
                                ${actual.toLocaleString()} <span style="font-size: 0.9rem; font-weight: 500; color: var(--text-muted);">/ ${target.toLocaleString()}</span>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Achievement</div>
                            <div style="font-size: 1.25rem; font-weight: 700; color: ${progressFillColor};">
                                ${achievement.toFixed(1)}%
                            </div>
                        </div>
                    </div>

                    <div class="kpi-progress-container">
                        <div class="kpi-progress-labels">
                            <span>Actual Progress: ${achievement.toFixed(1)}%</span>
                            <span>Expected Progress: ${expected.toFixed(1)}%</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill" style="width: ${progressWidth}%; background: ${progressFillColor};"></div>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-top: 6px; font-size: 0.78rem;">
                            <span style="color: var(--text-muted);">Performance Gap:</span>
                            <strong style="color: ${gap < 0 ? 'var(--danger)' : 'var(--success)'};">${gap >= 0 ? '+' : ''}${gap.toFixed(1)}%</strong>
                        </div>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-color); padding-top: 12px; margin-top: 12px;">
                    <span style="font-size: 0.75rem; color: var(--text-muted);">
                        ${k.last_evaluated_at ? `Evaluated: ${k.last_evaluated_at.slice(11, 16)} UTC` : 'Pending evaluation'}
                    </span>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="evaluateAllKpis()">Evaluate</button>
                        <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; color: var(--danger);" onclick="deleteKpi('${k.id}')">Delete</button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// -------------------------------------------------------------
// 3. TARGET CREATION MODAL & DROPDOWN POPULATION
// -------------------------------------------------------------
function openKpiModal() {
    const modal = document.getElementById('kpiModal');
    if (modal) {
        modal.classList.add('active');
        populateMetricColumnDropdown();
    }
}

function closeKpiModal() {
    const modal = document.getElementById('kpiModal');
    if (modal) modal.classList.remove('active');
}

function populateMetricColumnDropdown() {
    const select = document.getElementById('kpiMetricColSelect');
    if (!select) return;

    // Fetch numeric columns from active profile
    const profile = window.currentDatasetSummary?.profile || {};
    const numericCols = profile.numeric_cols || [];
    const kpiCols = profile.kpi_cols || [];
    const allCols = [...new Set([...numericCols, ...kpiCols])];

    if (allCols.length > 0) {
        select.innerHTML = '<option value="">-- Select Metric Column --</option>' +
            allCols.map(c => `<option value="${c}">${c}</option>`).join('');
    } else {
        // Fallback options
        select.innerHTML = `
            <option value="">-- Select Metric Column --</option>
            <option value="Sales">Sales</option>
            <option value="Profit">Profit</option>
            <option value="Revenue">Revenue</option>
            <option value="Quantity">Quantity</option>
        `;
    }
}

async function handleCreateKpi(event) {
    event.preventDefault();

    const payload = {
        kpi_name: document.getElementById('kpiNameInput').value.trim(),
        metric_column: document.getElementById('kpiMetricColSelect').value,
        calculation: document.getElementById('kpiCalcSelect').value,
        target_value: parseFloat(document.getElementById('kpiTargetValInput').value),
        period: document.getElementById('kpiPeriodSelect').value,
        start_date: document.getElementById('kpiStartDateInput').value || null,
        end_date: document.getElementById('kpiEndDateInput').value || null,
        alert_threshold_pct: parseFloat(document.getElementById('kpiThresholdInput').value || 10),
        recipients: document.getElementById('kpiRecipientsInput').value.trim()
    };

    try {
        const response = await fetch('/api/kpis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (response.ok) {
            showToast('KPI Target configured and active.', 'success');
            closeKpiModal();
            document.getElementById('kpiForm').reset();
            loadKpisAndSummary();
            loadAlertHistory();
        } else {
            showToast(result.error || 'Failed to create KPI', 'error');
        }
    } catch (e) {
        showToast(`Network error: ${e.message}`, 'error');
    }
}

async function evaluateAllKpis() {
    try {
        showToast('Evaluating all active KPIs against dataset...', 'info');
        const response = await fetch('/api/kpis/evaluate', { method: 'POST' });
        const result = await response.json();

        if (response.ok) {
            showToast(`Evaluated ${result.evaluated_count || 0} active KPIs.`, 'success');
            loadKpisAndSummary();
            loadAlertHistory();
        } else {
            showToast(result.error || 'Evaluation failed.', 'error');
        }
    } catch (e) {
        showToast(`Evaluation error: ${e.message}`, 'error');
    }
}

async function deleteKpi(kpiId) {
    if (!confirm('Are you sure you want to delete this KPI and its monitoring history?')) return;

    try {
        const response = await fetch(`/api/kpis/${kpiId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('KPI deleted successfully.', 'success');
            loadKpisAndSummary();
            loadAlertHistory();
        } else {
            showToast('Failed to delete KPI.', 'error');
        }
    } catch (e) {
        showToast(`Delete error: ${e.message}`, 'error');
    }
}

// -------------------------------------------------------------
// 4. ALERT HISTORY AUDIT TRAIL
// -------------------------------------------------------------
async function loadAlertHistory(severity = null) {
    const sev = severity || activeAlertFilter;
    try {
        let url = '/api/alerts/history?limit=50';
        if (sev && sev !== 'ALL') url += `&severity=${sev}`;

        const response = await fetch(url);
        if (!response.ok) return;
        const alerts = await response.json();
        renderAlertsTable(alerts);
    } catch (e) {
        console.warn("Could not load alert history:", e);
    }
}

function filterAlerts(severity, btn) {
    activeAlertFilter = severity;
    document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    loadAlertHistory(severity);
}

function renderAlertsTable(alerts) {
    const tbody = document.getElementById('alertsTableBody');
    if (!tbody) return;

    if (!alerts || alerts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 32px;">No alerts recorded for this filter.</td></tr>`;
        return;
    }

    tbody.innerHTML = alerts.map(a => {
        let badgeClass = 'badge-on-track';
        if (a.severity === 'CRITICAL') badgeClass = 'badge-critical';
        else if (a.severity === 'WARNING') badgeClass = 'badge-at-risk';
        else if (a.severity === 'INFO') badgeClass = 'badge-exceeded';

        const gap = a.performance_gap !== null && a.performance_gap !== undefined ? a.performance_gap : 0;
        const emailStatus = a.email_sent ?
            `<span style="color: var(--success); font-weight: 600;">✓ Email Sent</span>` :
            `<span style="color: var(--text-muted);">${a.email_error || 'No email required'}</span>`;

        return `
            <tr>
                <td style="white-space: nowrap; font-size: 0.8rem; color: var(--text-muted);">${a.triggered_at || '--'}</td>
                <td><strong>${a.kpi_name}</strong></td>
                <td><span style="font-size: 0.8rem; font-weight: 600;">${a.alert_type}</span></td>
                <td><span class="status-badge ${badgeClass}">${a.severity}</span></td>
                <td style="font-size: 0.85rem;">${(a.actual_value || 0).toLocaleString()} / ${(a.target_value || 0).toLocaleString()}</td>
                <td><strong style="color: ${gap < 0 ? 'var(--danger)' : 'var(--success)'};">${gap >= 0 ? '+' : ''}${gap.toFixed(1)}%</strong></td>
                <td style="font-size: 0.8rem;">${emailStatus}</td>
            </tr>
        `;
    }).join('');
}

// -------------------------------------------------------------
// 5. DYNAMIC CSV SYNC & MONITORING
// -------------------------------------------------------------
async function checkCsvUpdatesNow() {
    try {
        showToast('Checking for modified CSV files on disk...', 'info');
        const response = await fetch('/api/monitoring/check-now', { method: 'POST' });
        const result = await response.json();

        if (response.ok && result.status === 'success') {
            const summary = result.summary || {};
            const updatedCount = summary.csvs_updated || 0;
            const kpiCount = summary.evaluated_kpis || 0;

            if (updatedCount > 0) {
                showToast(`Detected CSV update! Re-cleaned and recalculated ${kpiCount} KPIs.`, 'success');
            } else {
                showToast(`No file changes detected. Evaluated ${kpiCount} active KPIs.`, 'info');
            }

            loadQualityReport();
            loadKpisAndSummary();
            loadAlertHistory();
        } else {
            showToast(result.error || 'Failed to check CSV updates.', 'error');
        }
    } catch (e) {
        showToast(`Sync error: ${e.message}`, 'error');
    }
}

