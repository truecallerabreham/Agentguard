"""Unit tests for ACID-compliant persistent SQLite database storage."""

import os
from pathlib import Path
import pytest

from agentguard.storage.sqlite_db import SqliteDatabaseManager


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_agentguard.db"
    mgr = SqliteDatabaseManager(db_path=db_file)
    return mgr


def test_sqlite_schema_initialization(temp_db):
    """Verify all tables and indexes are initialized properly."""
    tables = temp_db.list_tables()
    assert "merchants" in tables
    assert "stores" in tables
    assert "products" in tables
    assert "orders" in tables
    assert "knowledge_articles" in tables
    assert "approvals" in tables
    assert "sessions" in tables


def test_sqlite_seeded_default_data(temp_db):
    """Verify demo-store and seed data exist upon fresh initialization."""
    store = temp_db.get_store("demo-store")
    assert store is not None
    assert store["store_name"] == "Lumina Audio & Acoustics"

    merchant = temp_db.get_merchant_by_email("demo@lumina-audio.com")
    assert merchant is not None
    assert merchant["store_id"] == "demo-store"

    products = temp_db.list_products("demo-store")
    assert len(products) == 4

    order = temp_db.get_order("1001", "demo-store")
    assert order is not None
    assert order["customer_email"] == "sarah.connor@example.com"
    assert order["carrier"] == "USPS"


def test_sqlite_data_persistence_across_reconnect(tmp_path):
    """Verify data persists when database connection is closed and re-opened."""
    db_file = tmp_path / "persist_test.db"
    mgr1 = SqliteDatabaseManager(db_path=db_file)
    
    # Create merchant and order
    mgr1.create_merchant(
        merchant_id="merch_persist",
        email="owner@realstore.com",
        password_hash="hashed_secret",
        salt="random_salt",
        store_name="Real Store",
        store_id="store_real_123",
        api_key="ag_live_key_999",
    )
    mgr1.create_store(
        store_id="store_real_123",
        merchant_id="merch_persist",
        store_name="Real Store",
        return_window_days=60,
    )
    mgr1.create_order(
        order_id="ORD-9999",
        store_id="store_real_123",
        customer_email="buyer@gmail.com",
        customer_name="John Buyer",
        total_amount=199.95,
        carrier="USPS",
        tracking_number="TRK-USPS-001122",
    )

    # Re-open database with a completely new manager instance
    mgr2 = SqliteDatabaseManager(db_path=db_file)
    merchant = mgr2.get_merchant_by_email("owner@realstore.com")
    assert merchant is not None
    assert merchant["store_name"] == "Real Store"

    order = mgr2.get_order("ORD-9999", "store_real_123")
    assert order is not None
    assert order["customer_name"] == "John Buyer"
    assert order["total_amount"] == 199.95
    assert order["carrier"] == "USPS"


def test_sqlite_session_lifecycle(temp_db):
    """Verify session creation, verification, and deletion."""
    session = temp_db.create_session("sess_12345", "merch_demo", days=7)
    assert session is not None

    found = temp_db.get_session("sess_12345")
    assert found is not None
    assert found["email"] == "demo@lumina-audio.com"

    temp_db.delete_session("sess_12345")
    assert temp_db.get_session("sess_12345") is None


def test_sqlite_approval_persistence(temp_db):
    """Verify approval creation, retrieval, and decision update."""
    appr = temp_db.create_approval(
        approval_id="appr-test-1",
        store_id="demo-store",
        tool_name="issue_high_risk_refund",
        parameters={"order_id": "1001", "amount": 249.00},
        token="tok_secret_123",
    )
    assert appr["status"] == "PENDING"

    pending_list = temp_db.list_approvals("demo-store")
    assert any(a["token"] == "tok_secret_123" for a in pending_list)

    settled = temp_db.decide_approval("tok_secret_123", "APPROVE")
    assert settled["status"] == "SETTLED"
