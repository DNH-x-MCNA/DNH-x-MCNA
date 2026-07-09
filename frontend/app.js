// Rỗng = gọi API cùng origin với trang đang mở (backend/main.py mount frontend/ ngay tại "/").
// KHÔNG hard-code "127.0.0.1:8000" — khi deploy lên máy dùng chung, "127.0.0.1" trong trình
// duyệt của người khác luôn trỏ về CHÍNH máy họ, không phải máy chạy backend, làm login/gọi API
// luôn thất bại. Để rỗng thì fetch(`${API_BASE}/api/...`) tự thành "/api/..." — trình duyệt tự
// resolve đúng theo địa chỉ trang đang mở, dùng được cả khi chạy dev (127.0.0.1) lẫn khi deploy.
const API_BASE = "";
let authToken = localStorage.getItem("dnh_token") || "";
let currentRole = localStorage.getItem("dnh_role") || "";
let currentUsername = localStorage.getItem("dnh_username") || "";

// Câu hỏi có sẵn từ link ngoài (vd nút "Xem chi tiết trên Chatbot" trong card Teams,
// ?q=<câu hỏi đã encode> — xem src/notifier.py::_chatbot_deep_link). Tự hỏi luôn sau khi đăng
// nhập/vào app, không bắt người dùng gõ lại — RBAC vẫn theo đúng tài khoản họ tự đăng nhập.
let pendingQuestion = new URLSearchParams(window.location.search).get("q") || "";

// ---- Lưu lịch sử chat để F5/tải lại trang không mất hội thoại ----
// Lưu theo từng user vào localStorage; khôi phục vào DOM khi vào app.
let chatHistory = [];
let chatRestored = false;
const CHAT_MAX_ENTRIES = 50;

function chatKey() { return "dnh_chat_" + (currentUsername || "guest"); }

function saveChat() {
    if (chatHistory.length > CHAT_MAX_ENTRIES) chatHistory = chatHistory.slice(-CHAT_MAX_ENTRIES);
    try {
        localStorage.setItem(chatKey(), JSON.stringify(chatHistory));
    } catch (e) {
        // Vượt quota (thường do ảnh biểu đồ base64) → bỏ ảnh ở các lượt cũ rồi thử lại
        chatHistory = chatHistory.map(en => {
            if (en.kind === "bot" && en.data && en.data.chart_base64) {
                const d = Object.assign({}, en.data); delete d.chart_base64;
                return Object.assign({}, en, { data: d });
            }
            return en;
        });
        try { localStorage.setItem(chatKey(), JSON.stringify(chatHistory)); }
        catch (e2) {
            chatHistory = chatHistory.slice(-15);
            try { localStorage.setItem(chatKey(), JSON.stringify(chatHistory)); } catch (e3) {}
        }
    }
}

function clearChatHistory() {
    chatHistory = [];
    try { localStorage.removeItem(chatKey()); } catch (e) {}
}

function restoreChat() {
    if (chatRestored) return;
    chatRestored = true;
    try { chatHistory = JSON.parse(localStorage.getItem(chatKey()) || "[]"); }
    catch (e) { chatHistory = []; }
    chatHistory.forEach(en => {
        if (en.kind === "user") appendMessage(en.text, "user");
        else if (en.kind === "botText") appendMessage(en.text, "bot");
        else if (en.kind === "bot" && en.data) appendBotResponse(en.data);
    });
}

// DOM Elements
const loginScreen = document.getElementById("login-screen");
const appContainer = document.getElementById("app-container");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const userDisplayName = document.getElementById("user-display-name");
const userRole = document.getElementById("user-role");
const btnLogout = document.getElementById("btn-logout");

// Views
const viewChatbot = document.getElementById("view-chatbot");
const pageTitle = document.getElementById("page-title");

// Menu items
const menuChatbot = document.getElementById("menu-chatbot");

// On Load
document.addEventListener("DOMContentLoaded", () => {
    // Khôi phục giao diện Sáng/Tối đã lưu
    const savedTheme = localStorage.getItem("dnh_theme") || "light";
    const themeToggle = document.getElementById("theme-toggle");
    if (savedTheme === "dark") {
        document.body.classList.add("dark-theme");
        if (themeToggle) themeToggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
    } else {
        if (themeToggle) themeToggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
    }

    if (authToken) {
        showApp();
    } else {
        showLogin();
    }
});

// Theme Switcher Event Listener
const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
    themeToggle.addEventListener("click", () => {
        document.body.classList.toggle("dark-theme");
        const isDark = document.body.classList.contains("dark-theme");
        localStorage.setItem("dnh_theme", isDark ? "dark" : "light");
        themeToggle.innerHTML = isDark ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
    });
}

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
    // KHÔNG xoá lịch sử chat đã lưu
    chatRestored = false;
    chatHistory = [];
    if (typeof chatMessagesBox !== "undefined" && chatMessagesBox) {
        while (chatMessagesBox.children.length > 1) {
            chatMessagesBox.removeChild(chatMessagesBox.lastChild);
        }
    }
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

    // Khôi phục lịch sử chat đã lưu
    restoreChat();

    // Default load chatbot view directly
    switchView("chatbot");

    // Nếu vào app kèm sẵn câu hỏi từ link ngoài -> tự hỏi luôn. Xoá param khỏi URL sau khi dùng
    // để F5/tải lại trang không hỏi lặp lại câu cũ.
    if (pendingQuestion) {
        submitChatQuestion(pendingQuestion);
        pendingQuestion = "";
        const url = new URL(window.location.href);
        url.searchParams.delete("q");
        window.history.replaceState({}, "", url);
    }
}

// Navigation Logic
menuChatbot.addEventListener("click", (e) => { e.preventDefault(); switchView("chatbot"); });

function switchView(viewName) {
    if (viewName === "chatbot") {
        menuChatbot.classList.add("active");
        viewChatbot.style.display = "block";
        pageTitle.innerText = "AI Chatbot Trợ Lý Phân Tích Dữ Liệu Dược Nam Hà";
    }
}

// Format Money Helper
function formatVND(amount) {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
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
    // Append user message + lưu lịch sử
    appendMessage(question, "user");
    chatHistory.push({ kind: "user", text: question });
    saveChat();

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

        // Lệnh reset hội thoại (backend trả mode "System") -> xoá luôn lịch sử đã lưu
        if (data.mode === "System") {
            clearChatHistory();
        } else {
            chatHistory.push({ kind: "bot", data: data });
            saveChat();
        }
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

    // Add chart image (server sends it inline as base64 PNG)
    if (data.chart_base64) {
        bubbleContent += `<img class="chat-chart" src="data:image/png;base64,${data.chart_base64}" alt="Biểu đồ phân tích">`;
    }

    // Add SQL details
    if (data.sql) {
        bubbleContent += `<details><summary><i class="fa-solid fa-code"></i> Xem câu lệnh SQL do AI sinh</summary><code>${data.sql}</code></details>`;
    }
    
    // Add table if rows are returned
    if (data.data && data.data.length > 0) {
        const tableId = `chat-table-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
        let tableHtml = `<table id="${tableId}"><thead><tr>`;
        data.columns.forEach((col, idx) => {
            tableHtml += `<th onclick="sortChatTable('${tableId}', ${idx})">${col}<span class="sort-indicator"></span></th>`;
        });
        tableHtml += "</tr><tr class=\"col-filter-row\">";
        data.columns.forEach((col, idx) => {
            tableHtml += `<th><input type="text" class="col-filter-input" placeholder="Lọc..." oninput="filterChatTable('${tableId}')" data-col-index="${idx}"></th>`;
        });
        tableHtml += "</tr></thead><tbody>";

        const MONEY_COL_PATTERN = /doanh thu|công nợ|nợ|giá trị|tiền|chỉ tiêu|thực đạt|dư nợ|thanh toán|revenue|budget|amount|debt|balance|target|value/i;
        data.data.forEach(row => {
            tableHtml += "<tr>";
            data.columns.forEach(col => {
                let raw = row[col];
                let val = raw;
                if (typeof val === 'number' && Number.isFinite(val)) {
                    if (MONEY_COL_PATTERN.test(col)) {
                        val = formatVND(val);
                    } else if (Math.abs(val) >= 1000) {
                        // Not detected as currency, but still a long number — group digits
                        // so it stays legible instead of one unbroken string of digits.
                        val = val.toLocaleString('vi-VN');
                    }
                }
                const rawAttr = String(raw === null || raw === undefined ? '' : raw).replace(/"/g, '&quot;');
                tableHtml += `<td data-raw="${rawAttr}">${val}</td>`;
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

function filterChatTable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const filterInputs = table.querySelectorAll(".col-filter-input");
    const filters = Array.from(filterInputs).map(input => ({
        colIndex: parseInt(input.dataset.colIndex, 10),
        value: input.value.trim().toLowerCase()
    })).filter(f => f.value !== "");

    const rows = table.querySelectorAll("tbody tr");
    rows.forEach(row => {
        const cells = row.children;
        const matches = filters.every(f => {
            const cell = cells[f.colIndex];
            return cell && cell.textContent.toLowerCase().includes(f.value);
        });
        row.style.display = matches ? "" : "none";
    });
}

function sortChatTable(tableId, colIndex) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));

    const isSameColumn = table.dataset.sortCol === String(colIndex);
    const newDir = isSameColumn && table.dataset.sortDir === "asc" ? "desc" : "asc";
    table.dataset.sortCol = colIndex;
    table.dataset.sortDir = newDir;

    rows.sort((rowA, rowB) => {
        const rawA = rowA.children[colIndex]?.dataset.raw ?? "";
        const rawB = rowB.children[colIndex]?.dataset.raw ?? "";
        const numA = parseFloat(rawA);
        const numB = parseFloat(rawB);
        let cmp;
        if (rawA !== "" && rawB !== "" && !isNaN(numA) && !isNaN(numB)) {
            cmp = numA - numB;
        } else {
            cmp = rawA.localeCompare(rawB, "vi");
        }
        return newDir === "asc" ? cmp : -cmp;
    });

    rows.forEach(row => tbody.appendChild(row));

    table.querySelectorAll("thead tr:first-child th").forEach((th, idx) => {
        const indicator = th.querySelector(".sort-indicator");
        if (!indicator) return;
        indicator.textContent = idx === colIndex ? (newDir === "asc" ? " ▲" : " ▼") : "";
    });
}

// ============================================================
//  MODAL: ĐỔI MẬT KHẨU
// ============================================================
const modalChangePw  = document.getElementById("modal-change-pw");
const changePwForm   = document.getElementById("change-pw-form");
const changepwError  = document.getElementById("changepw-error");
const changepwSuccess= document.getElementById("changepw-success");
const strengthFill   = document.getElementById("pw-strength-fill");
const strengthLabel  = document.getElementById("pw-strength-label");

function openChangePwModal() {
    changePwForm.reset();
    changepwError.classList.remove("visible");
    changepwError.textContent = "";
    changepwSuccess.classList.remove("visible");
    strengthFill.style.width = "0%";
    strengthFill.style.background = "";
    strengthLabel.textContent = "Nhập mật khẩu mới để xem độ mạnh";
    modalChangePw.classList.remove("hidden");
    document.getElementById("pw-old").focus();
}
function closeChangePwModal() {
    modalChangePw.classList.add("hidden");
}

document.getElementById("btn-open-change-pw").addEventListener("click", openChangePwModal);
document.getElementById("btn-close-change-pw").addEventListener("click", closeChangePwModal);
document.getElementById("btn-cancel-change-pw").addEventListener("click", closeChangePwModal);
// Đóng khi click overlay (ngoài card)
modalChangePw.addEventListener("click", (e) => { if (e.target === modalChangePw) closeChangePwModal(); });

// Show/hide password toggle
document.querySelectorAll(".btn-toggle-pw").forEach(btn => {
    btn.addEventListener("click", () => {
        const targetId = btn.dataset.target;
        const input = document.getElementById(targetId);
        const icon = btn.querySelector("i");
        if (!input) return;
        if (input.type === "password") {
            input.type = "text";
            icon.className = "fa-regular fa-eye-slash";
        } else {
            input.type = "password";
            icon.className = "fa-regular fa-eye";
        }
    });
});

// Password strength meter
function calcStrength(pw) {
    let score = 0;
    if (pw.length >= 8)  score++;
    if (pw.length >= 12) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    return score; // 0-5
}

document.getElementById("pw-new").addEventListener("input", (e) => {
    const pw = e.target.value;
    if (!pw) {
        strengthFill.style.width = "0%";
        strengthLabel.textContent = "Nhập mật khẩu mới để xem độ mạnh";
        return;
    }
    const score = calcStrength(pw);
    const levels = [
        { pct: "15%", color: "#ef4444", text: "Rất yếu" },
        { pct: "30%", color: "#f97316", text: "Yếu" },
        { pct: "55%", color: "#f59e0b", text: "Trung bình" },
        { pct: "78%", color: "#22c55e", text: "Mạnh" },
        { pct: "100%",color: "#10b981", text: "Rất mạnh 💪" },
    ];
    const lvl = levels[Math.min(score - 1, 4)] || levels[0];
    strengthFill.style.width  = lvl.pct;
    strengthFill.style.background = lvl.color;
    strengthLabel.textContent = `Độ mạnh: ${lvl.text}`;
});

// Submit đổi mật khẩu
changePwForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    changepwError.classList.remove("visible");
    changepwError.textContent = "";
    changepwSuccess.classList.remove("visible");

    const oldPw  = document.getElementById("pw-old").value;
    const newPw  = document.getElementById("pw-new").value;
    const cfmPw  = document.getElementById("pw-confirm").value;
    const submitBtn = document.getElementById("btn-submit-change-pw");

    // Client-side validation nhanh
    if (!oldPw || !newPw || !cfmPw) {
        changepwError.textContent = "Vui lòng điền đầy đủ tất cả các trường.";
        changepwError.classList.add("visible");
        return;
    }
    if (newPw !== cfmPw) {
        changepwError.textContent = "Mật khẩu mới và xác nhận mật khẩu không khớp.";
        changepwError.classList.add("visible");
        return;
    }
    if (newPw.length < 8) {
        changepwError.textContent = "Mật khẩu mới phải có ít nhất 8 ký tự.";
        changepwError.classList.add("visible");
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang xử lý...';

    try {
        const resp = await fetch(`${API_BASE}/api/auth/change-password`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${authToken}`
            },
            body: JSON.stringify({
                old_password: oldPw,
                new_password: newPw,
                confirm_password: cfmPw
            })
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Đổi mật khẩu thất bại");

        // Thành công
        changepwSuccess.classList.add("visible");
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Đã đổi thành công';

        // Tự động đăng xuất sau 2.5s để bắt buộc đăng nhập với mật khẩu mới
        setTimeout(() => {
            closeChangePwModal();
            btnLogout.click();
        }, 2500);

    } catch (err) {
        changepwError.textContent = err.message;
        changepwError.classList.add("visible");
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Xác nhận đổi';
    }
});

// ============================================================
//  MODAL: HƯỚNG DẪN SỬ DỤNG CHATBOT
// ============================================================
const modalGuide = document.getElementById("modal-guide");

function openGuideModal() {
    modalGuide.classList.remove("hidden");
}
function closeGuideModal() {
    modalGuide.classList.add("hidden");
}

document.getElementById("btn-open-guide").addEventListener("click", openGuideModal);
document.getElementById("btn-close-guide").addEventListener("click", closeGuideModal);
document.getElementById("btn-close-guide-bottom").addEventListener("click", closeGuideModal);
modalGuide.addEventListener("click", (e) => { if (e.target === modalGuide) closeGuideModal(); });

// Accordion toggle
function toggleGuideSection(id) {
    const section = document.getElementById(id);
    if (!section) return;
    section.classList.toggle("open");
}

// Guide chip click → đóng modal + gửi câu hỏi vào chat
function sendGuideChip(el) {
    // Lấy text, bỏ icon FontAwesome (textContent bao gồm cả text icon)
    const text = el.textContent.trim();
    closeGuideModal();
    // Đặt vào input rồi submit
    if (chatInput) {
        chatInput.value = text;
        submitChatQuestion(text);
        chatInput.value = "";
    }
}

// Phím Escape đóng modal đang mở
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        if (!modalChangePw.classList.contains("hidden")) closeChangePwModal();
        if (!modalGuide.classList.contains("hidden")) closeGuideModal();
    }
});

