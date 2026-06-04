CREATE TABLE IF NOT EXISTS visitor_sessions (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID NOT NULL UNIQUE,
    visitor_id          VARCHAR(64) NOT NULL,
    store_id            VARCHAR(32) NOT NULL,
    entry_time          TIMESTAMPTZ NOT NULL,
    exit_time           TIMESTAMPTZ,
    converted           BOOLEAN DEFAULT FALSE,
    transaction_id      VARCHAR(64),
    reentry_count       INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    CHECK (reentry_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sessions_visitor ON visitor_sessions (visitor_id);
CREATE INDEX IF NOT EXISTS idx_sessions_store_entry ON visitor_sessions (store_id, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_converted ON visitor_sessions (store_id, entry_time DESC) WHERE converted = TRUE;
