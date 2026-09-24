-- AgentGuard Production Schema
-- ACID-compliant relational schema for merchants, stores, orders, knowledge bases, and approvals.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    store_name TEXT NOT NULL,
    store_id TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    platform TEXT NOT NULL DEFAULT 'native',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_merchants_email ON merchants (email);
CREATE INDEX IF NOT EXISTS idx_merchants_api_key ON merchants (api_key);

CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL,
    store_name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'native',
    api_url TEXT,
    api_token_enc TEXT,
    return_window_days INTEGER NOT NULL DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    inventory_count INTEGER NOT NULL DEFAULT 100,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_products_store ON products (store_id);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    customer_name TEXT,
    total_amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'fulfilled',
    fulfillment_status TEXT NOT NULL DEFAULT 'delivered',
    carrier TEXT NOT NULL DEFAULT 'FedEx',
    tracking_number TEXT NOT NULL,
    tracking_url TEXT,
    items_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_orders_store_email ON orders (store_id, customer_email);
CREATE INDEX IF NOT EXISTS idx_orders_store_id ON orders (store_id, order_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_articles (
    article_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_kb_store ON knowledge_articles (store_id);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_approvals_store ON approvals (store_id, status);
CREATE INDEX IF NOT EXISTS idx_approvals_token ON approvals (token);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at);
