"""HTTP handlers and API routes for the AgentGuard Merchant Control Panel."""

from __future__ import annotations
import json
import logging
import os
from typing import Any
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from agentguard.agents.orchestrator import MultiAgentOrchestrator
from agentguard.ecommerce.models import StoreConfig, StorePlatform
from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.governance.approval import get_approval_manager
from agentguard.observability.audit import get_audit_logger, verify_audit_log

logger = logging.getLogger("agentguard.ui.routes")


def get_dashboard_html() -> str:
    """Load or return the pre-compiled Merchant Dashboard HTML."""
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>AgentGuard Dashboard</h1><p>dashboard.html not found.</p></body></html>"


def get_landing_html() -> str:
    """Load or return the SaaS product landing page HTML."""
    html_path = os.path.join(os.path.dirname(__file__), "landing.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return get_dashboard_html()


def get_store_demo_html() -> str:
    """Load or return the customer storefront simulator HTML."""
    html_path = os.path.join(os.path.dirname(__file__), "store_demo.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return get_landing_html()


async def landing_endpoint(request: Request) -> Response:
    """Serve the public SaaS Landing Page."""
    html = get_landing_html()
    return HTMLResponse(content=html)


async def store_demo_endpoint(request: Request) -> Response:
    """Serve the customer-facing storefront simulation page."""
    html = get_store_demo_html()
    return HTMLResponse(content=html)


async def dashboard_endpoint(request: Request) -> Response:
    """Serve the Merchant Control Panel SPA."""
    html = get_dashboard_html()
    return HTMLResponse(content=html)


async def widget_script_endpoint(request: Request) -> Response:
    """Serve the embeddable customer chat widget JavaScript."""
    widget_path = os.path.join(os.path.dirname(__file__), "widget.js")
    if os.path.exists(widget_path):
        with open(widget_path, "r", encoding="utf-8") as f:
            code = f.read()
    else:
        code = "/* AgentGuard Store Widget */ console.log('AgentGuard widget loaded');"
    return Response(content=code, media_type="application/javascript")


async def api_chat_endpoint(request: Request) -> Response:
    """Execute customer support inquiries through the Multi-Agent Copilot pipeline."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON payload"}, status_code=400)

    inquiry = body.get("inquiry", "").strip()
    store_id = body.get("store_id") or "demo-store"
    customer_email = body.get("customer_email", "").strip()

    if not inquiry:
        return JSONResponse({"status": "error", "message": "Inquiry text is required"}, status_code=400)

    # If email provided in separate field, augment inquiry for the Planner
    full_inquiry = inquiry
    if customer_email and customer_email not in inquiry:
        full_inquiry = f"{inquiry} (Customer email: {customer_email})"

    orchestrator = MultiAgentOrchestrator()
    events = []

    def handle_event(evt):
        events.append(evt.to_dict())

    try:
        result = await orchestrator.run(
            inquiry=full_inquiry,
            tenant_id=store_id,
            event_handler=handle_event,
        )

        return JSONResponse({
            "status": "success",
            "response": result.final_response,
            "critique": {
                "score": result.critique.factual_accuracy_score,
                "passed": result.critique.passed,
                "hallucinations": result.critique.hallucinations,
                "unsupported_claims": result.critique.unsupported_claims,
            },
            "plan": [s.to_dict() for s in result.plan.steps],
            "events": events,
            "execution_time_ms": result.total_duration_ms,
        })
    except Exception as exc:
        logger.error("Chat API error: %s", exc, exc_info=True)
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)


async def api_list_approvals_endpoint(request: Request) -> Response:
    """List pending high-risk Human-in-the-Loop approval requests."""
    manager = get_approval_manager()
    pending = manager.list_pending()
    return JSONResponse({"status": "success", "approvals": pending})


async def api_decide_approval_endpoint(request: Request) -> Response:
    """Authorize or reject a pending refund request."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    approval_id = body.get("approval_id")
    decision = body.get("decision", "").lower()
    reason = body.get("reason", "Decision recorded via Merchant Dashboard")

    if not approval_id or decision not in ("approve", "reject"):
        return JSONResponse(
            {"status": "error", "message": "approval_id and decision ('approve' | 'reject') are required."},
            status_code=400,
        )

    manager = get_approval_manager()

    if decision == "reject":
        res = manager.reject(approval_id=approval_id, approver="merchant@dashboard", reason=reason)
        return JSONResponse({
            "status": "success",
            "decision": "rejected",
            "message": f"Approval request '{approval_id}' was rejected.",
        })

    # Retrieve approval item to get token and arguments
    pending_item = manager.get_approval(approval_id)
    if not pending_item:
        return JSONResponse({"status": "error", "message": f"Approval request '{approval_id}' not found."}, status_code=404)

    token = pending_item.approval_token
    # Approve the item in manager
    manager.approve(approval_id=approval_id, approver="merchant@dashboard", token=token)

    # If it was an ecommerce refund, execute the settlement
    if pending_item.tool_name == "ecommerce_request_refund":
        params = pending_item.arguments
        svc = get_ecommerce_service()
        try:
            settlement = await svc.execute_approved_refund(
                store_id=params.get("store_id", "demo-store"),
                order_number=params.get("order_number", ""),
                approval_id=approval_id,
                approval_token=token,
                amount_cents=params.get("amount_cents", 0),
                reason=reason,
            )
            return JSONResponse({
                "status": "success",
                "decision": "approved",
                "settlement": settlement,
                "message": f"Refund of ${params.get('amount_cents', 0) / 100:.2f} was approved and disbursed.",
            })
        except Exception as exc:
            logger.error("Refund settlement error: %s", exc)
            return JSONResponse({"status": "error", "message": f"Settlement failed: {exc}"}, status_code=500)

    return JSONResponse({"status": "success", "decision": "approved", "message": "Action approved successfully."})


async def api_store_config_endpoint(request: Request) -> Response:
    """Retrieve or update store connection configuration."""
    svc = get_ecommerce_service()

    if request.method == "GET":
        store_id = request.query_params.get("store_id", "demo-store")
        cfg = svc.get_store_config(store_id)
        return JSONResponse({"status": "success", "store": cfg.to_dict()})

    # POST: Update store configuration
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    store_id = body.get("store_id", "demo-store")
    platform_str = body.get("platform", "simulator").lower()
    platform = StorePlatform(platform_str) if platform_str in ("shopify", "woocommerce", "simulator") else StorePlatform.SIMULATOR

    new_cfg = StoreConfig(
        store_id=store_id,
        store_name=body.get("store_name", "My Online Store"),
        platform=platform,
        api_url=body.get("api_url", "https://demo.lumina-audio.com"),
        api_token=body.get("api_token", ""),
        api_secret=body.get("api_secret", ""),
        return_window_days=int(body.get("return_window_days", 30)),
    )
    svc.register_store(new_cfg)
    return JSONResponse({"status": "success", "store": new_cfg.to_dict()})


async def api_audit_log_endpoint(request: Request) -> Response:
    """Fetch recent cryptographic audit log entries and verify hash-chain integrity."""
    audit = get_audit_logger()
    valid, reason, count = verify_audit_log(audit.log_path)

    entries = []
    if os.path.exists(audit.log_path):
        with open(audit.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Return last 30 entries reversed (newest first)
            for line in reversed(lines[-30:]):
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass

    return JSONResponse({
        "status": "success",
        "chain_valid": valid,
        "verification_reason": reason,
        "total_entries": count,
        "entries": entries,
    })


async def api_auth_signup_endpoint(request: Request) -> Response:
    """Create a new merchant account, provision store ID, and return session token."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    email = body.get("email", "").strip()
    password = body.get("password", "").strip()
    store_name = body.get("store_name", "").strip()
    platform = body.get("platform", "simulator")
    api_url = body.get("api_url", "")
    api_token = body.get("api_token", "")
    api_secret = body.get("api_secret", "")
    return_window_days = body.get("return_window_days", 30)

    svc = get_ecommerce_service()
    try:
        merchant = svc.register_merchant(
            email=email,
            password=password,
            store_name=store_name,
            platform=platform,
            api_url=api_url,
            api_token=api_token,
            api_secret=api_secret,
            return_window_days=return_window_days,
        )
        return JSONResponse({
            "status": "success",
            "message": "Merchant account created successfully.",
            "merchant": merchant.to_dict(),
        })
    except Exception as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)


async def api_auth_login_endpoint(request: Request) -> Response:
    """Authenticate an existing merchant by email and password."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    email = body.get("email", "").strip()
    password = body.get("password", "").strip()

    svc = get_ecommerce_service()
    merchant = svc.authenticate_merchant(email, password)
    if not merchant:
        return JSONResponse({"status": "error", "message": "Invalid email or password."}, status_code=401)

    return JSONResponse({
        "status": "success",
        "message": "Authenticated successfully.",
        "merchant": merchant.to_dict(),
    })


async def api_kb_endpoint(request: Request) -> Response:
    """List or add custom knowledge base articles for a store."""
    svc = get_ecommerce_service()

    if request.method == "GET":
        store_id = request.query_params.get("store_id", "demo-store")
        articles = svc.list_kb_articles(store_id)
        return JSONResponse({
            "status": "success",
            "store_id": store_id,
            "articles": [a.to_dict() for a in articles],
        })

    # POST: Add new knowledge base article
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    store_id = body.get("store_id", "demo-store")
    category = body.get("category", "general")
    title = body.get("title", "").strip()
    content = body.get("content", "").strip()

    if not title or not content:
        return JSONResponse({"status": "error", "message": "Title and content are required."}, status_code=400)

    try:
        article = svc.add_kb_article(store_id, category, title, content)
        return JSONResponse({
            "status": "success",
            "message": "Knowledge base article saved.",
            "article": article.to_dict(),
        })
    except Exception as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)


async def api_kb_delete_endpoint(request: Request) -> Response:
    """Delete a custom knowledge base article from a store."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    store_id = body.get("store_id", "demo-store")
    article_id = body.get("article_id", "").strip()

    if not article_id:
        return JSONResponse({"status": "error", "message": "article_id is required."}, status_code=400)

    svc = get_ecommerce_service()
    deleted = svc.delete_kb_article(store_id, article_id)
    if not deleted:
        return JSONResponse({"status": "error", "message": f"Article '{article_id}' not found."}, status_code=404)

    return JSONResponse({"status": "success", "message": f"Article '{article_id}' was deleted."})


async def static_file_endpoint(request: Request) -> Response:
    """Serve static assets (images, logos, icons) securely with directory traversal protection."""
    filename = request.path_params.get("filename", "")
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
    file_path = os.path.abspath(os.path.join(static_dir, filename))

    if not file_path.startswith(static_dir) or not os.path.isfile(file_path):
        return Response("Not Found", status_code=404)

    mime_types = {
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".css": "text/css",
        ".js": "application/javascript",
    }
    ext = os.path.splitext(filename)[1].lower()
    media_type = mime_types.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        return Response(
            content=f.read(),
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )

