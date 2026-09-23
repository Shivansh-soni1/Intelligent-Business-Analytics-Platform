/* ==========================================================================
   AI Data Analyst - Chat & Visualization Controller (chat.js)
   Handles: AI Conversations, Typing Animation, Multi-Level Markdown,
   Stat KPI Cards, and Dynamic Chart.js Visualizations
   ========================================================================== */

let chartIdCounter = 0;
window.activeChartInstances = [];

function handleInputKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        submitUserQuestion();
    }
}

function executeSuggestedQuery(text) {
    const input = document.getElementById('userInput');
    if (input) input.value = text;
    // Switch to chat or dashboard view if needed
    if (AppState.activeTab === 'upload-view' || AppState.activeTab === 'preview-view') {
        switchTab('dashboard-view');
    }
    submitUserQuestion();
}

function startWithQuery(text) {
    executeSuggestedQuery(text);
}

async function submitUserQuestion() {
    const input = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const text = input ? input.value.trim() : '';

    if (!text) return;

    const chatWindow = document.getElementById('chatWindow');
    if (!chatWindow) return;

    // 1. Render User Message Bubble (Right-aligned)
    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userRow = document.createElement('div');
    userRow.className = 'chat-row user-row';
    userRow.innerHTML = `
        <div class="chat-avatar user">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                <circle cx="12" cy="7" r="4"></circle>
            </svg>
        </div>
        <div class="chat-bubble-container">
            <div class="chat-bubble">${escapeHtml(text)}</div>
            <span class="chat-meta-time">${timeString}</span>
        </div>
    `;
    chatWindow.appendChild(userRow);

    // Clear input & disable buttons during query
    if (input) {
        input.value = '';
        input.disabled = true;
    }
    if (sendBtn) sendBtn.disabled = true;

    // 2. Render Bot Typing Indicator (Left-aligned)
    const typingRow = document.createElement('div');
    typingRow.className = 'chat-row bot-row';
    typingRow.id = 'botTypingIndicator';
    typingRow.innerHTML = `
        <div class="chat-avatar bot">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>
                <rect width="18" height="12" x="3" y="8" rx="2"/>
                <circle cx="9" cy="14" r="1"/>
                <circle cx="15" cy="14" r="1"/>
            </svg>
        </div>
        <div class="chat-bubble-container">
            <div class="chat-bubble" style="background: var(--bg-surface-subtle); display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 0.85rem; color: var(--text-secondary);">Analyzing dataset with Pandas</span>
                <div class="typing-dots">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>
    `;
    chatWindow.appendChild(typingRow);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    // 3. Dispatch API Request to /api/query (or /ask)
    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: text,
                session_id: 'default_session'
            })
        });

        const data = await response.json();

        // Remove typing indicator
        const typingEl = document.getElementById('botTypingIndicator');
        if (typingEl) typingEl.remove();

        // 4. Render Bot Response
        renderBotResponse(data, chatWindow);

    } catch (err) {
        const typingEl = document.getElementById('botTypingIndicator');
        if (typingEl) typingEl.remove();

        renderBotErrorMessage('Network error while processing your analysis. Please check your connection.', chatWindow);
    } finally {
        if (input) {
            input.disabled = false;
            input.focus();
        }
        if (sendBtn) sendBtn.disabled = false;
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
}

// Render Successful Bot Analysis
function renderBotResponse(data, chatWindow) {
    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const botRow = document.createElement('div');
    botRow.className = 'chat-row bot-row';

    const rawAnswer = data.answer || 'Analysis complete.';
    const formattedHtml = formatAnalysisMarkdown(rawAnswer);

    let chartHtml = '';
    let canvasId = '';
    if (data.chart) {
        chartIdCounter++;
        canvasId = `chartCanvas_${chartIdCounter}`;
        chartHtml = `
            <div class="chart-container-bubble">
                <canvas id="${canvasId}" style="max-height: 320px; width: 100%;"></canvas>
            </div>
        `;
    }

    botRow.innerHTML = `
        <div class="chat-avatar bot">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>
                <rect width="18" height="12" x="3" y="8" rx="2"/>
                <circle cx="9" cy="14" r="1"/>
                <circle cx="15" cy="14" r="1"/>
            </svg>
        </div>
        <div class="chat-bubble-container" style="width: 100%;">
            <div class="chat-bubble">
                <div class="analysis-text-body">${formattedHtml}</div>
                ${chartHtml}
            </div>
            <span class="chat-meta-time">${timeString} • Verified by Pandas</span>
        </div>
    `;

    chatWindow.appendChild(botRow);

    // Initialize Chart.js if payload exists
    if (data.chart && canvasId) {
        setTimeout(() => {
            initDynamicChart(canvasId, data.chart);
        }, 50);
    }
}

// Render Error Message Gracefully
function renderBotErrorMessage(errMsg, chatWindow) {
    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const errRow = document.createElement('div');
    errRow.className = 'chat-row bot-row';
    errRow.innerHTML = `
        <div class="chat-avatar bot" style="background: #ef4444;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
        </div>
        <div class="chat-bubble-container">
            <div class="chat-bubble" style="border-left: 3px solid var(--danger);">
                <div style="font-weight: 600; margin-bottom: 4px; color: var(--danger);">Notice</div>
                <div>${escapeHtml(errMsg)}</div>
            </div>
            <span class="chat-meta-time">${timeString}</span>
        </div>
    `;
    chatWindow.appendChild(errRow);
}

// Initialize Dynamic Chart.js with SaaS Theme Palettes
function initDynamicChart(canvasId, chartPayload) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#cbd5e1' : '#475569';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';

    // Modern SaaS color sequence
    const palette = [
        '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6',
        '#06b6d4', '#ec4899', '#f97316', '#64748b'
    ];

    const ctx = canvas.getContext('2d');

    // Enhance dataset background colors
    if (chartPayload.data && chartPayload.data.datasets) {
        chartPayload.data.datasets.forEach((ds, idx) => {
            if (chartPayload.type === 'pie' || chartPayload.type === 'doughnut') {
                ds.backgroundColor = palette.slice(0, chartPayload.data.labels.length);
                ds.borderWidth = 2;
                ds.borderColor = isDark ? '#131d33' : '#ffffff';
            } else if (chartPayload.type === 'line') {
                ds.borderColor = palette[idx % palette.length];
                ds.backgroundColor = 'rgba(59, 130, 246, 0.12)';
                ds.fill = true;
                ds.tension = 0.35;
                ds.pointRadius = 4;
                ds.pointHoverRadius = 6;
            } else {
                ds.backgroundColor = palette[idx % palette.length];
                ds.borderRadius = 6;
            }
        });
    }

    // Modern Chart Options
    const options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: chartPayload.type === 'pie' || chartPayload.type === 'doughnut',
                position: 'bottom',
                labels: { color: textColor, font: { family: 'inherit', size: 12 } }
            },
            tooltip: {
                backgroundColor: isDark ? '#1e293b' : '#0f172a',
                titleColor: '#ffffff',
                bodyColor: '#ffffff',
                padding: 10,
                cornerRadius: 8
            }
        },
        scales: (chartPayload.type === 'pie' || chartPayload.type === 'doughnut') ? {} : {
            x: {
                ticks: { color: textColor, font: { size: 11 } },
                grid: { color: gridColor }
            },
            y: {
                ticks: { color: textColor, font: { size: 11 } },
                grid: { color: gridColor }
            }
        }
    };

    const newChart = new Chart(ctx, {
        type: chartPayload.type || 'bar',
        data: chartPayload.data,
        options: options
    });

    window.activeChartInstances.push(newChart);
}

// Markdown Parser for Clean Conversational Output
function formatAnalysisMarkdown(text) {
    if (!text) return '';

    let formatted = escapeHtml(text);

    // Bolding: **text** -> <strong>text</strong>
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Headers: ### Header -> <h4>Header</h4>
    formatted = formatted.replace(/^### (.*$)/gim, '<h4 style="margin: 8px 0 4px; color: var(--primary); font-weight: 700;">$1</h4>');
    formatted = formatted.replace(/^## (.*$)/gim, '<h3 style="margin: 10px 0 4px; font-weight: 700;">$1</h3>');

    // Bullet points: • item or - item -> <li>item</li>
    const lines = formatted.split('\n');
    let inList = false;
    const processedLines = [];

    lines.forEach(line => {
        const trimmed = line.trim();
        if (trimmed.startsWith('•') || trimmed.startsWith('-')) {
            if (!inList) {
                processedLines.push('<ul style="padding-left: 20px; margin: 6px 0;">');
                inList = true;
            }
            processedLines.push(`<li style="margin-bottom: 4px;">${trimmed.substring(1).trim()}</li>`);
        } else {
            if (inList) {
                processedLines.push('</ul>');
                inList = false;
            }
            if (trimmed.length > 0) {
                processedLines.push(`<p style="margin-bottom: 6px;">${trimmed}</p>`);
            }
        }
    });

    if (inList) processedLines.push('</ul>');

    return processedLines.join('');
}

function clearChatHistory() {
    resetAnalysisSession();
}