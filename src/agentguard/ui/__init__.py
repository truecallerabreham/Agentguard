"""UI and Web Control Panel package for AgentGuard."""

from agentguard.ui.routes import (
    dashboard_endpoint,
    widget_script_endpoint,
    api_chat_endpoint,
    api_list_approvals_endpoint,
    api_decide_approval_endpoint,
    api_store_config_endpoint,
    api_audit_log_endpoint,
)

__all__ = [
    "dashboard_endpoint",
    "widget_script_endpoint",
    "api_chat_endpoint",
    "api_list_approvals_endpoint",
    "api_decide_approval_endpoint",
    "api_store_config_endpoint",
    "api_audit_log_endpoint",
]
