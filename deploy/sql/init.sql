-- deploy/sql/init.sql: Complete Production Multi-Tenant Schema with PostgreSQL Row-Level Security (RLS)

-- 1. CLEANUP PREVIOUS TABLES
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS kb_articles CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- 2. CUSTOMERS TABLE
CREATE TABLE customers (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'standard'
);

CREATE INDEX idx_customers_tenant ON customers (tenant_id);

-- 3. ORDERS TABLE
CREATE TABLE orders (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    customer_id  TEXT NOT NULL REFERENCES customers(id),
    status       TEXT NOT NULL,
    total_cents  BIGINT NOT NULL
);

CREATE INDEX idx_orders_tenant_cust ON orders (tenant_id, customer_id);

-- 4. KNOWLEDGE BASE ARTICLES
CREATE TABLE kb_articles (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL
);

CREATE INDEX idx_kb_tenant_cat ON kb_articles (tenant_id, category);

-- 5. SUPPORT TICKETS
CREATE TABLE tickets (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    priority    TEXT NOT NULL DEFAULT 'medium',
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  DOUBLE PRECISION NOT NULL
);

CREATE INDEX idx_tickets_tenant_cust ON tickets (tenant_id, customer_id);

-- 6. SEED INITIAL DATA FOR TENANTS 'acme' AND 'globex'
INSERT INTO customers (id, tenant_id, name, email, tier) VALUES
    ('CUST-1001', 'acme',   'Alicia Rivera', 'alicia@acme.com', 'gold'),
    ('CUST-2001', 'globex', 'Cho Nakamura',  'cho@globex.com',  'gold');

INSERT INTO orders (id, tenant_id, customer_id, status, total_cents) VALUES
    ('o_9001', 'acme',   'CUST-1001', 'delivered',      12900),
    ('o_9002', 'acme',   'CUST-1001', 'processing',      4500),
    ('o_9101', 'globex', 'CUST-2001', 'refund_pending',  8900);

INSERT INTO kb_articles (id, tenant_id, category, title, content) VALUES
    ('KB-101', 'global', 'returns',  'Return Policy & Refunds', 'Customers may request a return within 30 days of delivery. Gold tier members receive free return shipping and 100% refund with zero restocking fee. Standard tier has a 10% restocking fee. Items must be in original condition.'),
    ('KB-102', 'global', 'warranty', 'Defective Merchandise & Replacement', 'Defective merchandise reported within 90 days qualifies for immediate return or direct replacement. Replacement orders are shipped via priority delivery within 24 hours of ticket confirmation.'),
    ('KB-103', 'global', 'billing',  'Billing Inquiries & Payment Disputes', 'Invoices are generated upon shipment. Refunds take 3-5 business days to post to the original payment method after an RMA has been settled.');

-- 7. ENABLE ROW-LEVEL SECURITY (RLS) ON ALL TABLES
ALTER TABLE customers   ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders      ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets     ENABLE ROW LEVEL SECURITY;

-- 8. DEFINE RLS POLICIES
-- Customer, Order, and Ticket rows are strictly isolated by session variable 'app.tenant_id'
CREATE POLICY tenant_isolation_customers ON customers
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_orders ON orders
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_tickets ON tickets
    USING (tenant_id = current_setting('app.tenant_id', true));

-- Knowledge base articles are visible if they belong to the tenant OR are 'global'
CREATE POLICY tenant_isolation_kb ON kb_articles
    USING (
        tenant_id = current_setting('app.tenant_id', true)
        OR tenant_id = 'global'
    );
