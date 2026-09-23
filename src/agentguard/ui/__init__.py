"""UI and Web Control Panel package for AgentGuard."""

from agentguard.ui.routes import (
    dashboard_endpoint,
    landing_endpoint,
    widget_script_endpoint,
    api_chat_endpoint,
    api_list_approvals_endpoint,
    api_decide_approval_endpoint,
    api_store_config_endpoint,
    api_audit_log_endpoint,
    api_auth_signup_endpoint,
    api_auth_login_endpoint,
    api_kb_endpoint,
    api_kb_delete_endpoint,
)

__all__ = [
    "dashboard_endpoint",
    "landing_endpoint",
    "widget_script_endpoint",
    "api_chat_endpoint",
    "api_list_approvals_endpoint",
    "api_decide_approval_endpoint",
    "api_store_config_endpoint",
    "api_audit_log_endpoint",
    "api_auth_signup_endpoint",
    "api_auth_login_endpoint",
    "api_kb_endpoint",
    "api_kb_delete_endpoint",
]

