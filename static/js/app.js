/* ==========================================================================
   AI Data Analyst - Core Application Controller (app.js)
   Handles: Theme Toggle, View/Tab Switching, Sidebar Navigation, Toasts
   ========================================================================== */

// Global Application State
window.AppState = {
    activeDataset: null,
    columns: [],
    sampleData: [],
    currentPage: 1,
    rowsPerPage: 15,
    filteredData: [],
    theme: localStorage.getItem('ai_analyst_theme') || 'light',
    activeTab: 'dashboard-view'
};

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    setupDragAndDrop();
    checkExistingSession();
});

// 1. Theme Management (Light / Dark Mode)
function initTheme() {
    document.documentElement.setAttribute('data-theme', AppState.theme);
    updateThemeIcons(AppState.theme);
}

function toggleAppTheme() {
    const nextTheme = AppState.theme === 'light' ? 'dark' : 'light';
    AppState.theme = nextTheme;
    localStorage.setItem('ai_analyst_theme', nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
    updateThemeIcons(nextTheme);

    // Re-render any active charts with updated theme text colors
    if (window.activeChartInstances) {
        window.activeChartInstances.forEach(chart => {
            if (chart && chart.update) {
                chart.options.color = nextTheme === 'dark' ? '#cbd5e1' : '#475569';
                chart.update();
            }
        });
    }
}

function updateThemeIcons(theme) {
    const sun = document.getElementById('themeIconSun');
    const moon = document.getElementById('themeIconMoon');
    if (!sun || !moon) return;

    if (theme === 'dark') {
        sun.style.display = 'block';
        moon.style.display = 'none';
    } else {
        sun.style.display = 'none';
        moon.style.display = 'block';
    }
}

// 2. Sidebar Navigation & Responsive Toggle
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('active');
}

function switchTab(viewId, triggerBtn) {
    // Hide all view panels
    const panels = document.querySelectorAll('.view-panel');
    panels.forEach(panel => panel.style.display = 'none');

    // Show target view
    const target = document.getElementById(viewId);
    if (target) {
        target.style.display = 'block';
        AppState.activeTab = viewId;
    }

    // Update active nav button
    if (triggerBtn) {
        document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
        triggerBtn.classList.add('active');
    }

    // Close mobile drawer if open
    const sidebar = document.getElementById('sidebar');
    if (sidebar && window.innerWidth <= 992) {
        sidebar.classList.remove('open');
        const overlay = document.getElementById('sidebarOverlay');
        if (overlay) overlay.classList.remove('active');
    }
}

// 3. Toast Alert Notification System
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconSvg = '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>';
    if (type === 'success') {
        iconSvg = '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>';
    } else if (type === 'error') {
        iconSvg = '<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>';
    }

    toast.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink: 0;">
            ${iconSvg}
        </svg>
        <div style="flex: 1; font-size: 0.88rem; line-height: 1.4;">${message}</div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// 4. Session Reset
function resetAnalysisSession() {
    // Clear chat window
    const chatWindow = document.getElementById('chatWindow');
    if (chatWindow) {
        chatWindow.innerHTML = `
            <div class="chat-row bot-row">
                <div class="chat-avatar bot">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>
                        <rect width="18" height="12" x="3" y="8" rx="2"/>
                        <circle cx="9" cy="14" r="1"/>
                        <circle cx="15" cy="14" r="1"/>
                    </svg>
                </div>
                <div class="chat-bubble-container">
                    <div class="chat-bubble">
                        New conversation session started. Ask any question about your data!
                    </div>
                    <span class="chat-meta-time">Just now</span>
                </div>
            </div>
        `;
    }
    showToast('Conversation session reset. Previous turn memory cleared.', 'info');
}

// 5. Initial Session Check
function checkExistingSession() {
    // Check if mobile menu button should show
    const checkMobile = () => {
        const btn = document.getElementById('mobileMenuBtn');
        if (btn) btn.style.display = window.innerWidth <= 992 ? 'flex' : 'none';
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
}

