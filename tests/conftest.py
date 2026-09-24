"""Global pytest fixtures and isolation setup for AgentGuard test suites."""

import pytest
from agentguard.ecommerce.service import get_ecommerce_service
from agentguard.governance.approval import get_approval_manager


@pytest.fixture(autouse=True)
def reset_system_state():
    """Ensure every single test across all test suites starts with clean, pristine state."""
    svc = get_ecommerce_service()
    svc.reset()
    mgr = get_approval_manager()
    with mgr._lock:
        mgr._approvals.clear()
    yield
    svc.reset()
    with mgr._lock:
        mgr._approvals.clear()
