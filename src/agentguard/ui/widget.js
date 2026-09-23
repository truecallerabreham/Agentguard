/**
 * AgentGuard Customer Support Embeddable Widget
 * Zero-dependency standalone JavaScript widget for e-commerce storefronts.
 * 
 * Usage:
 *   <script src="https://your-domain.com/widget.js" data-store-id="demo-store"></script>
 */

(function () {
    "use strict";

    // Prevent duplicate injection
    if (window.__AGENTGUARD_WIDGET_LOADED__) return;
    window.__AGENTGUARD_WIDGET_LOADED__ = true;

    // Discover configuration from script tag or window global
    const currentScript = document.currentScript || document.querySelector("script[src*='widget.js']");
    const scriptStoreId = currentScript ? currentScript.getAttribute("data-store-id") : null;
    const scriptApiBase = currentScript ? (currentScript.getAttribute("data-api-base") || "") : "";

    // Auto-discover API origin from currentScript.src if embedded on remote storefront
    let autoApiBase = "";
    try {
        if (currentScript && currentScript.src) {
            const parsedUrl = new URL(currentScript.src, window.location.href);
            if (parsedUrl.origin && parsedUrl.origin !== "null" && parsedUrl.origin !== window.location.origin) {
                autoApiBase = parsedUrl.origin;
            }
        }
    } catch (e) {
        // Fallback to relative path
    }

    const config = window.AgentGuardConfig || {};
    const storeId = config.storeId || scriptStoreId || "demo-store";
    const apiBase = config.apiBase || scriptApiBase || autoApiBase || "";

    // State
    let isOpen = false;
    let isSending = false;
    let customerEmail = localStorage.getItem("agentguard_email") || "";
    let customerOrder = localStorage.getItem("agentguard_order") || "";

    // Inject Modern Widget Styles
    const styleEl = document.createElement("style");
    styleEl.innerHTML = `
        .ag-widget-container * {
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            -webkit-font-smoothing: antialiased;
        }
        .ag-launcher-btn {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 56px;
            height: 56px;
            border-radius: 16px;
            background: #0f172a;
            color: #ffffff;
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.4), 0 8px 10px -6px rgba(15, 23, 42, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.15);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 999999;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .ag-launcher-btn:hover {
            transform: scale(1.05) translateY(-2px);
            background: #1e293b;
            box-shadow: 0 14px 28px -4px rgba(15, 23, 42, 0.5);
        }
        .ag-launcher-btn:active {
            transform: scale(0.96);
        }
        .ag-launcher-btn:focus-visible, .ag-header-close:focus-visible, .ag-quick-pill:focus-visible, .ag-send-btn:focus-visible, .ag-input-box:focus-visible, .ag-auth-input:focus-visible {
            outline: 2px solid #0f172a;
            outline-offset: 2px;
        }
        .ag-launcher-btn svg {
            width: 24px;
            height: 24px;
            transition: transform 0.2s ease;
        }
        .ag-chat-window {
            position: fixed;
            bottom: 92px;
            right: 24px;
            width: 390px;
            max-width: calc(100vw - 32px);
            height: 600px;
            max-height: calc(100vh - 120px);
            background: #ffffff;
            border-radius: 20px;
            box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.08);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            z-index: 999998;
            opacity: 0;
            transform: scale(0.96) translateY(12px);
            pointer-events: none;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .ag-chat-window.ag-open {
            opacity: 1;
            transform: scale(1) translateY(0);
            pointer-events: auto;
        }
        .ag-chat-header {
            background: #0f172a;
            color: #ffffff;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .ag-chat-header-info h3 {
            margin: 0;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: -0.01em;
            color: #ffffff;
        }
        .ag-chat-header-info p {
            margin: 2px 0 0 0;
            font-size: 11px;
            color: #94a3b8;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .ag-status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #10b981;
            box-shadow: 0 0 8px #10b981;
        }
        .ag-header-close {
            background: transparent;
            border: none;
            color: #94a3b8;
            cursor: pointer;
            padding: 4px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s ease;
        }
        .ag-header-close:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.1);
        }
        .ag-auth-bar {
            background: #f8fafc;
            padding: 10px 16px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            gap: 8px;
        }
        .ag-auth-input {
            flex: 1;
            background: #ffffff;
            border: 1px solid #cbd5e1;
            color: #0f172a;
            font-size: 11px;
            padding: 6px 10px;
            border-radius: 8px;
            outline: none;
            transition: border-color 0.15s ease;
        }
        .ag-auth-input:focus {
            border-color: #0f172a;
        }
        .ag-auth-input::placeholder {
            color: #94a3b8;
        }
        .ag-messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #f8fafc;
        }
        .ag-msg {
            max-width: 85%;
            font-size: 12.5px;
            line-height: 1.55;
            word-wrap: break-word;
        }
        .ag-msg-user {
            align-self: flex-end;
            background: #0f172a;
            color: #ffffff;
            padding: 10px 14px;
            border-radius: 14px 14px 2px 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .ag-msg-agent {
            align-self: flex-start;
            background: #ffffff;
            color: #0f172a;
            padding: 12px 15px;
            border-radius: 14px 14px 14px 2px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        .ag-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 10px;
            font-weight: 600;
            padding: 3px 7px;
            border-radius: 6px;
            margin-top: 8px;
        }
        .ag-badge-verified {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
        }
        .ag-badge-hitl {
            background: #fffbeb;
            color: #b45309;
            border: 1px solid #fde68a;
        }
        .ag-msg-thinking {
            align-self: flex-start;
            background: #ffffff;
            color: #64748b;
            font-size: 11px;
            padding: 8px 12px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
            border: 1px solid #e2e8f0;
        }
        .ag-spin {
            animation: ag-spin-anim 1s linear infinite;
        }
        @keyframes ag-spin-anim {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        .ag-quick-replies {
            padding: 8px 16px;
            background: #ffffff;
            border-top: 1px solid #e2e8f0;
            display: flex;
            gap: 6px;
            overflow-x: auto;
            white-space: nowrap;
        }
        .ag-quick-pill {
            background: #f1f5f9;
            color: #334155;
            font-size: 11px;
            font-weight: 500;
            padding: 5px 10px;
            border-radius: 20px;
            border: 1px solid #e2e8f0;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .ag-quick-pill:hover {
            background: #e2e8f0;
            color: #0f172a;
            border-color: #cbd5e1;
        }
        .ag-input-container {
            padding: 12px 16px;
            background: #ffffff;
            border-top: 1px solid #e2e8f0;
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .ag-input-box {
            flex: 1;
            padding: 9px 13px;
            background: #f8fafc;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            font-size: 12.5px;
            outline: none;
            transition: border-color 0.15s ease, background 0.15s ease;
        }
        .ag-input-box:focus {
            border-color: #0f172a;
            background: #ffffff;
        }
        .ag-input-box::placeholder {
            color: #94a3b8;
        }
        .ag-send-btn {
            background: #0f172a;
            color: white;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s ease;
        }
        .ag-send-btn:hover {
            background: #1e293b;
        }
        .ag-send-btn:disabled {
            background: #cbd5e1;
            color: #94a3b8;
            cursor: not-allowed;
        }
        .ag-footer-brand {
            padding: 5px 0 8px 0;
            text-align: center;
            font-size: 10px;
            color: #94a3b8;
            background: #ffffff;
        }
        .ag-footer-brand a {
            color: #0f172a;
            text-decoration: none;
            font-weight: 600;
        }
    `;
    document.head.appendChild(styleEl);

    // Build DOM Structure
    const container = document.createElement("div");
    container.className = "ag-widget-container";
    container.innerHTML = `
        <button id="ag-launcher" class="ag-launcher-btn" aria-label="Open Customer Support Chat">
            <svg id="ag-icon-chat" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <svg id="ag-icon-close" style="display:none;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>

        <div id="ag-chat" class="ag-chat-window">
            <div class="ag-chat-header">
                <div class="ag-chat-header-info">
                    <h3 id="ag-store-title">Lumina Audio Support</h3>
                    <p><span class="ag-status-dot"></span> Copilot Active • Policy Grounded</p>
                </div>
                <button id="ag-close-header" class="ag-header-close" aria-label="Close Chat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>

            <div class="ag-auth-bar">
                <input type="text" id="ag-order-inp" class="ag-auth-input" placeholder="Order # (e.g. 1001)" value="${customerOrder}">
                <input type="email" id="ag-email-inp" class="ag-auth-input" placeholder="Billing Email" value="${customerEmail}">
            </div>

            <div id="ag-msgs" class="ag-messages">
                <div class="ag-msg ag-msg-agent">
                    Hello! I'm your store's autonomous customer assistant. I can track orders in real time, evaluate return window eligibility, and answer policy questions.
                </div>
            </div>

            <div class="ag-quick-replies">
                <button class="ag-quick-pill" data-query="Where is order #1001?">Track #1001</button>
                <button class="ag-quick-pill" data-query="Can I return order #1001?">Return #1001</button>
                <button class="ag-quick-pill" data-query="What is your return policy and window?">Return Policy</button>
                <button class="ag-quick-pill" data-query="What warranty covers purchases?">Warranty</button>
            </div>

            <div class="ag-input-container">
                <input type="text" id="ag-input" class="ag-input-box" placeholder="Ask about orders, returns, or policies...">
                <button id="ag-send" class="ag-send-btn" aria-label="Send Message">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                </button>
            </div>

            <div class="ag-footer-brand">
                Protected by <a href="/" target="_blank">AgentGuard Privacy Shields</a>
            </div>
        </div>
    `;
    document.body.appendChild(container);

    // Elements
    const launcherBtn = document.getElementById("ag-launcher");
    const chatWindow = document.getElementById("ag-chat");
    const iconChat = document.getElementById("ag-icon-chat");
    const iconClose = document.getElementById("ag-icon-close");
    const closeHeaderBtn = document.getElementById("ag-close-header");
    const inputEl = document.getElementById("ag-input");
    const sendBtn = document.getElementById("ag-send");
    const msgsEl = document.getElementById("ag-msgs");
    const orderInp = document.getElementById("ag-order-inp");
    const emailInp = document.getElementById("ag-email-inp");
    const storeTitleEl = document.getElementById("ag-store-title");

    // Fetch store metadata to display custom store name in header
    async function loadStoreBranding() {
        try {
            const res = await fetch(`${apiBase}/api/store?store_id=${encodeURIComponent(storeId)}`);
            const data = await res.json();
            if (data.store && data.store.store_name) {
                storeTitleEl.textContent = `${data.store.store_name} Support`;
            }
        } catch (e) {
            // Keep default
        }
    }
    loadStoreBranding();

    // Toggle Chat
    function toggleChat(forceOpen) {
        if (typeof forceOpen === "boolean") {
            isOpen = forceOpen;
        } else {
            isOpen = !isOpen;
        }
        launcherBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
        if (isOpen) {
            chatWindow.classList.add("ag-open");
            iconChat.style.display = "none";
            iconClose.style.display = "block";
            setTimeout(() => inputEl.focus(), 200);
        } else {
            chatWindow.classList.remove("ag-open");
            iconChat.style.display = "block";
            iconClose.style.display = "none";
        }
    }

    // Accessible Escape Key to close chat window (WCAG 2.2 AA)
    window.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && isOpen) {
            toggleChat(false);
            launcherBtn.focus();
        }
    });

    // Expose Global Trigger for Storefront Action Buttons
    window.__AGENTGUARD_TRIGGER_CHAT = () => toggleChat(true);

    launcherBtn.addEventListener("click", () => toggleChat());
    closeHeaderBtn.addEventListener("click", () => toggleChat(false));

    // Save auth inputs to localStorage
    orderInp.addEventListener("change", () => {
        customerOrder = orderInp.value.trim();
        localStorage.setItem("agentguard_order", customerOrder);
    });
    emailInp.addEventListener("change", () => {
        customerEmail = emailInp.value.trim();
        localStorage.setItem("agentguard_email", customerEmail);
    });

    // Quick Replies
    const quickPills = container.querySelectorAll(".ag-quick-pill");
    quickPills.forEach(pill => {
        pill.addEventListener("click", () => {
            const query = pill.getAttribute("data-query");
            if (query && !isSending) {
                if (query.includes("1001") && !orderInp.value) {
                    orderInp.value = "1001";
                    emailInp.value = "sarah.connor@example.com";
                    customerOrder = "1001";
                    customerEmail = "sarah.connor@example.com";
                }
                sendMessage(query);
            }
        });
    });

    // Send Message
    async function sendMessage(text) {
        const inquiry = text || inputEl.value.trim();
        if (!inquiry || isSending) return;

        inputEl.value = "";
        isSending = true;
        sendBtn.disabled = true;

        // Append User Message
        const userMsg = document.createElement("div");
        userMsg.className = "ag-msg ag-msg-user";
        userMsg.textContent = inquiry;
        msgsEl.appendChild(userMsg);

        // Append Thinking Indicator
        const thinkingMsg = document.createElement("div");
        thinkingMsg.className = "ag-msg-thinking";
        thinkingMsg.id = "ag-temp-thinking";
        thinkingMsg.innerHTML = `
            <svg class="ag-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"></path></svg>
            <span>Copilot verifying with store policy...</span>
        `;
        msgsEl.appendChild(thinkingMsg);
        msgsEl.scrollTop = msgsEl.scrollHeight;

        try {
            const response = await fetch(`${apiBase}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    inquiry: inquiry,
                    store_id: storeId,
                    customer_email: customerEmail || emailInp.value.trim() || undefined,
                }),
            });

            const data = await response.json();
            thinkingMsg.remove();

            if (data.status === "success") {
                const agentMsg = document.createElement("div");
                agentMsg.className = "ag-msg ag-msg-agent";
                
                let formatted = escapeHtml(data.response).replace(/\n/g, "<br>");
                agentMsg.innerHTML = `<div>${formatted}</div>`;

                if (data.critique && data.critique.passed) {
                    const badge = document.createElement("div");
                    badge.className = "ag-badge ag-badge-verified";
                    badge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg><span>Policy Grounded (${((data.critique.score || 1) * 100).toFixed(0)}% accuracy)</span>`;
                    agentMsg.appendChild(badge);
                }

                if (inquiry.toLowerCase().includes("refund") && data.response.toLowerCase().includes("approval")) {
                    const hitlBadge = document.createElement("div");
                    hitlBadge.className = "ag-badge ag-badge-hitl";
                    hitlBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg><span>Approval Queued in Merchant Inbox</span>`;
                    agentMsg.appendChild(hitlBadge);
                }

                msgsEl.appendChild(agentMsg);
            } else {
                const errMsg = document.createElement("div");
                errMsg.className = "ag-msg ag-msg-agent";
                errMsg.style.color = "#f87171";
                errMsg.textContent = `Error: ${data.message || "Something went wrong"}`;
                msgsEl.appendChild(errMsg);
            }
        } catch (err) {
            thinkingMsg.remove();
            const errMsg = document.createElement("div");
            errMsg.className = "ag-msg ag-msg-agent";
            errMsg.style.color = "#f87171";
            errMsg.textContent = "Network error: Unable to contact support server.";
            msgsEl.appendChild(errMsg);
        } finally {
            isSending = false;
            sendBtn.disabled = false;
            msgsEl.scrollTop = msgsEl.scrollHeight;
        }
    }

    function escapeHtml(str) {
        return (str || "").replace(/[&<>'"]/g, tag => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"
        }[tag] || tag));
    }

    sendBtn.addEventListener("click", () => sendMessage());
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

})();
