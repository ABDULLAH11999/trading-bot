const API_URL = window.location.origin;

const adminEls = {
    loginView: document.getElementById('admin-login-view'),
    appView: document.getElementById('admin-app-view'),
    loginForm: document.getElementById('admin-login-form'),
    email: document.getElementById('admin-email'),
    password: document.getElementById('admin-password'),
    loginBtn: document.getElementById('admin-login-btn'),
    loginError: document.getElementById('admin-login-error'),
    logoutBtn: document.getElementById('admin-logout-btn'),
    navButtons: document.querySelectorAll('.admin-nav-btn'),
    usersTab: document.getElementById('admin-users-tab'),
    paymentsTab: document.getElementById('admin-payments-tab'),
    totalUsers: document.getElementById('stat-total-users'),
    paidUsers: document.getElementById('stat-paid-users'),
    totalPayments: document.getElementById('stat-total-payments'),
    realFee: document.getElementById('stat-real-fee'),
    userSearch: document.getElementById('admin-user-search'),
    paymentSearch: document.getElementById('admin-payment-search'),
    usersBody: document.getElementById('admin-users-body'),
    paymentsBody: document.getElementById('admin-payments-body')
};

let allUsers = [];
let allPayments = [];

function formatDateTime(ts) {
    if (!ts) return '-';
    return new Date(ts * 1000).toLocaleString();
}

function formatDate(ts) {
    if (!ts) return '-';
    return new Date(ts * 1000).toLocaleDateString();
}

function formatAmount(cents, currency = 'usd') {
    return `${currency.toUpperCase()} ${(Number(cents || 0) / 100).toFixed(2)}`;
}

function showAdminApp(isLoggedIn) {
    adminEls.loginView.style.display = isLoggedIn ? 'none' : 'grid';
    adminEls.appView.style.display = isLoggedIn ? 'grid' : 'none';
}

function setActiveTab(tabName) {
    adminEls.navButtons.forEach((button) => {
        button.classList.toggle('active', button.dataset.tab === tabName);
    });
    adminEls.usersTab.style.display = tabName === 'users' ? 'block' : 'none';
    adminEls.paymentsTab.style.display = tabName === 'payments' ? 'block' : 'none';
}

async function adminRequest(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || 'Request failed.');
    }
    return result;
}

function renderUsers(users) {
    adminEls.usersBody.innerHTML = users.length ? users.map((user) => `
        <tr>
            <td>${user.email}</td>
            <td><span class="pill ${user.is_active ? 'good' : 'bad'}">${user.is_active ? 'Active' : 'Inactive'}</span></td>
            <td>
                <span class="pill ${user.email_verified ? 'good' : (user.otp_bypass_allowed ? 'warn' : 'bad')}">
                    ${user.email_verified ? 'Verified' : (user.otp_bypass_allowed ? 'Admin Bypass' : 'OTP Required')}
                </span>
            </td>
            <td><span class="pill ${user.real_mode_enabled ? 'good' : 'warn'}">${user.real_mode_enabled ? 'Enabled' : 'Disabled'}</span></td>
            <td><span class="pill ${user.paid ? 'good' : 'warn'}">${user.paid ? 'Paid' : 'Not Paid'}</span></td>
            <td>${formatDate(user.subscription_end)}</td>
            <td>
                <div class="action-row">
                    <button class="mini-btn ${user.is_active ? 'warn' : 'good'}" data-email="${user.email}" data-action="toggle-active">
                        ${user.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    ${user.subscription_active ? `
                        <button class="mini-btn" type="button" disabled title="Active subscription already unlocks real mode">
                            Subscription Active
                        </button>
                    ` : `
                        <button class="mini-btn" data-email="${user.email}" data-action="toggle-real">
                            ${user.real_mode_enabled ? 'Disable Real' : 'Enable Real'}
                        </button>
                    `}
                </div>
            </td>
        </tr>
    `).join('') : '<tr><td colspan="7">No users found.</td></tr>';
}

function renderPayments(payments) {
    adminEls.paymentsBody.innerHTML = payments.length ? payments.map((payment) => `
        <tr>
            <td>${payment.email}</td>
            <td>${formatAmount(payment.amount_cents, payment.currency)}</td>
            <td>${formatDateTime(payment.paid_at)}</td>
            <td>${payment.payment_intent_id || '-'}</td>
            <td>${payment.subscription_id || '-'}</td>
        </tr>
    `).join('') : '<tr><td colspan="5">No payments found.</td></tr>';
}

function applyAdminFilters() {
    const userSearch = String(adminEls.userSearch?.value || '').trim().toLowerCase();
    const paymentSearch = String(adminEls.paymentSearch?.value || '').trim().toLowerCase();
    renderUsers(allUsers.filter((user) => !userSearch || user.email.toLowerCase().includes(userSearch)));
    renderPayments(allPayments.filter((payment) => !paymentSearch || payment.email.toLowerCase().includes(paymentSearch)));
}

async function loadAdminOverview() {
    const overview = await adminRequest(`${API_URL}/admin/overview`);
    adminEls.totalUsers.textContent = String(overview.stats.total_users || 0);
    adminEls.paidUsers.textContent = String(overview.stats.paid_users || 0);
    adminEls.totalPayments.textContent = String(overview.stats.total_payments || 0);
    adminEls.realFee.textContent = `$${Number(overview.real_mode_fee || 0).toFixed(0)}`;
}

async function loadAdminUsers() {
    const result = await adminRequest(`${API_URL}/admin/users`);
    allUsers = result.users || [];
    applyAdminFilters();
}

async function loadAdminPayments() {
    const result = await adminRequest(`${API_URL}/admin/payments`);
    allPayments = result.payments || [];
    applyAdminFilters();
}

async function refreshAdminData() {
    await loadAdminOverview();
    await loadAdminUsers();
    await loadAdminPayments();
}

async function bootAdmin() {
    try {
        const status = await adminRequest(`${API_URL}/admin/auth/status`);
        showAdminApp(Boolean(status.authenticated));
        if (status.authenticated) {
            await refreshAdminData();
        }
    } catch (error) {
        showAdminApp(false);
    }
}

adminEls.loginForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    adminEls.loginError.textContent = '';
    try {
        adminEls.loginBtn.disabled = true;
        await adminRequest(`${API_URL}/admin/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: adminEls.email.value.trim(),
                password: adminEls.password.value
            })
        });
        showAdminApp(true);
        await refreshAdminData();
    } catch (error) {
        adminEls.loginError.textContent = error.message || 'Login failed.';
    } finally {
        adminEls.loginBtn.disabled = false;
    }
});

adminEls.logoutBtn?.addEventListener('click', async () => {
    try {
        await adminRequest(`${API_URL}/admin/auth/logout`, { method: 'POST' });
    } catch (_) {
        // ignore
    }
    showAdminApp(false);
});

adminEls.navButtons.forEach((button) => {
    button.addEventListener('click', () => setActiveTab(button.dataset.tab || 'users'));
});

adminEls.usersBody?.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-email][data-action]');
    if (!button) return;
    const email = button.dataset.email;
    const action = button.dataset.action;
    const row = button.closest('tr');
    try {
        button.disabled = true;
        const payload = action === 'toggle-active'
            ? { is_active: button.textContent.trim() === 'Activate' }
            : { real_mode_enabled: button.textContent.trim() === 'Enable Real' };
        await adminRequest(`${API_URL}/admin/users/${encodeURIComponent(email)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        await refreshAdminData();
    } catch (error) {
        alert(error.message || 'Failed to update user.');
        if (row) row.classList.add('error');
    } finally {
        button.disabled = false;
    }
});

adminEls.userSearch?.addEventListener('input', applyAdminFilters);
adminEls.paymentSearch?.addEventListener('input', applyAdminFilters);

bootAdmin();
