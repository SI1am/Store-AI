CREATE TABLE IF NOT EXISTS pos_transactions (
    id                  BIGSERIAL PRIMARY KEY,
    transaction_id      VARCHAR(64) NOT NULL UNIQUE,
    store_id            VARCHAR(32) NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL,
    amount              NUMERIC(10, 2),
    items               JSONB DEFAULT '[]',
    payment_method      VARCHAR(32),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pos_store_ts ON pos_transactions (store_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pos_ts ON pos_transactions (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pos_amount ON pos_transactions (amount DESC);
