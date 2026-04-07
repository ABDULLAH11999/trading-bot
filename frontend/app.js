const API_URL = window.location.origin;

const elements = {
    balance: document.getElementById('total-balance'),
    freeBalance: document.getElementById('free-balance'),
    quoteAsset: document.getElementById('quote-asset'),
    currentActivity: document.getElementById('current-activity'),
    totalPnl: document.getElementById('total-pnl'),
    totalTrades: document.getElementById('total-trades'),
    currentHoldings: document.getElementById('current-holdings'),
    activeTradesList: document.getElementById('active-trades-list'),
    historyTradesList: document.getElementById('history-trades-list'),
    logsContainer: document.getElementById('logs-container'),
    themeToggle: document.getElementById('theme-toggle'),
    botUptime: document.getElementById('bot-uptime'),

    // New Controls
    riskSlider: document.getElementById('risk-slider'),
    riskValue: document.getElementById('risk-value'),
    modeSelect: document.getElementById('bot-mode-select'),
    testBalanceInput: document.getElementById('test-balance-input'),
    setBalanceBtn: document.getElementById('set-balance-btn'),
    testTradeBtn: document.getElementById('test-trade-btn'),

    // Header Controls
    botEnabledSelect: document.getElementById('bot-enabled-select'),
    resetBotBtn: document.getElementById('reset-bot-btn'),
    logoutBtn: document.getElementById('logout-btn'),
    backToModeBtn: document.getElementById('back-to-mode-btn'),
    totalCommissions: document.getElementById('total-commissions'),
    accountBadge: document.getElementById('account-badge'),
    serverIpBadge: document.getElementById('server-ip-badge'),
    apiModeBadge: document.getElementById('api-mode-badge'),
    apiModeSelect: document.getElementById('api-mode-select'),
    apiModeStatic: document.getElementById('api-mode-static'),
    subscriptionChip: document.getElementById('subscription-chip'),
    testBalanceGroup: document.getElementById('test-balance-group'),
    testKeysPanel: document.getElementById('test-keys-panel'),
    realKeysPanel: document.getElementById('real-keys-panel'),

    reportAccountPill: document.getElementById('report-account-pill'),
    reportRangeLabel: document.getElementById('report-range-label'),
    reportSummaryGrid: document.getElementById('report-summary-grid'),
    reportChart: document.getElementById('report-chart'),
    reportMetaList: document.getElementById('report-meta-list'),
    reportTradesBody: document.getElementById('report-trades-body'),
    reportTradesCount: document.getElementById('report-trades-count'),
    reportTradeFilterTabs: document.querySelectorAll('.report-trade-filter-btn'),
    reportsEmptyState: document.getElementById('reports-empty-state'),
    reportsContent: document.getElementById('reports-content'),

    authOverlay: document.getElementById('auth-overlay'),
    authForm: document.getElementById('auth-form'),
    authPassword: document.getElementById('auth-password'),
    authEmail: document.getElementById('auth-email'),
    authToggle: document.getElementById('auth-toggle'),
    authSubmit: document.getElementById('auth-submit'),
    authError: document.getElementById('auth-error'),
    authPanelLogin: document.getElementById('auth-panel-login'),
    authPanelRegister: document.getElementById('auth-panel-register'),
    authPanelVerify: document.getElementById('auth-panel-verify'),
    authPanelMode: document.getElementById('auth-panel-mode'),
    authPanelBilling: document.getElementById('auth-panel-billing'),
    openDocsModalBtn: document.getElementById('open-docs-modal-btn'),
    openRiskModalBtn: document.getElementById('open-risk-modal-btn'),
    showRegisterBtn: document.getElementById('show-register-btn'),
    showLoginBtn: document.getElementById('show-login-btn'),
    registerForm: document.getElementById('register-form'),
    registerEmail: document.getElementById('register-email'),
    registerPassword: document.getElementById('register-password'),
    registerSubmit: document.getElementById('register-submit'),
    registerError: document.getElementById('register-error'),
    verifyForm: document.getElementById('verify-form'),
    verifyCode: document.getElementById('verify-code'),
    verifySubmit: document.getElementById('verify-submit'),
    verifyError: document.getElementById('verify-error'),
    verifyEmailLabel: document.getElementById('verify-email-label'),
    resendCodeBtn: document.getElementById('resend-code-btn'),
    verifyBackBtn: document.getElementById('verify-back-btn'),
    modeUserEmail: document.getElementById('mode-user-email'),
    modeLogoutBtn: document.getElementById('mode-logout-btn'),
    enterTestModeBtn: document.getElementById('enter-test-mode-btn'),
    enterRealModeBtn: document.getElementById('enter-real-mode-btn'),
    realModePill: document.getElementById('real-mode-pill'),
    subscriptionSummary: document.getElementById('subscription-summary'),
    modeError: document.getElementById('mode-error'),
    billingBackBtn: document.getElementById('billing-back-btn'),
    startCheckoutBtn: document.getElementById('start-checkout-btn'),
    billingError: document.getElementById('billing-error'),
    billingCardNumber: document.getElementById('billing-card-number'),
    billingExpiry: document.getElementById('billing-expiry'),
    billingCvc: document.getElementById('billing-cvc'),
    billingZip: document.getElementById('billing-zip'),
    testApiKey: document.getElementById('test-api-key'),
    testApiSecret: document.getElementById('test-api-secret'),
    realApiKey: document.getElementById('real-api-key'),
    realApiSecret: document.getElementById('real-api-secret'),
    saveApiConfigBtn: document.getElementById('save-api-config-btn'),
    apiConfigStatus: document.getElementById('api-config-status'),
    favoritePairsEnabled: document.getElementById('favorite-pairs-enabled'),
    favoritePairsDropdownBtn: document.getElementById('favorite-pairs-dropdown-btn'),
    favoritePairsDropdown: document.getElementById('favorite-pairs-dropdown'),
    favoritePairsOptions: document.getElementById('favorite-pairs-options'),
    favoritePairsAddBtn: document.getElementById('favorite-pairs-add-btn'),
    favoritePairsCurrent: document.getElementById('favorite-pairs-current'),
    favoritePairsStatus: document.getElementById('favorite-pairs-status'),
    favoritePairsSummary: document.getElementById('favorite-pairs-summary'),
    timeSlotsEnabled: document.getElementById('time-slots-enabled'),
    timeSlotsSummary: document.getElementById('time-slots-summary'),
    timeSlotStart: document.getElementById('time-slot-start'),
    timeSlotEnd: document.getElementById('time-slot-end'),
    timeSlotAddBtn: document.getElementById('time-slot-add-btn'),
    timeSlotsList: document.getElementById('time-slots-list'),
    timeSlotsStatus: document.getElementById('time-slots-status'),
    timeSlotBotClock: document.getElementById('time-slot-bot-clock'),
    closeAllTradesBtn: document.getElementById('close-all-trades-btn'),
    closeProfitTradesBtn: document.getElementById('close-profit-trades-btn'),
    closeLossTradesBtn: document.getElementById('close-loss-trades-btn'),
    infoModal: document.getElementById('info-modal'),
    infoModalTitle: document.getElementById('info-modal-title'),
    infoModalBody: document.getElementById('info-modal-body'),
    infoModalClose: document.getElementById('info-modal-close')
};

const REPORT_RANGE_LABELS = {
    overall: 'Overall',
    last_week: 'Last Week',
    last_day: 'Last Day',
    last_hour: 'Last Hour'
};

let selectedReportRange = 'overall';
let selectedReportTradeFilter = 'all';
let lastLoadedReport = null;
let lastReportRefreshAt = 0;
let reportRequestInFlight = false;
let isAuthenticated = false;
let authRequired = true;
let dashboardInterval = null;
let currentUserEmail = '';
let pendingVerificationEmail = '';
let selectedDashboardMode = '';
let currentSubscription = null;
let currentRealModeFee = 29;
let currentAccessState = null;
let favoritePairsEnabled = false;
let favoritePairs = [];
let favoritePairOptions = [];
let pendingFavoriteSelections = new Set();
let timeSlotsEnabled = false;
let timeSlots = [];
let bulkCloseNotice = '';
let savedApiCredentialState = {
    test: { hasKey: false, hasSecret: false },
    real: { hasKey: false, hasSecret: false }
};

const LOGIN_DOCUMENTATION_HTML = `
    <section>
        <h4>How This Bot Works</h4>
        <p>This Binance spot scalper watches selected spot pairs, checks momentum and execution conditions, and places trades only when the active strategy rules are satisfied. It is designed to automate faster spot trading decisions while still letting you control the key settings.</p>
    </section>
    <section>
        <h4>Platform Flow</h4>
        <ul>
            <li><strong>Register once:</strong> create your account and verify it by email.</li>
            <li><strong>Test Mode:</strong> practice first, review behavior, and tune settings without real funds.</li>
            <li><strong>Real Mode:</strong> unlock with subscription, save your real Binance keys, then use the live dashboard.</li>
            <li><strong>Live Logs:</strong> see what the bot is checking, when it enters, and why it skips or exits trades.</li>
        </ul>
    </section>
    <section>
        <h4>Bot Options</h4>
        <ul>
            <li><strong>Bot Mode:</strong> choose Steady, Aggressive, or Flipping Scalper based on how fast you want execution.</li>
            <li><strong>Capital Per Trade:</strong> sets the percentage of available balance used on each setup.</li>
            <li><strong>Set Test Balance:</strong> simulate a starting balance in Test Mode before using real funds.</li>
            <li><strong>Favourite Pair List:</strong> restrict trading to the spot pairs you want the bot to focus on.</li>
            <li><strong>Time Slot Trading:</strong> limit trading to selected hours only.</li>
            <li><strong>Enable Bot State:</strong> the bot runs only when enabled and the correct API keys are saved.</li>
        </ul>
    </section>
    <section>
        <h4>Rules The Bot Follows</h4>
        <ul>
            <li>The bot trades spot only and does not use futures.</li>
            <li>The bot may skip trades if momentum, liquidity, timing, or risk rules do not pass.</li>
            <li>The bot uses only test keys in Test Mode and only real keys in Real Mode.</li>
            <li>The bot requires the proper API keys before trading can be enabled.</li>
        </ul>
    </section>
`;

const RISK_WARNING_HTML = `
    <section>
        <h4>Trading Risk Warning</h4>
        <p>Crypto spot trading carries real financial risk. This bot can automate speed and execution, but it cannot guarantee profit or prevent loss. Volatility, slippage, sudden reversals, spread changes, low liquidity, exchange delays, and setup mistakes can all affect results.</p>
    </section>
    <section>
        <h4>Risks That Can Happen</h4>
        <ul>
            <li>Fast price movement can make entries and exits worse than expected.</li>
            <li>Flipping Scalper reacts faster, so it can also experience faster drawdowns in unstable conditions.</li>
            <li>Wrong API permissions or wrong key type can stop execution or cause failed trades.</li>
            <li>Poor favorite pair choices or bad trading hours can reduce performance.</li>
            <li>Strong market reversals can trigger losses before the strategy can recover.</li>
        </ul>
    </section>
    <section>
        <h4>Recommended Starting Setup</h4>
        <ul>
            <li>Start in <strong>Test Mode</strong> first before switching to real capital.</li>
            <li>Use <strong>Flipping Scalper</strong> if you want fast execution and quicker momentum reaction.</li>
            <li>Start with a <strong>$100 test balance</strong> to review realistic behavior and dashboard logs.</li>
            <li>Keep your trade allocation controlled and monitor logs before increasing capital.</li>
            <li>After stable results in Test Mode, move to Real Mode carefully with the same logic.</li>
        </ul>
    </section>
    <section>
        <h4>Safety Reminders</h4>
        <ul>
            <li>Only use funds you can afford to lose.</li>
            <li>Confirm your Binance API permissions are correct and do not enable withdrawals.</li>
            <li>Review bot mode, trade allocation, favourite pairs, and time slot controls carefully.</li>
            <li>Monitor the bot regularly. Automation reduces manual work, but it does not remove trading risk.</li>
        </ul>
    </section>
`;

function formatMoney(value, quoteAsset = 'USDT') {
    const num = Number(value || 0);
    const sign = num < 0 ? '-' : '';
    return `${sign}$${Math.abs(num).toFixed(2)} ${quoteAsset}`;
}

function formatPercent(value) {
    const num = Number(value || 0);
    return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`;
}

function formatTimestamp(ts) {
    if (!ts) return '-';
    return new Date(ts * 1000).toLocaleString();
}

function formatDate(ts) {
    if (!ts) return '-';
    return new Date(ts * 1000).toLocaleDateString();
}

function formatSubscriptionFee() {
    return `$${Number(currentRealModeFee || 29).toFixed(0)}`;
}

function updateAccessState(access) {
    currentAccessState = access || null;
}

function updateSavedApiCredentialState(config) {
    savedApiCredentialState = {
        test: {
            hasKey: Boolean(config?.test?.has_saved_key),
            hasSecret: Boolean(config?.test?.has_saved_secret)
        },
        real: {
            hasKey: Boolean(config?.real?.has_saved_key),
            hasSecret: Boolean(config?.real?.has_saved_secret)
        }
    };
}

function hasCurrentTypedKeysForMode(mode) {
    const activeMode = mode === 'real' ? 'real' : 'test';
    const keyInput = activeMode === 'real' ? elements.realApiKey : elements.testApiKey;
    const secretInput = activeMode === 'real' ? elements.realApiSecret : elements.testApiSecret;
    return Boolean((keyInput?.value || '').trim()) && Boolean((secretInput?.value || '').trim());
}

function hasSavedKeysForMode(mode) {
    const activeMode = mode === 'real' ? 'real' : 'test';
    return Boolean(savedApiCredentialState?.[activeMode]?.hasKey) && Boolean(savedApiCredentialState?.[activeMode]?.hasSecret);
}

function hasUsableKeysForMode(mode) {
    return hasCurrentTypedKeysForMode(mode) || hasSavedKeysForMode(mode);
}

function scrollToApiSectionWithMessage(message, mode = selectedDashboardMode || 'test') {
    const modeLabel = mode === 'real' ? 'real' : 'test';
    if (elements.apiConfigStatus) {
        elements.apiConfigStatus.textContent = message || `Set your ${modeLabel} API keys in the API keys section below.`;
        elements.apiConfigStatus.style.color = '#fda4af';
    }
    const apiSection = document.getElementById('view-api');
    if (apiSection) {
        apiSection.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    if (modeLabel === 'real') {
        elements.realApiKey?.focus();
    } else {
        elements.testApiKey?.focus();
    }
    alert(message || `Enter your ${modeLabel} API keys to run the bot.`);
}

function applyFallbackIcons() {
    const iconMap = {
        'fa-eye': '◉',
        'fa-eye-slash': '◎',
        'fa-lock': '●',
        'fa-bolt': '▲',
        'fa-trash-alt': '⌫',
        'fa-sign-out-alt': '↗',
        'fa-moon': '◐',
        'fa-sun': '☼',
        'fa-wallet': '◫',
        'fa-exchange-alt': '⇄',
        'fa-briefcase': '▣',
        'fa-clock': '◷',
        'fa-percentage': '%',
        'fa-chevron-down': '▾',
        'fa-play': '▶',
        'fa-chart-bar': '▥',
        'fa-key': '⌘',
        'fa-spinner': '◌',
        'fa-times': '×'
    };
    document.querySelectorAll('i').forEach((icon) => {
        const match = Array.from(icon.classList).find((className) => iconMap[className]);
        if (!match) return;
        icon.textContent = iconMap[match];
        icon.classList.add('fallback-icon');
    });
}

function validateBillingFields() {
    const cardNumber = String(elements.billingCardNumber?.value || '').replace(/\s+/g, '');
    const expiry = String(elements.billingExpiry?.value || '').trim();
    const cvc = String(elements.billingCvc?.value || '').trim();
    const zip = String(elements.billingZip?.value || '').trim();
    if (!/^\d{16}$/.test(cardNumber)) {
        throw new Error('Enter a valid 16-digit card number.');
    }
    if (!/^\d{2}\/\d{2}$/.test(expiry)) {
        throw new Error('Enter expiry in MM/YY format.');
    }
    const [monthText, yearText] = expiry.split('/');
    const month = Number(monthText);
    if (month < 1 || month > 12) {
        throw new Error('Enter a valid expiry month.');
    }
    if (!/^\d{3,4}$/.test(cvc)) {
        throw new Error('Enter a valid CVC.');
    }
    if (!/^[A-Za-z0-9 -]{3,10}$/.test(zip)) {
        throw new Error('Enter a valid ZIP / postal code.');
    }
    return { cardNumber, expiry, cvc, zip };
}

function formatChartPrice(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num) || num <= 0) return '$0.0000';
    if (num >= 100) return `$${num.toFixed(2)}`;
    if (num >= 1) return `$${num.toFixed(4)}`;
    return `$${num.toFixed(6)}`;
}

function formatUptimeFromEpoch(epochSeconds) {
    const startMs = Number(epochSeconds || 0) * 1000;
    if (!Number.isFinite(startMs) || startMs <= 0) {
        return '00:00:00';
    }
    const diff = Math.max(0, Math.floor((Date.now() - startMs) / 1000));
    const h = Math.floor(diff / 3600).toString().padStart(2, '0');
    const m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
    const s = (diff % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function renderReportChart(points, quoteAsset) {
    if (!elements.reportChart) return;
    if (!points || points.length === 0) {
        elements.reportChart.innerHTML = '<div class="empty-state" style="padding: 60px 20px;">No capital data yet.</div>';
        return;
    }

    const width = 920;
    const height = 290;
    const padding = { top: 24, right: 22, bottom: 34, left: 58 };
    const values = points.map(point => Number(point.equity || 0));
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const span = Math.max(maxValue - minValue, 1);
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    const path = points.map((point, index) => {
        const x = padding.left + (plotWidth * index / Math.max(points.length - 1, 1));
        const normalized = (Number(point.equity || 0) - minValue) / span;
        const y = padding.top + plotHeight - (normalized * plotHeight);
        return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    }).join(' ');

    const grid = [0, 0.25, 0.5, 0.75, 1].map(step => {
        const y = padding.top + (plotHeight * step);
        return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-width="1" />`;
    }).join('');

    const labels = [maxValue, minValue + (span * 0.5), minValue].map((value, index) => {
        const y = index === 0 ? padding.top + 4 : index === 1 ? padding.top + (plotHeight / 2) + 4 : padding.top + plotHeight + 4;
        return `<text x="12" y="${y}" fill="rgba(203,213,225,0.88)" font-size="11">${formatMoney(value, quoteAsset)}</text>`;
    }).join('');

    const lastPoint = points[points.length - 1];
    const lastX = padding.left + plotWidth;
    const lastY = padding.top + plotHeight - (((Number(lastPoint.equity || 0) - minValue) / span) * plotHeight);

    elements.reportChart.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Capital progress chart">
            <defs>
                <linearGradient id="reportLineFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="rgba(59,130,246,0.35)" />
                    <stop offset="100%" stop-color="rgba(59,130,246,0.02)" />
                </linearGradient>
            </defs>
            ${grid}
            ${labels}
            <path d="${path}" fill="none" stroke="#54a6ff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
            <circle cx="${lastX}" cy="${lastY}" r="5" fill="#10b981"></circle>
        </svg>
    `;
}

function renderReport(report) {
    lastLoadedReport = report;
    const stats = report.stats || {};
    const quoteAsset = report.quote_asset || 'USDT';
    const trades = report.trades || [];
    const filteredTrades = trades.filter((trade) => {
        const pnl = Number(trade.net_pnl || 0);
        if (selectedReportTradeFilter === 'profit') return pnl > 0;
        if (selectedReportTradeFilter === 'loss') return pnl < 0;
        return true;
    });
    const hasReportData = (report.equity_curve || []).length > 1 || trades.length > 0;

    if (elements.reportAccountPill) {
        elements.reportAccountPill.textContent = `${report.account_label} Report`;
    }
    if (elements.reportRangeLabel) {
        elements.reportRangeLabel.textContent = REPORT_RANGE_LABELS[report.range] || 'Overall';
    }
    if (elements.reportTradesCount) {
        const total = Number(stats.trade_count || trades.length || 0);
        if (selectedReportTradeFilter === 'all') {
            elements.reportTradesCount.textContent = `${total} trades`;
        } else {
            elements.reportTradesCount.textContent = `${filteredTrades.length} of ${total} trades`;
        }
    }
    if (elements.reportsEmptyState && elements.reportsContent) {
        elements.reportsEmptyState.style.display = hasReportData ? 'none' : 'block';
        elements.reportsContent.style.display = hasReportData ? 'block' : 'none';
    }

    if (!hasReportData) {
        return;
    }

    if (elements.reportSummaryGrid) {
        const cards = [
            ['Net PnL', formatMoney(stats.net_pnl, quoteAsset)],
            ['Return', formatPercent(stats.return_pct)],
            ['Trades', `${stats.trade_count || 0}`],
            ['Win Rate', `${Number(stats.win_rate || 0).toFixed(2)}%`],
            ['Fees', formatMoney(stats.commission_paid, quoteAsset)],
            ['Ending Capital', formatMoney(stats.end_equity, quoteAsset)]
        ];
        elements.reportSummaryGrid.innerHTML = cards.map(([label, value]) => `
            <div class="report-stat-card">
                <span>${label}</span>
                <strong>${value}</strong>
            </div>
        `).join('');
    }

    renderReportChart(report.equity_curve || [], quoteAsset);

    if (elements.reportMetaList) {
        const rows = [
            ['Session Started', formatTimestamp(report.session_started_at)],
            ['Last Reset', formatTimestamp(report.last_reset_at)],
            ['Range Start', formatTimestamp(report.range_started_at)],
            ['Best Trade', formatMoney(stats.best_trade, quoteAsset)],
            ['Worst Trade', formatMoney(stats.worst_trade, quoteAsset)],
            ['Active Positions', `${stats.active_positions || 0}`]
        ];
        elements.reportMetaList.innerHTML = rows.map(([label, value]) => `
            <div class="report-meta-row">
                <span>${label}</span>
                <strong>${value}</strong>
            </div>
        `).join('');
    }

    if (elements.reportTradesBody) {
        elements.reportTradesBody.innerHTML = filteredTrades.length > 0
            ? filteredTrades.map(trade => `
                <tr>
                    <td>${trade.symbol}</td>
                    <td>${formatTimestamp(trade.opened_at)}</td>
                    <td>${formatTimestamp(trade.closed_at)}</td>
                    <td>$${Number(trade.entry_price || 0).toFixed(4)}</td>
                    <td>$${Number(trade.exit_price || 0).toFixed(4)}</td>
                    <td>${Number(trade.amount || 0).toFixed(4)}</td>
                    <td>$${Number(trade.commission_paid || 0).toFixed(4)}</td>
                    <td class="${Number(trade.net_pnl || 0) >= 0 ? 'net-plus' : 'net-minus'}">${Number(trade.net_pnl || 0) >= 0 ? '+' : ''}$${Number(trade.net_pnl || 0).toFixed(4)}</td>
                </tr>
            `).join('')
            : '<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">No matching trades for this filter in this range.</td></tr>';
    }
}

async function updatePerformanceReport(range = selectedReportRange) {
    if (!isAuthenticated && authRequired) return;
    if (reportRequestInFlight) return;
    if (Date.now() - lastReportRefreshAt < 4000 && range === selectedReportRange) return;
    try {
        reportRequestInFlight = true;
        const response = await fetch(`${API_URL}/reports/summary?range=${encodeURIComponent(range)}`);
        if (response.status === 401) {
            lockApp('Please login to continue.');
            return;
        }
        if (!response.ok) throw new Error('Failed to load performance report');
        const report = await response.json();
        selectedReportRange = report.range || range;
        lastReportRefreshAt = Date.now();
        document.querySelectorAll('.report-range-btn').forEach(button => {
            button.classList.toggle('active', button.dataset.range === selectedReportRange);
        });
        renderReport(report);
    } catch (error) {
        console.error('Performance report update failed:', error);
    } finally {
        reportRequestInFlight = false;
    }
}

function downloadPerformanceReport(range) {
    if (!isAuthenticated && authRequired) return;
    const link = document.createElement('a');
    link.href = `${API_URL}/reports/download?range=${encodeURIComponent(range)}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
}

function setAuthPanel(panelName, message = '') {
    const panels = {
        login: elements.authPanelLogin,
        register: elements.authPanelRegister,
        verify: elements.authPanelVerify,
        mode: elements.authPanelMode,
        billing: elements.authPanelBilling
    };
    Object.entries(panels).forEach(([name, panel]) => {
        if (panel) {
            panel.style.display = name === panelName ? 'block' : 'none';
        }
    });
    if (elements.authError) elements.authError.textContent = panelName === 'login' ? message : '';
    if (elements.registerError) elements.registerError.textContent = panelName === 'register' ? message : '';
    if (elements.verifyError) elements.verifyError.textContent = panelName === 'verify' ? message : '';
    if (elements.modeError) elements.modeError.textContent = panelName === 'mode' ? message : '';
    if (elements.billingError) elements.billingError.textContent = panelName === 'billing' ? message : '';
}

function openInfoModal(title, html) {
    if (!elements.infoModal || !elements.infoModalTitle || !elements.infoModalBody) return;
    elements.infoModalTitle.textContent = title;
    elements.infoModalBody.innerHTML = html;
    elements.infoModal.style.display = 'flex';
}

function closeInfoModal() {
    if (!elements.infoModal) return;
    elements.infoModal.style.display = 'none';
}

function updateSubscriptionUi(subscription) {
    currentSubscription = subscription || null;
    const active = Boolean(subscription?.active || currentAccessState?.real_mode_enabled);
    const endText = subscription?.current_period_end ? formatDate(subscription.current_period_end) : '-';
    const showRealModeDate = selectedDashboardMode === 'real';
    if (elements.subscriptionChip) {
        elements.subscriptionChip.textContent = active
            ? (showRealModeDate && subscription?.current_period_end
                ? `Subscription ends on ${endText}`
                : 'Subscription: Real mode unlocked')
            : 'Subscription: Real mode locked';
    }
    if (elements.realModePill) {
        elements.realModePill.className = active ? 'mode-pill success' : 'mode-pill locked';
        elements.realModePill.innerHTML = active ? 'Unlocked' : '<i class="fas fa-lock"></i> Locked';
    }
    if (elements.subscriptionSummary) {
        elements.subscriptionSummary.textContent = active
            ? `Real mode unlocked.${subscription?.current_period_end ? ` Current subscription ends on ${endText}.` : ' Admin access is enabled for this account.'}`
            : `${formatSubscriptionFee()}/month subscription required to unlock real account.`;
    }
    if (elements.enterRealModeBtn) {
        elements.enterRealModeBtn.textContent = active ? 'Enter Real Mode' : 'Unlock Real Dashboard';
    }
    const billingFeeText = document.getElementById('billing-fee-text');
    if (billingFeeText) {
        billingFeeText.textContent = `${formatSubscriptionFee()} / month`;
    }
    applyFallbackIcons();
}

function applyModePresentation(mode) {
    const activeMode = mode === 'real' ? 'real' : 'test';
    const isRealMode = activeMode === 'real';

    document.body.classList.toggle('real-mode', isRealMode);

    if (elements.accountBadge) {
        elements.accountBadge.innerText = isRealMode ? 'Real Account' : 'Demo';
        elements.accountBadge.className = isRealMode ? 'badge-status real' : 'badge-status demo';
    }

    if (elements.apiModeBadge) {
        elements.apiModeBadge.innerText = isRealMode ? 'Real Keys' : 'Testnet Active';
        elements.apiModeBadge.className = isRealMode ? 'badge yellow' : 'badge green';
    }

    if (elements.testBalanceInput) {
        elements.testBalanceInput.disabled = isRealMode;
        if (isRealMode) {
            elements.testBalanceInput.value = '';
            elements.testBalanceInput.placeholder = 'Disabled in Real Mode';
        }
    }

    if (elements.setBalanceBtn) {
        elements.setBalanceBtn.disabled = isRealMode;
    }

    if (elements.testBalanceGroup) {
        elements.testBalanceGroup.style.display = isRealMode ? 'none' : '';
    }
}

function syncModeSpecificUi(mode) {
    const activeMode = mode === 'real' ? 'real' : 'test';
    selectedDashboardMode = activeMode;
    applyModePresentation(activeMode);
    if (elements.testKeysPanel) elements.testKeysPanel.style.display = activeMode === 'test' ? 'grid' : 'none';
    if (elements.realKeysPanel) elements.realKeysPanel.style.display = activeMode === 'real' ? 'grid' : 'none';
    if (elements.apiModeSelect && !elements.apiModeSelect.matches(':focus')) {
        elements.apiModeSelect.value = activeMode;
    }
    if (elements.apiModeStatic) {
        elements.apiModeStatic.textContent = activeMode === 'real' ? 'Real Keys' : 'Test Keys';
    }
    if (elements.saveApiConfigBtn) {
        elements.saveApiConfigBtn.innerHTML = `<i class="fas fa-key"></i> Save ${activeMode === 'real' ? 'Real' : 'Test'} Keys`;
    }
    applyFallbackIcons();
}

function lockApp(message = '') {
    isAuthenticated = false;
    document.body.classList.add('auth-locked');
    setAuthPanel('login', message);
    if (elements.authPassword) {
        elements.authPassword.value = '';
        setTimeout(() => elements.authPassword.focus(), 40);
    }
}

function unlockApp(showModePicker = false) {
    isAuthenticated = true;
    if (showModePicker) {
        document.body.classList.add('auth-locked');
        setAuthPanel('mode');
    } else {
        document.body.classList.remove('auth-locked');
    }
}

async function refreshBillingStatus(force = true) {
    if (!isAuthenticated && authRequired) return null;
    try {
        const response = await fetch(`${API_URL}/billing/status`);
        if (response.status === 401) {
            lockApp('Please login again.');
            return null;
        }
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Failed to load subscription status.');
        }
        currentRealModeFee = Number(result.real_mode_fee || currentRealModeFee || 29);
        updateSubscriptionUi(result.subscription || null);
        return result.subscription || null;
    } catch (error) {
        console.error('Billing status failed:', error);
        return null;
    }
}

async function checkAuthStatus() {
    const response = await fetch(`${API_URL}/auth/status`);
    if (!response.ok) {
        throw new Error('Unable to verify access status.');
    }
    const result = await response.json();
    authRequired = Boolean(result.auth_required);
    currentRealModeFee = Number(result.real_mode_fee || currentRealModeFee || 29);
    currentUserEmail = result.email || '';
    updateAccessState(result.user?.access || null);
    updateSubscriptionUi(result.subscription || result.user?.subscription || null);
    if (elements.modeUserEmail) {
        elements.modeUserEmail.textContent = currentUserEmail || '-';
    }
    if (!authRequired || result.authenticated) {
        unlockApp(true);
        await loadApiConfig();
        await refreshBillingStatus();
        await refreshServerIpBadge();
    } else {
        if (elements.serverIpBadge) {
            elements.serverIpBadge.textContent = 'Current IP: login required';
            elements.serverIpBadge.title = '';
        }
        lockApp('Login with your email and password to continue.');
    }
}

function applyMaskedPlaceholder(input, maskedValue) {
    if (!input) return;
    input.value = '';
    const placeholderText = maskedValue ? `Saved: ${maskedValue}` : '';
    input.placeholder = placeholderText;
    input.title = placeholderText || 'No saved key for this field yet.';
}

async function loadApiConfig() {
    if (!isAuthenticated && authRequired) return;
    try {
        const response = await fetch(`${API_URL}/user/api-config`);
        if (response.status === 401) {
            lockApp('Please login again to continue.');
            return;
        }
        if (!response.ok) {
            throw new Error('Failed to load API key settings.');
        }
        const config = await response.json();
        currentUserEmail = config.email || currentUserEmail;
        currentRealModeFee = Number(config.real_mode_fee || currentRealModeFee || 29);
        updateAccessState(config.access || null);
        updateSubscriptionUi(config.subscription || null);
        updateSavedApiCredentialState(config);

        const activeMode = selectedDashboardMode || config.preferred_mode || 'test';
        if (elements.apiModeSelect) {
            elements.apiModeSelect.value = activeMode;
        }
        syncModeSpecificUi(activeMode);

        applyMaskedPlaceholder(elements.testApiKey, config.test?.saved_key_masked);
        applyMaskedPlaceholder(elements.testApiSecret, config.test?.saved_secret_masked);
        applyMaskedPlaceholder(elements.realApiKey, config.real?.saved_key_masked);
        applyMaskedPlaceholder(elements.realApiSecret, config.real?.saved_secret_masked);

        if (elements.apiConfigStatus) {
            elements.apiConfigStatus.style.color = 'var(--text-secondary)';
            elements.apiConfigStatus.textContent = `Logged in as ${currentUserEmail || 'session user'}. ${activeMode === 'real' ? 'Real' : 'Test'} keys shown below are encrypted and saved per email.${hasSavedKeysForMode(activeMode) ? ' Saved keys are ready to use after refresh.' : ''}`;
        }
    } catch (error) {
        console.error('API config load failed:', error);
        if (elements.apiConfigStatus) {
            elements.apiConfigStatus.textContent = error.message || 'Failed to load API key settings.';
        }
    }
}

async function refreshServerIpBadge() {
    if (!elements.serverIpBadge) return;
    if (!isAuthenticated && authRequired) {
        elements.serverIpBadge.textContent = 'Current IP: login required';
        elements.serverIpBadge.title = '';
        return;
    }
    try {
        const response = await fetch(`${API_URL}/server/network-info`);
        if (response.status === 401) {
            elements.serverIpBadge.textContent = 'Current IP: login required';
            elements.serverIpBadge.title = '';
            return;
        }
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || 'Unable to fetch server IP.');
        }
        const ipValue = String(payload.public_ip || '').trim();
        elements.serverIpBadge.textContent = ipValue ? `Current IP: ${ipValue}` : 'Current IP: unavailable';
        elements.serverIpBadge.title = payload.note || '';
    } catch (error) {
        console.error('Server IP fetch failed:', error);
        elements.serverIpBadge.textContent = 'Current IP: unavailable';
        elements.serverIpBadge.title = 'Unable to fetch the current server IP right now.';
    }
}

function setFavoritePairsStatus(message, isError = false) {
    if (!elements.favoritePairsStatus) return;
    elements.favoritePairsStatus.textContent = message;
    elements.favoritePairsStatus.style.color = isError ? '#fda4af' : 'var(--text-secondary)';
}

function buildFavoritePairOptionMap() {
    const optionMap = new Map();
    favoritePairOptions.forEach(option => {
        optionMap.set(option.symbol, option);
    });
    favoritePairs.forEach(symbol => {
        if (!optionMap.has(symbol)) {
            optionMap.set(symbol, { symbol, label: symbol, group: 'Favorites', price_change_pct: 0 });
        }
    });
    return optionMap;
}

function renderFavoritePairTags() {
    if (!elements.favoritePairsCurrent) return;
    if (!favoritePairs.length) {
        elements.favoritePairsCurrent.innerHTML = '<span class="favorites-empty">No favorite pairs added yet.</span>';
        return;
    }
    elements.favoritePairsCurrent.innerHTML = favoritePairs.map(symbol => `
        <button type="button" class="favorite-tag" data-symbol="${symbol}" title="Remove ${symbol}">
            <span>${symbol}</span>
            <i class="fas fa-times"></i>
        </button>
    `).join('');
}

function renderFavoritePairOptions() {
    if (!elements.favoritePairsOptions) return;
    if (!favoritePairOptions.length) {
        elements.favoritePairsOptions.innerHTML = '<div class="favorites-empty">No pair options available right now.</div>';
        return;
    }

    const optionMap = buildFavoritePairOptionMap();
    let currentGroup = '';
    const parts = [];
    Array.from(optionMap.values()).forEach(option => {
        if (option.group !== currentGroup) {
            currentGroup = option.group;
            parts.push(`<div class="favorites-empty" style="padding: 6px 2px 0;">${currentGroup}</div>`);
        }
        const symbol = option.symbol;
        const isSavedFavorite = favoritePairs.includes(symbol);
        const checked = pendingFavoriteSelections.has(symbol) || isSavedFavorite;
        parts.push(`
            <div class="favorites-option">
                <label>
                    <input type="checkbox" data-symbol="${symbol}" ${checked ? 'checked' : ''} ${isSavedFavorite ? 'disabled' : ''}>
                    <span>${symbol}</span>
                </label>
                <span class="favorites-option-meta">${isSavedFavorite ? 'Saved' : `${Number(option.price_change_pct || 0).toFixed(2)}%`}</span>
            </div>
        `);
    });
    elements.favoritePairsOptions.innerHTML = parts.join('');
}

function syncFavoritePairsUi() {
    if (elements.favoritePairsEnabled && !elements.favoritePairsEnabled.matches(':focus')) {
        elements.favoritePairsEnabled.checked = favoritePairsEnabled;
    }
    if (elements.favoritePairsSummary) {
        elements.favoritePairsSummary.textContent = favoritePairsEnabled
            ? 'Favorite pair trading is enabled. Your selected pairs can bypass the daily growth filter and will still require bullish momentum and strategy confirmation.'
            : 'Favorite pairs are saved per email. Enable the toggle to let your selected spot pairs bypass the normal daily growth filter while still respecting strategy and momentum checks.';
    }
    renderFavoritePairTags();
    renderFavoritePairOptions();
}

function setTimeSlotsStatus(message, isError = false) {
    if (!elements.timeSlotsStatus) return;
    elements.timeSlotsStatus.textContent = message || '';
    elements.timeSlotsStatus.style.color = isError ? '#ff9a9a' : 'var(--text-secondary)';
}

function parseTimeToMinutes(value) {
    const text = String(value || '').trim();
    const parts = text.split(':');
    if (parts.length !== 2) return null;
    const hour = Number(parts[0]);
    const minute = Number(parts[1]);
    if (!Number.isInteger(hour) || !Number.isInteger(minute)) return null;
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
    return (hour * 60) + minute;
}

function formatSlotTimeLabel(value) {
    const minutes = parseTimeToMinutes(value);
    if (minutes === null) return value || '--:--';
    const hour24 = Math.floor(minutes / 60);
    const minute = minutes % 60;
    const suffix = hour24 >= 12 ? 'PM' : 'AM';
    const hour12 = hour24 % 12 || 12;
    return `${hour12}:${String(minute).padStart(2, '0')} ${suffix}`;
}

function slotSegments(slot) {
    const start = parseTimeToMinutes(slot.start);
    const end = parseTimeToMinutes(slot.end);
    if (start === null || end === null || start === end) return [];
    if (start < end) return [[start, end]];
    return [[start, 1440], [0, end]];
}

function hasOverlappingSlots(slots) {
    const segments = slots.flatMap(slotSegments).sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
    let previousEnd = -1;
    for (const [start, end] of segments) {
        if (start < previousEnd) return true;
        previousEnd = Math.max(previousEnd, end);
    }
    return false;
}

function syncTimeSlotsUi() {
    if (elements.timeSlotsEnabled && !elements.timeSlotsEnabled.matches(':focus')) {
        elements.timeSlotsEnabled.checked = timeSlotsEnabled;
    }
    if (elements.timeSlotsSummary) {
        elements.timeSlotsSummary.textContent = timeSlotsEnabled
            ? 'Time slot trading is enabled. Bot trading toggles automatically for your slots across all days.'
            : 'When disabled, trading follows your normal manual Bot Enabled control.';
    }
    if (!elements.timeSlotsList) return;
    if (!timeSlots.length) {
        elements.timeSlotsList.innerHTML = '<div class="time-slot-empty">No time slots added yet.</div>';
        return;
    }
    elements.timeSlotsList.innerHTML = timeSlots.map((slot, index) => `
        <div class="time-slot-item">
            <strong>${formatSlotTimeLabel(slot.start)} - ${formatSlotTimeLabel(slot.end)}</strong>
            <button class="btn outline small" data-remove-slot="${index}">Remove</button>
        </div>
    `).join('');
}

function renderBotClock(botClock) {
    if (!elements.timeSlotBotClock) return;
    if (!botClock || !botClock.local_time) {
        elements.timeSlotBotClock.textContent = 'Bot Time: --';
        return;
    }
    const zone = botClock.timezone || 'local';
    elements.timeSlotBotClock.textContent = `Bot Time: ${botClock.local_time} (${zone})`;
}

async function loadTimeSlots() {
    if (!isAuthenticated && authRequired) return;
    try {
        const response = await fetch(`${API_URL}/user/time-slots`);
        if (response.status === 401) {
            lockApp('Please login to continue.');
            return;
        }
        if (response.status === 405) {
            throw new Error('Time-slot API is not available in this backend build. Please restart/update the app backend.');
        }
        if (!response.ok) {
            throw new Error('Failed to load time slot settings.');
        }
        const payload = await response.json();
        timeSlotsEnabled = Boolean(payload.enabled);
        timeSlots = Array.isArray(payload.slots) ? payload.slots : [];
        syncTimeSlotsUi();
        setTimeSlotsStatus(`Time slot settings loaded for ${currentUserEmail || 'this email'}.`);
    } catch (error) {
        console.error('Time slots load failed:', error);
        setTimeSlotsStatus(error.message || 'Failed to load time slot settings.', true);
    }
}

async function saveTimeSlots(payload, successMessage) {
    const response = await fetch(`${API_URL}/user/time-slots`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 405) {
        throw new Error('Time-slot saving is not available in this backend build. Please restart/update the app backend.');
    }
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to save time slot settings.');
    }
    const saved = result.time_slots || {};
    timeSlotsEnabled = Boolean(saved.enabled);
    timeSlots = Array.isArray(saved.slots) ? saved.slots : [];
    syncTimeSlotsUi();
    if (successMessage) {
        setTimeSlotsStatus(successMessage);
    }
    await updateDashboard();
}

async function loadTradingPreferences() {
    if (!isAuthenticated && authRequired) return;
    try {
        const response = await fetch(`${API_URL}/user/trading-preferences`);
        if (response.status === 401) {
            lockApp('Please login to continue.');
            return;
        }
        if (!response.ok) {
            throw new Error('Failed to load favorite pair settings.');
        }
        const preferences = await response.json();
        favoritePairsEnabled = Boolean(preferences.favorite_pairs_enabled);
        favoritePairs = Array.isArray(preferences.favorite_pairs) ? preferences.favorite_pairs : [];
        pendingFavoriteSelections = new Set();
        syncFavoritePairsUi();
        setFavoritePairsStatus(`Favorite pair settings loaded for ${currentUserEmail || 'this email'}.`);
    } catch (error) {
        console.error('Favorite settings load failed:', error);
        setFavoritePairsStatus(error.message || 'Failed to load favorite pair settings.', true);
    }
}

async function loadFavoritePairOptions() {
    if (!isAuthenticated && authRequired) return;
    try {
        const response = await fetch(`${API_URL}/market/pair-options`);
        if (response.status === 401) {
            lockApp('Please login to continue.');
            return;
        }
        if (!response.ok) {
            throw new Error('Failed to load pair options.');
        }
        const result = await response.json();
        favoritePairOptions = Array.isArray(result.options) ? result.options : [];
        renderFavoritePairOptions();
    } catch (error) {
        console.error('Favorite pair options load failed:', error);
        setFavoritePairsStatus(error.message || 'Failed to load pair options.', true);
    }
}

async function saveTradingPreferences(payload, successMessage) {
    const response = await fetch(`${API_URL}/user/trading-preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to save favorite pair settings.');
    }
    const preferences = result.preferences || {};
    favoritePairsEnabled = Boolean(preferences.favorite_pairs_enabled);
    favoritePairs = Array.isArray(preferences.favorite_pairs) ? preferences.favorite_pairs : [];
    pendingFavoriteSelections = new Set();
    syncFavoritePairsUi();
    if (successMessage) {
        setFavoritePairsStatus(successMessage);
    }
    await updateDashboard();
}

async function saveApiConfig() {
    const saveMode = elements.apiModeSelect?.value || selectedDashboardMode || 'test';
    const payload = {
        preferred_mode: saveMode,
        test: {
            api_key: elements.testApiKey?.value || '',
            api_secret: elements.testApiSecret?.value || ''
        },
        real: {
            api_key: elements.realApiKey?.value || '',
            api_secret: elements.realApiSecret?.value || ''
        }
    };

    const response = await fetch(`${API_URL}/user/api-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to save API key settings.');
    }
    await loadApiConfig();
}

async function submitPassword(password, email) {
    const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, email })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (response.status === 403) {
            pendingVerificationEmail = email;
            if (elements.verifyEmailLabel) {
                elements.verifyEmailLabel.textContent = email;
            }
            setAuthPanel('verify', result.detail || 'Verification code required.');
        }
        throw new Error(result.detail || 'Access denied.');
    }
    currentUserEmail = result.email || '';
    if (elements.modeUserEmail) {
        elements.modeUserEmail.textContent = currentUserEmail || '-';
    }
    updateAccessState(result.user?.access || null);
    updateSubscriptionUi(result.subscription || result.user?.subscription || null);
    unlockApp(true);
    lastReportRefreshAt = 0;
    await loadApiConfig();
    await loadTradingPreferences();
    await loadFavoritePairOptions();
    await loadTimeSlots();
    await refreshServerIpBadge();
}

async function registerUser(email, password) {
    const response = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Registration failed.');
    }
    pendingVerificationEmail = result.email || email;
    if (elements.verifyEmailLabel) {
        elements.verifyEmailLabel.textContent = pendingVerificationEmail;
    }
    setAuthPanel('verify');
}

async function verifyRegistrationCode(email, code) {
    const response = await fetch(`${API_URL}/auth/verify-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Verification failed.');
    }
    currentUserEmail = result.email || email;
    if (elements.modeUserEmail) {
        elements.modeUserEmail.textContent = currentUserEmail || '-';
    }
    updateAccessState(result.user?.access || null);
    updateSubscriptionUi(result.user?.subscription || null);
    unlockApp(true);
    await loadApiConfig();
    await loadTradingPreferences();
    await loadFavoritePairOptions();
    await loadTimeSlots();
    await refreshServerIpBadge();
}

async function resendRegistrationCode(email) {
    const response = await fetch(`${API_URL}/auth/resend-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to resend code.');
    }
    return result;
}

async function logoutUser() {
    try {
        await fetch(`${API_URL}/auth/logout`, { method: 'POST' });
    } catch (error) {
        console.error('Logout failed:', error);
    }
    currentUserEmail = '';
    selectedDashboardMode = '';
    pendingVerificationEmail = '';
    currentSubscription = null;
    currentAccessState = null;
    savedApiCredentialState = {
        test: { hasKey: false, hasSecret: false },
        real: { hasKey: false, hasSecret: false }
    };
    updateSubscriptionUi(null);
    if (elements.serverIpBadge) {
        elements.serverIpBadge.textContent = 'Current IP: login required';
        elements.serverIpBadge.title = '';
    }
    lockApp('Login with your email and password to continue.');
}

async function selectDashboardMode(mode) {
    const selectedMode = mode === 'real' ? 'real' : 'test';
    if (selectedMode === 'real') {
        const subscription = await refreshBillingStatus();
        if (!subscription?.active && !currentAccessState?.real_mode_enabled) {
            await startStripeCheckout();
            return;
        }
    }
    const result = await sendUpdate({ account_mode: selectedMode });
    if (elements.apiModeSelect) {
        elements.apiModeSelect.value = selectedMode;
    }
    syncModeSpecificUi(selectedMode);
    document.body.classList.remove('auth-locked');
    lastReportRefreshAt = 0;
    await loadApiConfig();
    await updateDashboard();
    await updatePerformanceReport(selectedReportRange);
    return result;
}

function setModeEntryButtonsLoading(activeMode = '', loading = false) {
    const isReal = activeMode === 'real';
    if (elements.enterRealModeBtn) {
        elements.enterRealModeBtn.disabled = loading;
        elements.enterRealModeBtn.textContent = loading && isReal
            ? 'Processing...'
            : (currentSubscription?.active || currentAccessState?.real_mode_enabled ? 'Enter Real Mode' : 'Unlock Real Dashboard');
    }
    if (elements.enterTestModeBtn) {
        elements.enterTestModeBtn.disabled = loading;
        elements.enterTestModeBtn.textContent = loading && !isReal
            ? 'Processing...'
            : 'Enter Test Dashboard';
    }
}

async function startStripeCheckout() {
    const response = await fetch(`${API_URL}/billing/create-checkout-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'real' })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to start Stripe checkout.');
    }
    if (result.status === 'already_active') {
        updateSubscriptionUi(result.subscription || null);
        setAuthPanel('mode');
        return;
    }
    if (!result.checkout_url) {
        throw new Error('Stripe checkout URL was not returned.');
    }
    window.location.href = result.checkout_url;
}

async function updateDashboard() {
    if (!isAuthenticated && authRequired) return;
    try {
        const response = await fetch(`${API_URL}/status`);
        if (response.status === 401) {
            lockApp('Please login to continue.');
            return;
        }
        if (!response.ok) throw new Error("Server offline");
        const data = await response.json();
        const activeMode = selectedDashboardMode || data.account_mode || data.settings.account_mode || 'test';

        if (elements.apiModeSelect && !elements.apiModeSelect.matches(':focus')) {
            elements.apiModeSelect.value = activeMode;
        }
        syncModeSpecificUi(activeMode);
        updateSubscriptionUi(data.subscription || data.user?.subscription || currentSubscription);

        if (lastLoadedReport && lastLoadedReport.account_mode !== data.account_mode) {
            lastReportRefreshAt = 0;
        }
        updatePerformanceReport(selectedReportRange);

        // Calculate active PnL to update balance dynamically
        let activePnl = 0;
        if (data.active_trades) {
            Object.values(data.active_trades).forEach(trade => {
                activePnl += (trade.pnl || 0);
            });
        }

        // Update basic info
        const totalDynamicBalance = data.balance + activePnl;
        elements.balance.innerHTML = `${totalDynamicBalance.toFixed(2)} <small id="quote-asset">${data.quote_asset}</small>`;
        if (elements.freeBalance) {
            elements.freeBalance.innerText = data.free_balance.toFixed(2);
        }
        if (data.bot_enabled) {
            elements.currentActivity.innerText = data.current_activity || "Bot ready. Waiting for spot momentum signals...";
            elements.currentActivity.style.color = "var(--text-primary)";
        } else if (data.current_activity) {
            elements.currentActivity.innerText = data.current_activity;
            elements.currentActivity.style.color = "#ff9a9a";
        } else {
            elements.currentActivity.innerText = "Bot is disabled. Enable bot trading to start.";
            elements.currentActivity.style.color = "#ff9a9a";
        }

        // Sync local controls if they aren't being touched
        if (!elements.riskSlider.matches(':active')) {
            elements.riskSlider.value = data.settings.risk;
            elements.riskValue.innerText = Math.round(data.settings.risk);
        }
        if (!elements.modeSelect.matches(':focus')) {
            elements.modeSelect.value = data.settings.mode;
        }
        if (!elements.testBalanceInput.matches(':focus') && data.settings.test_balance !== null) {
            elements.testBalanceInput.placeholder = `Current: $${Math.floor(data.settings.test_balance)}`;
        }
        if (typeof data.settings.time_slots_enabled === 'boolean') {
            timeSlotsEnabled = Boolean(data.settings.time_slots_enabled);
        }
        if (Array.isArray(data.settings.time_slots)) {
            timeSlots = data.settings.time_slots;
        }
        syncTimeSlotsUi();
        renderBotClock(data.bot_clock);

        // Sync Bot Enabled Select
        if (!elements.botEnabledSelect.matches(':focus')) {
            elements.botEnabledSelect.value = data.bot_enabled.toString();
        }

        // Stats
        elements.totalPnl.innerText = `$${data.total_pnl.toFixed(2)}`;
        elements.totalPnl.className = data.total_pnl >= 0 ? 'pnl plus' : 'pnl minus';
        elements.totalTrades.innerText = data.closed_trades_count;

        if (elements.totalCommissions) {
            elements.totalCommissions.innerText = `$${(data.total_commission_paid || 0).toFixed(2)}`;
        }

        const activeCount = Object.keys(data.active_trades).length;
        elements.currentHoldings.innerText = activeCount;
        if (elements.closeAllTradesBtn) {
            elements.closeAllTradesBtn.title = activeCount === 0 ? 'No active trades right now. Click to log close request.' : 'Close all active trades';
        }
        if (elements.closeProfitTradesBtn) {
            const hasProfitTrades = Object.values(data.active_trades || {}).some(trade => Number(trade.pnl || 0) > 0);
            elements.closeProfitTradesBtn.title = hasProfitTrades ? 'Close profitable active trades' : 'No profitable active trades right now. Click to log close request.';
        }
        if (elements.closeLossTradesBtn) {
            const hasLossTrades = Object.values(data.active_trades || {}).some(trade => Number(trade.pnl || 0) < 0);
            elements.closeLossTradesBtn.title = hasLossTrades ? 'Close losing active trades' : 'No losing active trades right now. Click to log close request.';
        }

        // Active Trades
        if (activeCount > 0) {
            elements.activeTradesList.innerHTML = '';
            Object.values(data.active_trades).forEach(trade => {
                const entryPrice = Number(trade.entry_price || 0);
                const stopPrice = Number(trade.stop_loss_price || 0);
                const targetPct = Number(trade.profit_target_pct || 0);
                const explicitTarget = Number(trade.profit_target_price || 0);
                const targetPrice = explicitTarget > 0 ? explicitTarget : (entryPrice > 0 && targetPct > 0 ? entryPrice * (1 + targetPct) : 0);
                const tradeAmount = Number(trade.amount || 0);
                const pnlValue = Number(trade.pnl || 0);
                const currentPrice = tradeAmount > 0 ? entryPrice + (pnlValue / tradeAmount) : entryPrice;
                const targetText = targetPrice > 0 ? `TP: $${targetPrice.toFixed(4)} | ` : '';
                const currentPriceText = currentPrice > 0 ? `CP: $${currentPrice.toFixed(4)} | ` : '';
                const item = document.createElement('div');
                item.className = 'trade-item';
                item.innerHTML = `
                    <div class="trade-coin">
                        <div class="coin-icon">${trade.symbol.substring(0, 1)}</div>
                        <div class="coin-info">
                            <div class="name">${trade.symbol} <span class="close-action" style="font-size:10px; opacity:0.6; cursor:pointer;" onclick="closeTrade('${trade.symbol}')" title="Force Close Position">(Close)</span></div>
                            <div class="price">${(trade.amount).toFixed(4)} coins @ $${trade.entry_price.toFixed(4)}</div>
                        </div>
                    </div>
                    <div class="trade-perf">
                        <div class="pnl ${(trade.pnl || 0) >= 0 ? 'plus' : 'minus'}">
                            ${(trade.pnl || 0) >= 0 ? '+' : ''}$${(trade.pnl || 0).toFixed(4)}
                        </div>
                        <div class="price">${currentPriceText}${targetText}SL: $${stopPrice.toFixed(4)}</div>
                    </div>
                `;

                // Clicking trade opens chart modal
                item.style.cursor = 'pointer';
                item.onclick = (e) => {
                    if (e.target.closest('.close-action')) return;
                    openTVModal(trade.symbol);
                };

                elements.activeTradesList.appendChild(item);
            });
        } else {
            elements.activeTradesList.innerHTML = '<div class="empty-state">No active trades</div>';
        }

        // History Trades
        if (data.recent_trades && data.recent_trades.length > 0) {
            elements.historyTradesList.innerHTML = '';
            data.recent_trades.forEach(trade => {
                const item = document.createElement('div');
                item.className = 'trade-item';
                item.innerHTML = `
                    <div class="trade-coin">
                        <div class="coin-icon" style="background: rgba(255,255,255,0.1); color: var(--text-primary);">${trade.symbol.substring(0, 1)}</div>
                        <div class="coin-info">
                            <div class="name">${trade.symbol}</div>
                            <div class="price">Entry: $${trade.entry_price.toFixed(2)} | Exit: $${(trade.exit_price || 0).toFixed(2)}</div>
                        </div>
                    </div>
                    <div class="trade-perf">
                        <div class="pnl ${(trade.pnl || 0) >= 0 ? 'plus' : 'minus'}">
                            ${(trade.pnl || 0) >= 0 ? '+' : ''}$${(trade.pnl || 0).toFixed(4)}
                        </div>
                        <div class="price">${trade.status.toUpperCase()}</div>
                    </div>
                `;
                item.style.cursor = 'pointer';
                item.onclick = () => openTVModal(trade.symbol);
                elements.historyTradesList.appendChild(item);
            });
        } else {
            elements.historyTradesList.innerHTML = '<div class="empty-state">No closed trades yet</div>';
        }

        // Logs
        elements.logsContainer.innerHTML = '';
        data.logs.slice().reverse().forEach(log => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerText = log;
            elements.logsContainer.appendChild(entry);
        });

        // Uptime: treat enabled bot as active even if bot_running flag lags.
        const botActive = Boolean(data.bot_running || data.bot_enabled);
        if (botActive) {
            elements.botUptime.innerText = formatUptimeFromEpoch(data.start_time || data.last_update);
        } else {
            elements.botUptime.innerText = '00:00:00';
        }

    } catch (error) {
        console.error("Dashboard update failed:", error);
    }
}

// Navigation Logic removed for single page scroll
// Theme Persist & Toggle
const savedTheme = localStorage.getItem('bot-theme');
if (savedTheme === 'light') {
    document.body.classList.add('light-mode');
    if (elements.themeToggle) elements.themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
} else {
    if (elements.themeToggle) elements.themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
}
applyFallbackIcons();

if (elements.themeToggle) {
    elements.themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('light-mode');
        const isLight = document.body.classList.contains('light-mode');
        localStorage.setItem('bot-theme', isLight ? 'light' : 'dark');
        elements.themeToggle.innerHTML = isLight ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
        applyFallbackIcons();
    });
}

// Update Settings
async function sendUpdate(payload) {
    try {
        const response = await fetch(`${API_URL}/update_settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || "Update failed");
        }
        return result;
    } catch (e) {
        console.error("Update failed", e);
        throw e;
    }
}

elements.riskSlider.addEventListener('input', (e) => {
    elements.riskValue.innerText = parseInt(e.target.value);
});

elements.riskSlider.addEventListener('change', (e) => {
    sendUpdate({ risk: parseFloat(e.target.value) });
});

elements.modeSelect.addEventListener('change', (e) => {
    sendUpdate({ mode: e.target.value });
});

if (elements.apiModeSelect) {
    elements.apiModeSelect.disabled = true;
}

if (elements.saveApiConfigBtn) {
    elements.saveApiConfigBtn.addEventListener('click', () => {
        openConfirmModal({
            title: 'Save API Keys',
            message: `Save these API key changes for ${currentUserEmail || 'this email'}?`,
            confirmLabel: 'Save Keys',
            onConfirm: async () => {
                try {
                    elements.saveApiConfigBtn.disabled = true;
                    elements.saveApiConfigBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
                    await saveApiConfig();
                    if (elements.apiConfigStatus) {
                        elements.apiConfigStatus.textContent = `API keys saved for ${currentUserEmail || 'this email'}.`;
                    }
                } catch (error) {
                    if (elements.apiConfigStatus) {
                        elements.apiConfigStatus.textContent = error.message || 'Failed to save API key settings.';
                    }
                } finally {
                    elements.saveApiConfigBtn.disabled = false;
                    syncModeSpecificUi(elements.apiModeSelect?.value || selectedDashboardMode || 'test');
                }
            }
        });
    });
}

if (elements.favoritePairsDropdownBtn) {
    elements.favoritePairsDropdownBtn.addEventListener('click', () => {
        const isVisible = elements.favoritePairsDropdown?.style.display === 'block';
        if (elements.favoritePairsDropdown) {
            elements.favoritePairsDropdown.style.display = isVisible ? 'none' : 'block';
        }
    });
}

if (elements.favoritePairsOptions) {
    elements.favoritePairsOptions.addEventListener('change', (event) => {
        const checkbox = event.target;
        if (!checkbox.matches('input[type="checkbox"][data-symbol]')) return;
        const symbol = checkbox.dataset.symbol;
        if (!symbol) return;
        if (checkbox.checked) {
            pendingFavoriteSelections.add(symbol);
        } else {
            pendingFavoriteSelections.delete(symbol);
        }
    });
}

if (elements.favoritePairsAddBtn) {
    elements.favoritePairsAddBtn.addEventListener('click', async () => {
        const mergedPairs = Array.from(new Set([...favoritePairs, ...pendingFavoriteSelections]));
        if (!mergedPairs.length) {
            setFavoritePairsStatus('Select at least one pair to add to favorites.', true);
            return;
        }
        try {
            elements.favoritePairsAddBtn.disabled = true;
            await saveTradingPreferences({
                favorite_pairs_enabled: elements.favoritePairsEnabled?.checked || false,
                favorite_pairs: mergedPairs,
            }, 'Favorite pair list updated.');
            if (elements.favoritePairsDropdown) {
                elements.favoritePairsDropdown.style.display = 'none';
            }
        } catch (error) {
            setFavoritePairsStatus(error.message || 'Failed to update favorite pairs.', true);
        } finally {
            elements.favoritePairsAddBtn.disabled = false;
        }
    });
}

if (elements.favoritePairsEnabled) {
    elements.favoritePairsEnabled.addEventListener('change', async (event) => {
        try {
            await saveTradingPreferences({
                favorite_pairs_enabled: event.target.checked,
                favorite_pairs: favoritePairs,
            }, event.target.checked ? 'Favorite pair trading enabled.' : 'Favorite pair trading disabled.');
        } catch (error) {
            event.target.checked = !event.target.checked;
            favoritePairsEnabled = event.target.checked;
            syncFavoritePairsUi();
            setFavoritePairsStatus(error.message || 'Failed to update favorite pair toggle.', true);
        }
    });
}

if (elements.favoritePairsCurrent) {
    elements.favoritePairsCurrent.addEventListener('click', (event) => {
        const badge = event.target.closest('.favorite-tag');
        if (!badge) return;
        const symbol = badge.dataset.symbol;
        if (!symbol) return;
        openConfirmModal({
            title: 'Remove Favorite Pair',
            message: `Remove ${symbol} from your favorite pair list?`,
            confirmLabel: 'Remove Pair',
            onConfirm: async () => {
                await saveTradingPreferences({
                    favorite_pairs_enabled: favoritePairsEnabled,
                    favorite_pairs: favoritePairs.filter(pair => pair !== symbol),
                }, `${symbol} removed from favorite pairs.`);
            }
        });
    });
}

if (elements.timeSlotsEnabled) {
    elements.timeSlotsEnabled.addEventListener('change', async (event) => {
        try {
            await saveTimeSlots({
                enabled: event.target.checked,
                slots: timeSlots,
            }, event.target.checked ? 'Time slot trading enabled.' : 'Time slot trading disabled.');
        } catch (error) {
            event.target.checked = !event.target.checked;
            timeSlotsEnabled = event.target.checked;
            syncTimeSlotsUi();
            setTimeSlotsStatus(error.message || 'Failed to update time slot toggle.', true);
        }
    });
}

if (elements.timeSlotAddBtn) {
    elements.timeSlotAddBtn.addEventListener('click', async () => {
        const start = (elements.timeSlotStart?.value || '').trim();
        const end = (elements.timeSlotEnd?.value || '').trim();
        const startMinutes = parseTimeToMinutes(start);
        const endMinutes = parseTimeToMinutes(end);
        if (startMinutes === null || endMinutes === null) {
            setTimeSlotsStatus('Please use valid start and end times.', true);
            return;
        }
        if (startMinutes === endMinutes) {
            setTimeSlotsStatus('Start and end time cannot be the same.', true);
            return;
        }

        const candidate = { start, end };
        const deduped = timeSlots.filter(slot => !(slot.start === start && slot.end === end));
        const nextSlots = [...deduped, candidate];
        if (hasOverlappingSlots(nextSlots)) {
            setTimeSlotsStatus('Slot overlaps with an existing range. Please adjust times.', true);
            return;
        }

        try {
            elements.timeSlotAddBtn.disabled = true;
            await saveTimeSlots({
                enabled: elements.timeSlotsEnabled?.checked || false,
                slots: nextSlots,
            }, `Slot ${formatSlotTimeLabel(start)} - ${formatSlotTimeLabel(end)} added.`);
        } catch (error) {
            setTimeSlotsStatus(error.message || 'Failed to add time slot.', true);
        } finally {
            elements.timeSlotAddBtn.disabled = false;
        }
    });
}

if (elements.timeSlotsList) {
    elements.timeSlotsList.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-remove-slot]');
        if (!button) return;
        const index = Number(button.dataset.removeSlot);
        if (!Number.isInteger(index) || index < 0 || index >= timeSlots.length) return;

        const removed = timeSlots[index];
        const nextSlots = timeSlots.filter((_, slotIndex) => slotIndex !== index);
        try {
            await saveTimeSlots({
                enabled: elements.timeSlotsEnabled?.checked || false,
                slots: nextSlots,
            }, `Slot ${formatSlotTimeLabel(removed.start)} - ${formatSlotTimeLabel(removed.end)} removed.`);
        } catch (error) {
            setTimeSlotsStatus(error.message || 'Failed to remove time slot.', true);
        }
    });
}

document.addEventListener('click', (event) => {
    if (!elements.favoritePairsDropdown || !elements.favoritePairsDropdownBtn) return;
    const clickedInside = elements.favoritePairsDropdown.contains(event.target) || elements.favoritePairsDropdownBtn.contains(event.target);
    if (!clickedInside) {
        elements.favoritePairsDropdown.style.display = 'none';
    }
});

elements.botEnabledSelect.addEventListener('change', async (e) => {
    const nextEnabled = e.target.value === 'true';
    const previousValue = nextEnabled ? 'false' : 'true';
    const targetMode = selectedDashboardMode === 'real' ? 'real' : 'test';
    try {
        if (nextEnabled && !hasUsableKeysForMode(targetMode)) {
            throw new Error(targetMode === 'real'
                ? 'Please save your real Binance API key and secret before enabling the bot.'
                : 'Please save your test Binance API key and secret before enabling the bot.');
        }
        await sendUpdate({ bot_enabled: nextEnabled, account_mode: targetMode });
    } catch (error) {
        elements.botEnabledSelect.value = previousValue;
        const message = error.message || 'Failed to update bot state.';
        const lowered = message.toLowerCase();
        if (nextEnabled && (lowered.includes('api key') || lowered.includes('api secret') || lowered.includes('save your'))) {
            const isReal = targetMode === 'real';
            scrollToApiSectionWithMessage(
                isReal
                    ? 'Set your real API keys in Api Keys section below before enabling bot state.'
                    : 'Enter test API keys to run bot. Set your test API keys in Api Keys section below.',
                isReal ? 'real' : 'test'
            );
        } else {
            alert(message);
        }
        if (nextEnabled && selectedDashboardMode === 'real' && !currentSubscription?.active) {
            document.body.classList.add('auth-locked');
            setAuthPanel('billing', error.message || 'Real mode requires an active subscription.');
        }
    }
});

elements.resetBotBtn.addEventListener('click', async () => {
    if (confirm("Are you sure you want to reset all PnL and trade history?")) {
        try {
            await fetch(`${API_URL}/reset_bot`, { method: 'POST' });
            window.location.reload();
        } catch (e) {
            console.error("Reset failed", e);
        }
    }
});

elements.setBalanceBtn.addEventListener('click', () => {
    const val = parseFloat(elements.testBalanceInput.value);
    if (!isNaN(val)) {
        sendUpdate({ test_balance: val });
        elements.testBalanceInput.value = '';
    }
});

elements.testTradeBtn.addEventListener('click', async () => {
    try {
        elements.testTradeBtn.disabled = true;
        elements.testTradeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enforcing...';

        await fetch(`${API_URL}/test_trade`, { method: 'POST' });

        setTimeout(() => {
            elements.testTradeBtn.disabled = false;
            elements.testTradeBtn.innerHTML = '<i class="fas fa-play"></i> Enforce Best Setup';
        }, 2000);
    } catch (e) {
        console.error("Test trade failed", e);
    }
});

let currentCloseSymbol = null;
const confirmModal = document.getElementById('confirm-modal');
const modalTitle = document.getElementById('modal-title');
const modalCancelBtn = document.getElementById('modal-cancel-btn');
const modalConfirmBtn = document.getElementById('modal-confirm-btn');
const modalMessage = document.getElementById('modal-message');
let confirmModalAction = null;

function closeConfirmModal() {
    if (confirmModal) {
        confirmModal.style.display = 'none';
    }
    currentCloseSymbol = null;
    confirmModalAction = null;
}

function openConfirmModal({ title, message, confirmLabel, onConfirm }) {
    if (modalTitle) {
        modalTitle.innerText = title || 'Confirm Action';
    }
    if (modalMessage) {
        modalMessage.innerText = message || 'Are you sure you want to continue?';
    }
    if (modalConfirmBtn) {
        modalConfirmBtn.innerText = confirmLabel || 'Confirm';
    }
    confirmModalAction = onConfirm || null;
    if (confirmModal) {
        confirmModal.style.display = 'flex';
    }
}

function closeTrade(symbol) {
    currentCloseSymbol = symbol;
    openConfirmModal({
        title: 'Close Position',
        message: `Are you sure you want to market close ${symbol}?`,
        confirmLabel: 'Close Now',
        onConfirm: async () => {
            try {
                await fetch(`${API_URL}/close_trade/${currentCloseSymbol}`, { method: 'POST' });
            } catch (e) {
                console.error("Failed to close trade", e);
            }
            setTimeout(() => updateDashboard(), 1500);
        }
    });
}

async function closeTradesByScope(scope) {
    bulkCloseNotice = '';
    let result = null;
    try {
        const response = await fetch(`${API_URL}/close_trades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scope })
        });
        result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Failed to submit bulk close request.');
        }
        if (result.status === 'no_match') {
            bulkCloseNotice = `No matching active trades to close for ${scope}.`;
        } else if (result.status === 'triggered') {
            bulkCloseNotice = `Bulk close queued: ${result.count || 0} trade(s) for ${scope}.`;
        }
    } catch (e) {
        console.error("Failed to close trades by scope", e);
        bulkCloseNotice = e.message || 'Failed to submit bulk close request.';
    }
    if (bulkCloseNotice) {
        alert(bulkCloseNotice);
    }
    setTimeout(() => updateDashboard(), 1500);
    return result;
}

if (elements.closeAllTradesBtn) {
    elements.closeAllTradesBtn.addEventListener('click', () => {
        openConfirmModal({
            title: 'Close All Active Trades',
            message: 'Are you sure you want to close all active trades at market price?',
            confirmLabel: 'Close All',
            onConfirm: async () => closeTradesByScope('all')
        });
    });
}

if (elements.closeProfitTradesBtn) {
    elements.closeProfitTradesBtn.addEventListener('click', () => {
        openConfirmModal({
            title: 'Close Profit Trades',
            message: 'Close all currently profitable active trades?',
            confirmLabel: 'Close Profit',
            onConfirm: async () => closeTradesByScope('profit')
        });
    });
}

if (elements.closeLossTradesBtn) {
    elements.closeLossTradesBtn.addEventListener('click', () => {
        openConfirmModal({
            title: 'Close Loss Trades',
            message: 'Close all currently losing active trades?',
            confirmLabel: 'Close Loss',
            onConfirm: async () => closeTradesByScope('loss')
        });
    });
}

if (modalCancelBtn) {
    modalCancelBtn.addEventListener('click', () => {
        closeConfirmModal();
    });
}

if (modalConfirmBtn) {
    modalConfirmBtn.addEventListener('click', async () => {
        if (confirmModalAction) {
            try {
                await confirmModalAction();
            } catch (e) {
                console.error("Confirm action failed", e);
            }
        }
        closeConfirmModal();
    });
}

// TradingView Modal Code
const tvModal = document.getElementById('tv-modal');
const tvModalTitle = document.getElementById('tv-modal-title');
const tvModalClose = document.getElementById('tv-modal-close');
const tvWidgetContainer = document.getElementById('tv-widget-container');
let tradingViewScriptPromise = null;

function normalizeChartSymbol(symbol) {
    return String(symbol || '')
        .trim()
        .toUpperCase()
        .replace(/\s+/g, '')
        .replace(/-/g, '/');
}

function getTradingViewSymbol(symbol) {
    const normalized = normalizeChartSymbol(symbol);
    if (!normalized) return '';
    if (normalized.includes('/')) {
        const [base, quote] = normalized.split('/');
        if (base && quote) {
            return `BINANCE:${base}${quote}`;
        }
    }

    const knownQuotes = ['USDT', 'FDUSD', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB', 'TRY'];
    const matchedQuote = knownQuotes.find((quote) => normalized.endsWith(quote) && normalized.length > quote.length);
    if (!matchedQuote) {
        return `BINANCE:${normalized}`;
    }
    const base = normalized.slice(0, -matchedQuote.length);
    return `BINANCE:${base}${matchedQuote}`;
}

function ensureTradingViewScript() {
    if (window.TradingView?.widget) {
        return Promise.resolve();
    }
    if (tradingViewScriptPromise) {
        return tradingViewScriptPromise;
    }

    tradingViewScriptPromise = new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-tradingview-script="true"]');
        if (existing) {
            if (window.TradingView?.widget || existing.dataset.loaded === 'true') {
                resolve();
                return;
            }
            existing.addEventListener('load', () => resolve(), { once: true });
            existing.addEventListener('error', () => reject(new Error('TradingView script failed to load.')), { once: true });
            return;
        }

        const script = document.createElement('script');
        script.src = 'https://s3.tradingview.com/tv.js';
        script.async = true;
        script.dataset.tradingviewScript = 'true';
        script.onload = () => {
            script.dataset.loaded = 'true';
            resolve();
        };
        script.onerror = () => reject(new Error('TradingView script failed to load.'));
        document.head.appendChild(script);
    }).catch((error) => {
        tradingViewScriptPromise = null;
        throw error;
    });

    return tradingViewScriptPromise;
}

function openTVModal(symbol) {
    const normalized = normalizeChartSymbol(symbol);
    if (tvModalTitle) tvModalTitle.innerText = `Live Chart: ${normalized || symbol}`;
    if (tvModal) tvModal.style.display = 'flex';
    if (tvWidgetContainer) {
        tvWidgetContainer.innerHTML = '<div class="empty-state" style="padding: 48px 20px;">Loading chart...</div>';
    }
    loadTradeChart(symbol);
}

async function loadTradeChart(symbol) {
    if (!tvWidgetContainer) return;
    try {
        await ensureTradingViewScript();
        if (!window.TradingView?.widget) {
            throw new Error('TradingView widget is unavailable.');
        }

        const tradingViewSymbol = getTradingViewSymbol(symbol);
        if (!tradingViewSymbol) {
            throw new Error('Invalid symbol for chart.');
        }

        tvWidgetContainer.innerHTML = `
            <div class="report-meta" style="margin-bottom: 14px;">
                Source: Binance via TradingView. Pair: ${tradingViewSymbol.replace('BINANCE:', '')}
            </div>
            <div id="tv-widget-inner" style="width: 100%; height: 100%; min-height: 520px;"></div>
        `;

        new window.TradingView.widget({
            autosize: true,
            symbol: tradingViewSymbol,
            interval: '15',
            timezone: 'Etc/UTC',
            theme: 'dark',
            style: '1',
            locale: 'en',
            enable_publishing: false,
            hide_top_toolbar: false,
            hide_legend: false,
            allow_symbol_change: false,
            container_id: 'tv-widget-inner',
        });
        return;
    } catch (widgetError) {
        console.error('TradingView widget failed, falling back to internal chart:', widgetError);
    }

    try {
        if (!tvWidgetContainer) return;
        const response = await fetch(`${API_URL}/chart/${encodeURIComponent(symbol)}`);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || 'Failed to load chart.');
        }
        renderTradeChart(payload);
    } catch (error) {
        console.error('Chart load failed:', error);
        tvWidgetContainer.innerHTML = `<div class="empty-state" style="padding: 48px 20px;">${error.message || 'Chart unavailable.'}</div>`;
    }
}

function renderTradeChart(payload) {
    if (!tvWidgetContainer) return;
    const candles = Array.isArray(payload?.candles) ? payload.candles : [];
    const trade = payload?.trade || null;
    if (!candles.length) {
        tvWidgetContainer.innerHTML = '<div class="empty-state" style="padding: 48px 20px;">No candle data available.</div>';
        return;
    }

    const width = 1080;
    const height = 540;
    const padding = { top: 24, right: 118, bottom: 42, left: 18 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const prices = [];
    candles.forEach((candle) => {
        prices.push(Number(candle.high || 0), Number(candle.low || 0));
    });
    ['entry_price', 'stop_loss_price', 'hard_stop_price', 'profit_target_price', 'quick_profit_price', 'high_water_price', 'exit_price'].forEach((key) => {
        if (trade && Number(trade[key] || 0) > 0) {
            prices.push(Number(trade[key]));
        }
    });
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const span = Math.max(maxPrice - minPrice, maxPrice * 0.01, 1e-9);
    const paddedMin = Math.max(0, minPrice - (span * 0.08));
    const paddedMax = maxPrice + (span * 0.08);
    const candleWidth = Math.max(3, Math.min(10, plotWidth / Math.max(candles.length * 1.8, 1)));

    const yForPrice = (price) => {
        const normalized = (Number(price || 0) - paddedMin) / Math.max(paddedMax - paddedMin, 1e-9);
        return padding.top + plotHeight - (normalized * plotHeight);
    };
    const xForIndex = (index) => padding.left + (plotWidth * index / Math.max(candles.length - 1, 1));

    const grid = [0, 0.25, 0.5, 0.75, 1].map((step) => {
        const y = padding.top + (plotHeight * step);
        const price = paddedMax - ((paddedMax - paddedMin) * step);
        return `
            <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(148,163,184,0.14)" stroke-width="1" />
            <text x="${width - padding.right + 10}" y="${y + 4}" fill="rgba(226,232,240,0.8)" font-size="11">${formatChartPrice(price)}</text>
        `;
    }).join('');

    const candlesSvg = candles.map((candle, index) => {
        const x = xForIndex(index);
        const open = Number(candle.open || 0);
        const close = Number(candle.close || 0);
        const high = Number(candle.high || 0);
        const low = Number(candle.low || 0);
        const bullish = close >= open;
        const color = bullish ? '#22c55e' : '#ef4444';
        const bodyTop = yForPrice(Math.max(open, close));
        const bodyBottom = yForPrice(Math.min(open, close));
        const bodyHeight = Math.max(2, bodyBottom - bodyTop);
        return `
            <line x1="${x}" y1="${yForPrice(high)}" x2="${x}" y2="${yForPrice(low)}" stroke="${color}" stroke-width="1.4" />
            <rect x="${x - (candleWidth / 2)}" y="${bodyTop}" width="${candleWidth}" height="${bodyHeight}" rx="1.2" fill="${color}" />
        `;
    }).join('');

    const overlays = trade ? [
        ['entry_price', '#22c55e', 'Entry'],
        ['stop_loss_price', '#ef4444', 'Stop'],
        ['hard_stop_price', '#f97316', 'Hard SL'],
        ['quick_profit_price', '#38bdf8', 'Quick TP'],
        ['profit_target_price', '#a78bfa', 'Target'],
        ['high_water_price', '#facc15', 'Peak'],
        ['exit_price', '#f8fafc', 'Exit'],
    ].map(([key, color, label]) => {
        const value = Number(trade[key] || 0);
        if (!(value > 0)) return '';
        const y = yForPrice(value);
        return `
            <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="${color}" stroke-width="1.4" stroke-dasharray="6 4" opacity="0.9" />
            <circle cx="${width - padding.right - 10}" cy="${y}" r="4" fill="${color}" />
            <text x="${width - padding.right + 10}" y="${y - 7}" fill="${color}" font-size="11">${label}</text>
        `;
    }).join('') : '';

    const summary = trade ? `
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 12px;">
            <div class="report-stat-card"><span>Status</span><strong>${trade.status || 'unknown'}</strong></div>
            <div class="report-stat-card"><span>Entry</span><strong>${formatChartPrice(trade.entry_price)}</strong></div>
            <div class="report-stat-card"><span>Stop</span><strong>${formatChartPrice(trade.stop_loss_price)}</strong></div>
            <div class="report-stat-card"><span>Target</span><strong>${formatChartPrice(trade.profit_target_price)}</strong></div>
            <div class="report-stat-card"><span>Exit</span><strong>${trade.exit_price ? formatChartPrice(trade.exit_price) : '-'}</strong></div>
            <div class="report-stat-card"><span>Net</span><strong>${formatMoney(trade.net_pnl || trade.pnl || 0)}</strong></div>
        </div>
        <div class="report-meta" style="margin-bottom: 14px;">
            ${trade.exit_reason ? `Close reason: ${trade.exit_reason}. ` : ''}Opened ${formatTimestamp(trade.opened_at)}${trade.closed_at ? `, closed ${formatTimestamp(trade.closed_at)}.` : '.'}
        </div>
    ` : '<div class="report-meta" style="margin-bottom: 14px;">Live candles loaded, but no matching trade setup metadata was found for this symbol.</div>';

    tvWidgetContainer.innerHTML = `
        ${summary}
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Trade setup chart" style="width:100%; height:100%; min-height:420px; background: linear-gradient(180deg, rgba(15,23,42,0.96), rgba(2,6,23,0.92)); border-radius: 18px;">
            ${grid}
            ${candlesSvg}
            ${overlays}
        </svg>
    `;
}

if (tvModalClose) {
    tvModalClose.addEventListener('click', () => {
        tvModal.style.display = 'none';
        tvWidgetContainer.innerHTML = '';
    });
}

document.querySelectorAll('.report-range-btn').forEach(button => {
    button.addEventListener('click', () => {
        selectedReportRange = button.dataset.range || 'overall';
        lastReportRefreshAt = 0;
        updatePerformanceReport(selectedReportRange);
    });
});

document.querySelectorAll('.report-download-btn').forEach(button => {
    button.addEventListener('click', () => {
        downloadPerformanceReport(button.dataset.range || selectedReportRange);
    });
});

document.querySelectorAll('.report-trade-filter-btn').forEach(button => {
    button.addEventListener('click', () => {
        selectedReportTradeFilter = button.dataset.tradeFilter || 'all';
        document.querySelectorAll('.report-trade-filter-btn').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tradeFilter === selectedReportTradeFilter);
        });
        if (lastLoadedReport) {
            renderReport(lastLoadedReport);
        }
    });
});

if (elements.authToggle && elements.authPassword) {
    elements.authToggle.addEventListener('click', () => {
        const visible = elements.authPassword.type === 'text';
        elements.authPassword.type = visible ? 'password' : 'text';
        elements.authToggle.innerHTML = `<i class="far fa-${visible ? 'eye' : 'eye-slash'}"></i>`;
        applyFallbackIcons();
    });
}

if (elements.authForm) {
    elements.authForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const password = (elements.authPassword?.value || '').trim();
        const email = (elements.authEmail?.value || '').trim();
        if (!password) {
            setAuthPanel('login', 'Password is required.');
            return;
        }
        if (!email) {
            setAuthPanel('login', 'Email is required.');
            return;
        }
        try {
            if (elements.authSubmit) {
                elements.authSubmit.disabled = true;
                elements.authSubmit.textContent = 'Logging in...';
            }
            await submitPassword(password, email);
        } catch (error) {
            if (elements.authPanelVerify?.style.display === 'block') {
                setAuthPanel('verify', error.message || 'Verification code required.');
            } else {
                setAuthPanel('login', error.message || 'Access denied.');
            }
        } finally {
            if (elements.authSubmit) {
                elements.authSubmit.disabled = false;
                elements.authSubmit.textContent = 'Login';
            }
        }
    });
}

if (elements.showRegisterBtn) {
    elements.showRegisterBtn.addEventListener('click', () => setAuthPanel('register'));
}

if (elements.openDocsModalBtn) {
    elements.openDocsModalBtn.addEventListener('click', () => {
        openInfoModal('Documentation', LOGIN_DOCUMENTATION_HTML);
    });
}

if (elements.openRiskModalBtn) {
    elements.openRiskModalBtn.addEventListener('click', () => {
        openInfoModal('Risk Warning', RISK_WARNING_HTML);
    });
}

if (elements.infoModalClose) {
    elements.infoModalClose.addEventListener('click', closeInfoModal);
}

if (elements.infoModal) {
    elements.infoModal.addEventListener('click', (event) => {
        if (event.target === elements.infoModal) {
            closeInfoModal();
        }
    });
}

if (elements.showLoginBtn) {
    elements.showLoginBtn.addEventListener('click', () => setAuthPanel('login'));
}

if (elements.verifyBackBtn) {
    elements.verifyBackBtn.addEventListener('click', () => setAuthPanel('register'));
}

if (elements.registerForm) {
    elements.registerForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const email = (elements.registerEmail?.value || '').trim();
        const password = (elements.registerPassword?.value || '').trim();
        if (!email) {
            setAuthPanel('register', 'Email is required.');
            return;
        }
        if (password.length < 6) {
            setAuthPanel('register', 'Password must be at least 6 characters.');
            return;
        }
        try {
            if (elements.registerSubmit) {
                elements.registerSubmit.disabled = true;
                elements.registerSubmit.textContent = 'Sending code...';
            }
            await registerUser(email, password);
        } catch (error) {
            setAuthPanel('register', error.message || 'Registration failed.');
        } finally {
            if (elements.registerSubmit) {
                elements.registerSubmit.disabled = false;
                elements.registerSubmit.textContent = 'Send 4-Digit Code';
            }
        }
    });
}

if (elements.verifyForm) {
    elements.verifyForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const code = (elements.verifyCode?.value || '').trim();
        if (code.length !== 4) {
            setAuthPanel('verify', 'Please enter the 4-digit code.');
            return;
        }
        try {
            if (elements.verifySubmit) {
                elements.verifySubmit.disabled = true;
                elements.verifySubmit.textContent = 'Verifying...';
            }
            await verifyRegistrationCode(pendingVerificationEmail, code);
        } catch (error) {
            setAuthPanel('verify', error.message || 'Verification failed.');
        } finally {
            if (elements.verifySubmit) {
                elements.verifySubmit.disabled = false;
                elements.verifySubmit.textContent = 'Verify & Continue';
            }
        }
    });
}

if (elements.resendCodeBtn) {
    elements.resendCodeBtn.addEventListener('click', async () => {
        try {
            elements.resendCodeBtn.disabled = true;
            await resendRegistrationCode(pendingVerificationEmail);
            setAuthPanel('verify', 'A new code has been sent to your email.');
        } catch (error) {
            setAuthPanel('verify', error.message || 'Failed to resend code.');
        } finally {
            elements.resendCodeBtn.disabled = false;
        }
    });
}

if (elements.billingCardNumber) {
    elements.billingCardNumber.addEventListener('input', () => {
        const digits = elements.billingCardNumber.value.replace(/\D+/g, '').slice(0, 16);
        elements.billingCardNumber.value = digits.replace(/(\d{4})(?=\d)/g, '$1 ').trim();
    });
}

if (elements.billingExpiry) {
    elements.billingExpiry.addEventListener('input', () => {
        const digits = elements.billingExpiry.value.replace(/\D+/g, '').slice(0, 4);
        if (digits.length <= 2) {
            elements.billingExpiry.value = digits;
        } else {
            elements.billingExpiry.value = `${digits.slice(0, 2)}/${digits.slice(2)}`;
        }
    });
}

if (elements.billingCvc) {
    elements.billingCvc.addEventListener('input', () => {
        elements.billingCvc.value = elements.billingCvc.value.replace(/\D+/g, '').slice(0, 4);
    });
}

if (elements.billingZip) {
    elements.billingZip.addEventListener('input', () => {
        elements.billingZip.value = elements.billingZip.value.replace(/[^A-Za-z0-9 -]/g, '').slice(0, 10);
    });
}

if (elements.enterTestModeBtn) {
    elements.enterTestModeBtn.addEventListener('click', async () => {
        try {
            setModeEntryButtonsLoading('test', true);
            await selectDashboardMode('test');
        } catch (error) {
            setAuthPanel('mode', error.message || 'Failed to enter test mode.');
        } finally {
            setModeEntryButtonsLoading('test', false);
        }
    });
}

if (elements.enterRealModeBtn) {
    elements.enterRealModeBtn.addEventListener('click', async () => {
        try {
            setModeEntryButtonsLoading('real', true);
            await selectDashboardMode('real');
        } catch (error) {
            setAuthPanel('mode', error.message || 'Failed to open real mode.');
        } finally {
            setModeEntryButtonsLoading('real', false);
        }
    });
}

if (elements.billingBackBtn) {
    elements.billingBackBtn.addEventListener('click', () => setAuthPanel('mode'));
}

if (elements.startCheckoutBtn) {
    elements.startCheckoutBtn.addEventListener('click', async () => {
        try {
            elements.startCheckoutBtn.disabled = true;
            elements.startCheckoutBtn.textContent = 'Opening Stripe...';
            await startStripeCheckout();
        } catch (error) {
            setAuthPanel('billing', error.message || 'Failed to start checkout.');
        } finally {
            elements.startCheckoutBtn.disabled = false;
            elements.startCheckoutBtn.textContent = 'Continue To Stripe Checkout';
        }
    });
}

if (elements.modeLogoutBtn) {
    elements.modeLogoutBtn.addEventListener('click', logoutUser);
}

if (elements.logoutBtn) {
    elements.logoutBtn.addEventListener('click', logoutUser);
}

if (elements.backToModeBtn) {
    elements.backToModeBtn.addEventListener('click', async () => {
        document.body.classList.add('auth-locked');
        setAuthPanel('mode');
        await refreshBillingStatus();
    });
}

async function bootApp() {
    applyFallbackIcons();
    try {
        await checkAuthStatus();
        if (isAuthenticated || !authRequired) {
            await loadTradingPreferences();
            await loadFavoritePairOptions();
            await loadTimeSlots();
            const urlParams = new URLSearchParams(window.location.search);
            const billingState = urlParams.get('billing');
            if (billingState === 'success') {
                await refreshBillingStatus();
                setAuthPanel('mode', 'Payment successful. Click Enter Real Mode to continue.');
            }
            if (billingState) {
                window.history.replaceState({}, document.title, window.location.pathname);
            }
            if (!document.body.classList.contains('auth-locked')) {
                await updateDashboard();
                await updatePerformanceReport();
            }
        }
    } catch (error) {
        if (elements.serverIpBadge) {
            elements.serverIpBadge.textContent = 'Current IP: unavailable';
            elements.serverIpBadge.title = '';
        }
        lockApp('Unable to verify access. Please retry.');
        console.error('App boot failed:', error);
    }

    if (!dashboardInterval) {
        dashboardInterval = setInterval(updateDashboard, 1000);
    }
}

bootApp();
