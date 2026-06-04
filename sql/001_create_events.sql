CREATE TABLE IF NOT EXISTS events (
    id                  BIGSERIAL PRIMARY KEY,
    event_id            UUID NOT NULL UNIQUE,
    trace_id            VARCHAR(64),
    store_id            VARCHAR(32) NOT NULL,
    camera_id           VARCHAR(32) NOT NULL,
    visitor_id          VARCHAR(64) NOT NULL,
    event_type          VARCHAR(32) NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL,
    zone_id             VARCHAR(32),
    dwell_ms            INTEGER DEFAULT 0,
    is_staff            BOOLEAN DEFAULT FALSE,
    confidence          FLOAT NOT NULL,
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    CHECK (dwell_ms >= 0),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (event_type IN (
        'ENTRY',
        'EXIT',
        'ZONE_ENTER',
        'ZONE_EXIT',
        'ZONE_DWELL',
        'BILLING_QUEUE_JOIN',
        'BILLING_QUEUE_ABANDON',
        'REENTRY'
    ))
);

CREATE INDEX IF NOT EXISTS idx_events_store_ts ON events (store_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_visitor ON events (visitor_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_camera ON events (camera_id);
CREATE INDEX IF NOT EXISTS idx_events_zone ON events (zone_id) WHERE zone_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_entries ON events (store_id, timestamp DESC) WHERE event_type = 'ENTRY' AND is_staff = FALSE;
CREATE INDEX IF NOT EXISTS idx_events_billing_queue ON events (store_id, visitor_id) WHERE zone_id = 'BILLING' AND event_type IN ('BILLING_QUEUE_JOIN', 'BILLING_QUEUE_ABANDON');
