/* ==========================================================================
   AI Data Analyst - Dashboard Controller (dashboard.js)
   Handles: Drag-and-Drop File Upload, Dataset Profiling, KPI Updates,
   Suggested Question Chips, and Paginated Interactive Table Preview
   ========================================================================== */

function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        uploadFileToServer(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        uploadFileToServer(files[0]);
    }
}

// Upload CSV to /api/upload
async function uploadFileToServer(file) {
    if (!file) return;

    // Validate file extension
    const fileName = file.name;
    if (!fileName.toLowerCase().endsWith('.csv') && !fileName.toLowerCase().endsWith('.txt')) {
        showToast('Please upload a valid CSV file (.csv)', 'error');
        return;
    }

    const progressContainer = document.getElementById('uploadProgressContainer');
    const progressBar = document.getElementById('uploadProgressBar');
    const progressPct = document.getElementById('uploadProgressPct');
    const fileNameEl = document.getElementById('uploadFileName');

    if (progressContainer) progressContainer.style.display = 'block';
    if (fileNameEl) fileNameEl.textContent = `${fileName} (${formatBytes(file.size)})`;

    // Simulated progress animation
    let progress = 10;
    const interval = setInterval(() => {
        progress = Math.min(progress + 15, 90);
        if (progressBar) progressBar.style.width = `${progress}%`;
        if (progressPct) progressPct.textContent = `${progress}%`;
    }, 150);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', 'default_session');

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        clearInterval(interval);

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            if (progressBar) progressBar.style.width = '100%';
            if (progressPct) progressPct.textContent = '100%';

            setTimeout(() => {
                if (progressContainer) progressContainer.style.display = 'none';
                if (progressBar) progressBar.style.width = '0%';
            }, 1000);

            showToast(`Dataset "${fileName}" loaded and profiled successfully!`, 'success');
            updateDashboardSummary(data.summary, fileName);

            // Switch to Dashboard view
            switchTab('dashboard-view');
        } else {
            if (progressContainer) progressContainer.style.display = 'none';
            const errorMsg = data.error || 'Failed to parse dataset.';
            showToast(errorMsg, 'error');
        }
    } catch (err) {
        clearInterval(interval);
        if (progressContainer) progressContainer.style.display = 'none';
        showToast('Network error while connecting to server. Please try again.', 'error');
    }
}

// Update Dashboard View with Profile Summary
function updateDashboardSummary(summary, filename) {
    AppState.activeDataset = filename;
    AppState.columns = summary.columns || summary.profile?.columns || [];
    AppState.sampleData = summary.sample_data || [];
    AppState.filteredData = [...AppState.sampleData];
    AppState.currentPage = 1;

    // 1. Hide Empty State Hero
    const emptyState = document.getElementById('emptyStateHero');
    if (emptyState) emptyState.style.display = 'none';

    // 2. Update Header Badge
    const headerBadge = document.getElementById('headerDatasetBadge');
    const headerFilename = document.getElementById('headerDatasetFilename');
    if (headerBadge && headerFilename) {
        headerBadge.style.display = 'inline-flex';
        headerFilename.textContent = filename;
    }

    // 3. Update Sidebar Dataset Card
    const sbName = document.getElementById('sidebarDatasetName');
    const sbStatus = document.getElementById('sidebarDatasetStatus');
    const sbDetails = document.getElementById('sidebarDatasetDetails');
    if (sbName) sbName.textContent = filename;
    if (sbStatus) {
        sbStatus.style.display = 'inline-flex';
        sbStatus.textContent = 'Active';
    }
    if (sbDetails) {
        sbDetails.innerHTML = `
            <span><strong>Rows:</strong> ${summary.row_count.toLocaleString()}</span>
            <span><strong>Columns:</strong> ${summary.col_count}</span>
            <span><strong>Domain:</strong> ${summary.domain || 'General'}</span>
        `;
    }

    // 4. Update KPI Overview Cards
    const prof = summary.profile || {};
    const kpiRows = document.getElementById('kpiRowsValue');
    const kpiCols = document.getElementById('kpiColsValue');
    const kpiNum = document.getElementById('kpiNumericValue');
    const kpiCat = document.getElementById('kpiCatValue');
    const kpiDates = document.getElementById('kpiDatesValue');

    if (kpiRows) kpiRows.textContent = summary.row_count.toLocaleString();
    if (kpiCols) kpiCols.textContent = summary.col_count;
    if (kpiNum) kpiNum.textContent = (prof.numeric_cols || []).length;
    if (kpiCat) kpiCat.textContent = (prof.categorical_cols || []).length;
    if (kpiDates) kpiDates.textContent = (prof.date_cols || []).length;

    // 5. Update Suggested Questions Chips
    const suggestionsContainer = document.getElementById('suggestedQuestionsContainer');
    if (suggestionsContainer && summary.suggested_questions) {
        suggestionsContainer.innerHTML = summary.suggested_questions.map(q => `
            <button class="suggestion-chip" onclick="executeSuggestedQuery('${escapeHtml(q)}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 14 14"></polyline>
                </svg>
                <span>${escapeHtml(q)}</span>
            </button>
        `).join('');
    }

    // 6. Render Paginated Dataset Preview Table
    renderPreviewTable();

    // 7. Refresh Data Quality Audit & KPI Targets Dropdown
    window.currentDatasetSummary = summary;
    if (summary.quality_report && typeof renderQualityReport === 'function') {
        renderQualityReport(summary.quality_report);
    }
    if (typeof loadKpisAndSummary === 'function') {
        loadKpisAndSummary();
    }
}

// 7. Interactive Dataset Preview Table Rendering
function renderPreviewTable() {
    const tableHead = document.getElementById('previewTableHead');
    const tableBody = document.getElementById('previewTableBody');
    const recordCountEl = document.getElementById('previewRecordCount');
    if (!tableHead || !tableBody) return;

    if (!AppState.columns || AppState.columns.length === 0) {
        tableHead.innerHTML = '<tr><th>No active columns</th></tr>';
        tableBody.innerHTML = '<tr><td>Upload a dataset to view records.</td></tr>';
        return;
    }

    if (recordCountEl) {
        recordCountEl.textContent = `Showing ${AppState.filteredData.length} records (${AppState.columns.length} columns)`;
    }

    // Render Table Header with column names
    tableHead.innerHTML = `
        <tr>
            <th style="width: 50px;">#</th>
            ${AppState.columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}
        </tr>
    `;

    // Calculate Pagination Slice
    const total = AppState.filteredData.length;
    const startIdx = (AppState.currentPage - 1) * AppState.rowsPerPage;
    const endIdx = Math.min(startIdx + AppState.rowsPerPage, total);
    const pageRows = AppState.filteredData.slice(startIdx, endIdx);

    if (pageRows.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="${AppState.columns.length + 1}" style="text-align: center; color: var(--text-muted); padding: 24px;">No matching records found.</td></tr>`;
    } else {
        tableBody.innerHTML = pageRows.map((row, idx) => `
            <tr>
                <td style="color: var(--text-muted); font-size: 0.78rem;">${startIdx + idx + 1}</td>
                ${AppState.columns.map(c => `<td>${escapeHtml(String(row[c] !== undefined && row[c] !== null ? row[c] : ''))}</td>`).join('')}
            </tr>
        `).join('');
    }

    // Update Pagination Controls
    const totalPages = Math.max(1, Math.ceil(total / AppState.rowsPerPage));
    const pageInfo = document.getElementById('paginationInfo');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');

    if (pageInfo) pageInfo.textContent = `Page ${AppState.currentPage} of ${totalPages} (${total} total rows)`;
    if (prevBtn) prevBtn.disabled = AppState.currentPage <= 1;
    if (nextBtn) nextBtn.disabled = AppState.currentPage >= totalPages;
}

function changePreviewPage(delta) {
    const totalPages = Math.ceil(AppState.filteredData.length / AppState.rowsPerPage);
    const target = AppState.currentPage + delta;
    if (target >= 1 && target <= totalPages) {
        AppState.currentPage = target;
        renderPreviewTable();
    }
}

function filterPreviewTable() {
    const input = document.getElementById('tableSearchInput');
    const query = (input ? input.value : '').toLowerCase().trim();

    if (!query) {
        AppState.filteredData = [...AppState.sampleData];
    } else {
        AppState.filteredData = AppState.sampleData.filter(row => {
            return Object.values(row).some(val => String(val).toLowerCase().includes(query));
        });
    }

    AppState.currentPage = 1;
    renderPreviewTable();
}

// Utilities
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

