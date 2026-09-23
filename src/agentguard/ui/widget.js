/**
 * AgentGuard Customer Support Embeddable Widget
 * Zero-dependency standalone JavaScript widget for e-commerce storefronts.
 * 
 * Usage:
 *   <script src="http://localhost:8000/widget.js" data-store-id="demo-store"></script>
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

    // Inject Widget Styles
    const styleEl = document.createElement("style");
    styleEl.innerHTML = `
        .ag-widget-container * {
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }
        .ag-launcher-btn {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: #ffffff;
            box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.4), 0 8px 10px -6px rgba(79, 70, 229, 0.2);
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 999999;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .ag-launcher-btn:hover {
            transform: scale(1.08) translateY(-2px);
            box-shadow: 0 14px 28px -4px rgba(79, 70, 229, 0.5);
        }
        .ag-launcher-btn svg {
            width: 28px;
            height: 28px;
            transition: transform 0.2s ease;
        }
        .ag-chat-window {
            position: fixed;
            bottom: 96px;
            right: 24px;
            width: 400px;
            max-width: calc(100vw - 32px);
            height: 620px;
            max-height: calc(100vh - 120px);
            background: #ffffff;
            border-radius: 18px;
            box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.2), 0 1px 3px rgba(0,0,0,0.08);
            border: 1px solid rgba(0, 0, 0, 0.08);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            z-index: 999998;
            opacity: 0;
            transform: scale(0.95) translateY(10px);
            pointer-events: none;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .ag-chat-window.ag-open {
            opacity: 1;
            transform: scale(1) translateY(0);
            pointer-events: auto;
        }
        .ag-chat-header {
            background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
            color: #ffffff;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .ag-chat-header h3 {
            margin: 0;
            font-size: 15px;
            font-weight: 600;
            letter-spacing: -0.01em;
        }
        .ag-chat-header p {
            margin: 2px 0 0 0;
            font-size: 12px;
            color: #a5b4fc;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .ag-status-dot {
            width: 7px;
            height: 7px;
            background: #10b981;
            border-radius: 50%;
            display: inline-block;
        }
        .ag-header-close {
            background: transparent;
            border: none;
            color: #c7d2fe;
            cursor: pointer;
            padding: 4px;
            display: flex;
            align-items: center;
            border-radius: 6px;
        }
        .ag-header-close:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
        }
        .ag-auth-bar {
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
            padding: 8px 16px;
            display: flex;
            gap: 8px;
            font-size: 12px;
        }
        .ag-auth-input {
            flex: 1;
            padding: 5px 8px;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            font-size: 11px;
            outline: none;
            background: #ffffff;
            color: #1e293b;
        }
        .ag-auth-input:focus {
            border-color: #6366f1;
        }
        .ag-messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #fbfbfe;
        }
        .ag-msg {
            max-width: 86%;
            padding: 10px 14px;
            border-radius: 14px;
            font-size: 13px;
            line-height: 1.45;
            word-break: break-word;
        }
        .ag-msg-user {
            align-self: flex-end;
            background: #4f46e5;
            color: #ffffff;
            border-bottom-right-radius: 3px;
        }
        .ag-msg-agent {
            align-self: flex-start;
            background: #ffffff;
            color: #1e293b;
            border: 1px solid #e2e8f0;
            border-bottom-left-radius: 3px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
        }
        .ag-badge {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            font-size: 10px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            margin-top: 6px;
        }
        .ag-badge-verified {
            background: #ecfdf5;
            color: #059669;
            border: 1px solid #a7f3d0;
        }
        .ag-badge-hitl {
            background: #fffbeb;
            color: #d97706;
            border: 1px solid #fde68a;
        }
        .ag-msg-thinking {
            align-self: flex-start;
            background: #f1f5f9;
            color: #64748b;
            font-size: 12px;
            font-style: italic;
            padding: 8px 12px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .ag-quick-replies {
            padding: 8px 16px;
            background: #ffffff;
            border-top: 1px solid #f1f5f9;
            display: flex;
            gap: 6px;
            overflow-x: auto;
            white-space: nowrap;
        }
        .ag-quick-pill {
            background: #f1f5f9;
            color: #475569;
            font-size: 11px;
            font-weight: 500;
            padding: 5px 10px;
            border-radius: 20px;
            border: 1px solid #e2e8f0;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .ag-quick-pill:hover {
            background: #e0e7ff;
            color: #4338ca;
            border-color: #c7d2fe;
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
            padding: 10px 14px;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            font-size: 13px;
            outline: none;
            transition: border-color 0.15s ease;
        }
        .ag-input-box:focus {
            border-color: #6366f1;
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
        }
        .ag-send-btn {
            background: #4f46e5;
            color: white;
            border: none;
            width: 38px;
            height: 38px;
            border-radius: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.15s ease;
        }
        .ag-send-btn:hover {
            background: #4338ca;
        }
        .ag-send-btn:disabled {
            background: #cbd5e1;
            cursor: not-allowed;
        }
        .ag-footer-brand {
            padding: 4px 0 8px 0;
            text-align: center;
            font-size: 10px;
            color: #94a3b8;
            background: #ffffff;
        }
        .ag-footer-brand a {
            color: #6366f1;
            text-decoration: none;
            font-weight: 500;
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
                <div>
                    <h3>Lumina Audio Support</h3>
                    <p><span class="ag-status-dot"></span> AgentGuard AI Copilot Active</p>
                </div>
                <button id="ag-close-header" class="ag-header-close" aria-label="Close Chat">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>

            <div class="ag-auth-bar">
                <input type="text" id="ag-order-inp" class="ag-auth-input" placeholder="Order # (e.g. 1001)" value="${customerOrder}">
                <input type="email" id="ag-email-inp" class="ag-auth-input" placeholder="Billing Email" value="${customerEmail}">
            </div>

            <div id="ag-msgs" class="ag-messages">
                <div class="ag-msg ag-msg-agent">
                    👋 Hi there! I'm your autonomous assistant. I can look up live order tracking, check return eligibility, or submit refunds with merchant approval.
                </div>
            </div>

            <div class="ag-quick-replies">
                <button class="ag-quick-pill" data-query="Where is my order #1001?">📍 Track #1001</button>
                <button class="ag-quick-pill" data-query="Can I return order #1001? The sound quality is bad">🔄 Return #1001</button>
                <button class="ag-quick-pill" data-query="Track order #1002">📦 Status #1002</button>
            </div>

            <div class="ag-input-container">
                <input type="text" id="ag-input" class="ag-input-box" placeholder="Ask a question..." autocomplete="off">
                <button id="ag-send" class="ag-send-btn" aria-label="Send Message">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                </button>
            </div>

            <div class="ag-footer-brand">
                Protected by <a href="/dashboard" target="_blank">AgentGuard Zero-Trust AI</a>
            </div>
        </div>
    `;
    document.body.appendChild(container);

    // Elements
    const launcher = document.getElementById("ag-launcher");
    const chatWindow = document.getElementById("ag-chat");
    const closeBtn = document.getElementById("ag-close-header");
    const iconChat = document.getElementById("ag-icon-chat");
    const iconClose = document.getElementById("ag-icon-close");
    const msgsEl = document.getElementById("ag-msgs");
    const inputEl = document.getElementById("ag-input");
    const sendBtn = document.getElementById("ag-send");
    const orderInp = document.getElementById("ag-order-inp");
    const emailInp = document.getElementById("ag-email-inp");

    // Toggle Chat
    function toggleChat(open) {
        isOpen = (typeof open === "boolean") ? open : !isOpen;
        if (isOpen) {
            chatWindow.classList.add("ag-open");
            iconChat.style.display = "none";
            iconClose.style.display = "block";
            setTimeout(() => inputEl.focus(), 150);
        } else {
            chatWindow.classList.remove("ag-open");
            iconChat.style.display = "block";
            iconClose.style.display = "none";
        }
    }

    window.__AGENTGUARD_TRIGGER_CHAT = () => toggleChat(true);

    launcher.addEventListener("click", () => toggleChat());
    closeBtn.addEventListener("click", () => toggleChat(false));

    // Save auth inputs
    orderInp.addEventListener("change", (e) => {
        customerOrder = e.target.value.trim();
        localStorage.setItem("agentguard_order", customerOrder);
    });
    emailInp.addEventListener("change", (e) => {
        customerEmail = e.target.value.trim();
        localStorage.setItem("agentguard_email", customerEmail);
    });

    // Quick replies
    document.querySelectorAll(".ag-quick-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            const query = pill.getAttribute("data-query");
            if (query && !isSending) {
                // If query is for #1001 and inputs are empty, autofill demo credentials
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
            <span>AgentGuard Copilot is verifying with store policy...</span>
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
                
                // Format text with paragraph breaks
                let formatted = data.response.replace(/\n/g, "<br>");
                agentMsg.innerHTML = `<div>${formatted}</div>`;

                // Add audit/critic badge
                if (data.critique && data.critique.passed) {
                    const badge = document.createElement("div");
                    badge.className = "ag-badge ag-badge-verified";
                    badge.innerHTML = `✓ Factually Verified (${data.critique.score * 100}% accuracy)`;
                    agentMsg.appendChild(badge);
                }

                if (inquiry.toLowerCase().includes("refund") && data.response.toLowerCase().includes("approval")) {
                    const hitlBadge = document.createElement("div");
                    hitlBadge.className = "ag-badge ag-badge-hitl";
                    hitlBadge.innerHTML = `🛡️ HITL Approval Queued in Merchant Inbox`;
                    agentMsg.appendChild(hitlBadge);
                }

                msgsEl.appendChild(agentMsg);
            } else {
                const errMsg = document.createElement("div");
                errMsg.className = "ag-msg ag-msg-agent";
                errMsg.style.color = "#dc2626";
                errMsg.textContent = `Error: ${data.message || "Something went wrong"}`;
                msgsEl.appendChild(errMsg);
            }
        } catch (err) {
            thinkingMsg.remove();
            const errMsg = document.createElement("div");
            errMsg.className = "ag-msg ag-msg-agent";
            errMsg.style.color = "#dc2626";
            errMsg.textContent = "Network error: Unable to contact support server.";
            msgsEl.appendChild(errMsg);
        } finally {
            isSending = false;
            sendBtn.disabled = false;
            msgsEl.scrollTop = msgsEl.scrollHeight;
        }
    }

    sendBtn.addEventListener("click", () => sendMessage());
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

})();
