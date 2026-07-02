const API_BASE = "http://127.0.0.1:8000";
let authToken = localStorage.getItem("dnh_token") || "";
let currentRole = localStorage.getItem("dnh_role") || "";
let currentUsername = localStorage.getItem("dnh_username") || "";

// Chart instances
let chartQuarterly = null;
let chartRegional = null;
let chartSegment = null;

// DOM Elements
const loginScreen = document.getElementById("login-screen");
const appContainer = document.getElementById("app-container");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const userDisplayName = document.getElementById("user-display-name");
const userRole = document.getElementById("user-role");
const btnLogout = document.getElementById("btn-logout");

// Views
const viewDashboard = document.getElementById("view-dashboard");
const viewDebt = document.getElementById("view-debt");
const viewChatbot = document.getElementById("view-chatbot");
const pageTitle = document.getElementById("page-title");

// Menu items
const menuDashboard = document.getElementById("menu-dashboard");
const menuDebt = document.getElementById("menu-debt");
const menuChatbot = document.getElementById("menu-chatbot");

// On Load
document.addEventListener("DOMContentLoaded", () => {
    if (authToken) {
        showApp();
    } else {
        showLogin();
    }
});

// Login Form Submit
loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    
    loginError.style.display = "none";
    
    try {
        const response = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || "Đăng nhập thất bại");
        }
        
        // Save auth data
        authToken = data.token;
        currentRole = data.role;
        currentUsername = data.username;
        localStorage.setItem("dnh_token", authToken);
        localStorage.setItem("dnh_role", currentRole);
        localStorage.setItem("dnh_username", currentUsername);
        
        showApp();
    } catch (err) {
        loginError.innerText = err.message;
        loginError.style.display = "block";
    }
});

// Logout Button
btnLogout.addEventListener("click", () => {
    authToken = "";
    currentRole = "";
    currentUsername = "";
    localStorage.removeItem("dnh_token");
    localStorage.removeItem("dnh_role");
    localStorage.removeItem("dnh_username");
    showLogin();
});

function showLogin() {
    loginScreen.style.display = "flex";
    appContainer.style.display = "none";
}

function showApp() {
    loginScreen.style.display = "none";
    appContainer.style.display = "flex";
    
    userDisplayName.innerText = currentUsername.toUpperCase();
    userRole.innerText = currentRole;
    
    // Default load dashboard
    switchView("dashboard");
}

// Navigation Logic
menuDashboard.addEventListener("click", (e) => { e.preventDefault(); switchView("dashboard"); });
menuDebt.addEventListener("click", (e) => { e.preventDefault(); switchView("debt"); });
menuChatbot.addEventListener("click", (e) => { e.preventDefault(); switchView("chatbot"); });

function switchView(viewName) {
    // Update active menu class
    [menuDashboard, menuDebt, menuChatbot].forEach(item => item.classList.remove("active"));
    
    // Hide all views
    viewDashboard.style.display = "none";
    viewDebt.style.display = "none";
    viewChatbot.style.display = "none";
    
    if (viewName === "dashboard") {
        menuDashboard.classList.add("active");
        viewDashboard.style.display = "block";
        pageTitle.innerText = "Dashboard Tổng Quan";
        loadDashboardData();
    } else if (viewName === "debt") {
        menuDebt.classList.add("active");
        viewDebt.style.display = "block";
        pageTitle.innerText = "Hạn Mức Công Nợ Cảnh Báo";
        loadDebtData();
    } else if (viewName === "chatbot") {
        menuChatbot.classList.add("active");
        viewChatbot.style.display = "block";
        pageTitle.innerText = "AI Chatbot Truy Vấn Tự Nhiên";
    }
}

// Format Money Helper
function formatVND(amount) {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
}

// LOAD DASHBOARD DATA
async function loadDashboardData() {
    try {
        // Fetch stats card data
        const statsRes = await fetch(`${API_BASE}/api/dashboard/stats`, {
            headers: { "Authorization": `Bearer ${authToken}` }
        });
        if (!statsRes.ok) throw new Error("Could not load stats");
        const stats = await statsRes.json();
        
        document.getElementById("stat-revenue").innerText = formatVND(stats.total_receivable);
        document.getElementById("stat-orders").innerText = formatVND(stats.total_overdue);
        document.getElementById("stat-customers").innerText = stats.total_customers.toLocaleString();
        document.getElementById("stat-contracts").innerText = stats.total_inventory_items.toLocaleString();
        
        // Fetch chart data
        const chartRes = await fetch(`${API_BASE}/api/dashboard/charts`, {
            headers: { "Authorization": `Bearer ${authToken}` }
        });
        if (!chartRes.ok) throw new Error("Could not load charts");
        const charts = await chartRes.json();
        
        renderCharts(charts);
    } catch (err) {
        console.error("Dashboard error:", err);
    }
}

function renderCharts(data) {
    // 1. Phai thu theo kenh (Bar)
    const labelsQuarterly = data.receivable_by_channel.map(item => item.sales_channel || "Khác");
    const revenuesQuarterly = data.receivable_by_channel.map(item => item.total_balance);
    
    if (chartQuarterly) chartQuarterly.destroy();
    chartQuarterly = new Chart(document.getElementById("chart-quarterly"), {
        type: 'bar',
        data: {
            labels: labelsQuarterly,
            datasets: [{
                label: 'Tổng nợ phải thu (VND)',
                data: revenuesQuarterly,
                backgroundColor: ['#8b5cf6', '#3b82f6', '#10b981'],
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            }
        }
    });

    // 2. Doanh so KPI theo vung (Doughnut)
    const labelsRegional = data.kpi_by_region.map(item => item.area_code === 'MN' ? 'Miền Nam' : (item.area_code === 'MB' ? 'Miền Bắc' : (item.area_code === 'MB2' ? 'Miền Bắc 2' : item.area_code)));
    const revenuesRegional = data.kpi_by_region.map(item => item.total_month_sale);
    
    if (chartRegional) chartRegional.destroy();
    chartRegional = new Chart(document.getElementById("chart-regional"), {
        type: 'doughnut',
        data: {
            labels: labelsRegional,
            datasets: [{
                data: revenuesRegional,
                backgroundColor: ['#3b82f6', '#10b981', '#ec4899', '#f59e0b'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#94a3b8', font: { family: 'Outfit' } } }
            }
        }
    });

    // 3. Tuoi no qua han (Bar)
    const labelsSegment = data.overdue_aging.map(item => item.bucket);
    const revenuesSegment = data.overdue_aging.map(item => item.amount);
    
    if (chartSegment) chartSegment.destroy();
    chartSegment = new Chart(document.getElementById("chart-segment"), {
        type: 'bar',
        data: {
            labels: labelsSegment,
            datasets: [{
                label: 'Số tiền quá hạn',
                data: revenuesSegment,
                backgroundColor: ['#ec4899', '#ef4444', '#f59e0b', '#dc2626'],
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            }
        }
    });
}

// LOAD DEBT ALERTS
async function loadDebtData() {
    const tableBody = document.querySelector("#debt-alerts-table tbody");
    tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> Đang tải dữ liệu cảnh báo...</td></tr>`;
    
    try {
        const response = await fetch(`${API_BASE}/api/debt/alerts`, {
            headers: { "Authorization": `Bearer ${authToken}` }
        });
        if (!response.ok) throw new Error("Could not load debt alerts");
        const data = await response.json();
        
        tableBody.innerHTML = "";
        
        if (data.alerts.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--success);"><i class="fa-solid fa-circle-check"></i> Không có khách hàng nào nợ quá hạn!</td></tr>`;
            return;
        }
        
        data.alerts.forEach(alert => {
            let badgeText = "Quá hạn nợ";
            let badgeClass = "danger";
            
            let breakdown = [];
            if (alert.overdue_1_15 > 0) breakdown.push(`1-15d: ${formatVND(alert.overdue_1_15)}`);
            if (alert.overdue_15_30 > 0) breakdown.push(`15-30d: ${formatVND(alert.overdue_15_30)}`);
            if (alert.overdue_30_45 > 0) breakdown.push(`30-45d: ${formatVND(alert.overdue_30_45)}`);
            if (alert.overdue_gt_45 > 0) breakdown.push(`>45d: ${formatVND(alert.overdue_gt_45)}`);
            let breakdownStr = breakdown.join(" | ") || "N/A";
            
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${alert.customer_code}</strong></td>
                <td>${alert.customer_name}</td>
                <td>${alert.sales_channel || 'OTC'}</td>
                <td style="font-weight:500;">${formatVND(alert.balance_end)}</td>
                <td style="color: var(--danger); font-weight:600;">${formatVND(alert.total_overdue)}</td>
                <td style="font-size:12px; color:#94a3b8; font-family: monospace;">${breakdownStr}</td>
                <td><span class="badge ${badgeClass}">${badgeText}</span></td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (err) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger);"><i class="fa-solid fa-circle-exclamation"></i> Lỗi: ${err.message}</td></tr>`;
    }
}

// CHATBOT INTERACTION
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessagesBox = document.getElementById("chat-messages-box");
const suggestBtns = document.querySelectorAll(".suggest-btn");
const aiModeBadge = document.getElementById("ai-mode-badge");

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = chatInput.value.trim();
    if (!q) return;
    submitChatQuestion(q);
    chatInput.value = "";
});

// Click Suggestion Buttons
suggestBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        const q = btn.getAttribute("data-q");
        submitChatQuestion(q);
    });
});

async function submitChatQuestion(question) {
    // Append user message
    appendMessage(question, "user");
    
    // Append loader placeholder
    const loaderId = appendLoader();
    
    try {
        const response = await fetch(`${API_BASE}/api/chatbot/query`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "Authorization": `Bearer ${authToken}`
            },
            body: JSON.stringify({ question })
        });
        
        const data = await response.json();
        removeLoader(loaderId);
        
        if (!response.ok) {
            throw new Error(data.detail || "Lỗi truy vấn chatbot");
        }
        
        // Update AI mode badge
        aiModeBadge.innerText = data.mode;
        
        // Append response
        appendBotResponse(data);
    } catch (err) {
        removeLoader(loaderId);
        appendMessage(`Lỗi: ${err.message}`, "bot");
    }
}

function appendMessage(text, sender) {
    const msg = document.createElement("div");
    msg.classList.add("message", sender);
    msg.innerHTML = `
        <div class="message-avatar"><i class="fa-solid ${sender === 'bot' ? 'fa-robot' : 'fa-user'}"></i></div>
        <div class="message-bubble">${text}</div>
    `;
    chatMessagesBox.appendChild(msg);
    chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
}

function appendLoader() {
    const id = "loader-" + Date.now();
    const msg = document.createElement("div");
    msg.classList.add("message", "bot");
    msg.id = id;
    msg.innerHTML = `
        <div class="message-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-bubble loader-msg">
            AI đang phân tích dữ liệu <div class="dot-flashing"></div>
        </div>
    `;
    chatMessagesBox.appendChild(msg);
    chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
    return id;
}

function removeLoader(id) {
    const loader = document.getElementById(id);
    if (loader) loader.remove();
}

function appendBotResponse(data) {
    const msg = document.createElement("div");
    msg.classList.add("message", "bot");
    
    let bubbleContent = `<p>${data.answer}</p>`;
    
    // Add SQL details
    if (data.sql) {
        bubbleContent += `<details><summary><i class="fa-solid fa-code"></i> Xem câu lệnh SQL do AI sinh</summary><code>${data.sql}</code></details>`;
    }
    
    // Add table if rows are returned
    if (data.data && data.data.length > 0) {
        let tableHtml = "<table><thead><tr>";
        data.columns.forEach(col => {
            tableHtml += `<th>${col}</th>`;
        });
        tableHtml += "</tr></thead><tbody>";
        
        data.data.forEach(row => {
            tableHtml += "tr";
            tableHtml += "<tr>";
            data.columns.forEach(col => {
                let val = row[col];
                if (typeof val === 'number' && (col.includes('revenue') || col.includes('budget') || col.includes('amount') || col.includes('debt'))) {
                    val = formatVND(val);
                }
                tableHtml += `<td>${val}</td>`;
            });
            tableHtml += "</tr>";
        });
        tableHtml += "</tbody></table>";
        bubbleContent += tableHtml;
    }
    
    msg.innerHTML = `
        <div class="message-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-bubble">${bubbleContent}</div>
    `;
    chatMessagesBox.appendChild(msg);
    chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
}
