-- deploy/sql/init.sql: Multi-tenant schema with PostgreSQL Row-Level Security (RLS)

DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'standard'
);

CREATE TABLE orders (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    customer_id  TEXT NOT NULL REFERENCES customers(id),
    status       TEXT NOT NULL,
    total_cents  BIGINT NOT NULL
);

-- Seed initial records for two distinct tenants: 'acme' and 'globex'
INSERT INTO customers (id, tenant_id, name, email, tier) VALUES
    ('CUST-1001', 'acme',   'Alicia Rivera', 'alicia@acme.com', 'gold'),
    ('CUST-2001', 'globex', 'Cho Nakamura',  'cho@globex.com',  'gold');

INSERT INTO orders (id, tenant_id, customer_id, status, total_cents) VALUES
    ('o_9001', 'acme',   'CUST-1001', 'delivered',      12900),
    ('o_9101', 'globex', 'CUST-2001', 'refund_pending',  8900);

-- 1. Enable Row-Level Security on every tenant-scoped table:
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders    ENABLE ROW LEVEL SECURITY;

-- 2. Define the RLS Policies:
-- A row is visible if and only if its tenant_id matches the session variable 'app.tenant_id'
CREATE POLICY tenant_isolation_customers ON customers
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_orders ON orders
    USING (tenant_id = current_setting('app.tenant_id', true));
