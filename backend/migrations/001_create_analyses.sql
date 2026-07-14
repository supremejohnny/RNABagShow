CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NULL,
    task VARCHAR(100) NOT NULL,
    modality VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued',
            'validating',
            'running',
            'succeeded',
            'failed',
            'cancelled',
            'expired',
            'purged'
        )),
    original_filename VARCHAR(512) NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes >= 0),
    file_sha256 CHAR(64) NOT NULL
        CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    content_type VARCHAR(128) NOT NULL
        DEFAULT 'text/tab-separated-values',
    storage_provider VARCHAR(32) NOT NULL DEFAULT 's3',
    storage_bucket VARCHAR(255) NOT NULL,
    storage_key VARCHAR(1024) NOT NULL,
    input_summary JSONB NULL
        CHECK (
            input_summary IS NULL
            OR jsonb_typeof(input_summary) = 'object'
        ),
    result JSONB NULL
        CHECK (
            result IS NULL
            OR jsonb_typeof(result) = 'object'
        ),
    error JSONB NULL
        CHECK (
            error IS NULL
            OR jsonb_typeof(error) = 'object'
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NULL,
    purged_at TIMESTAMPTZ NULL,
    CONSTRAINT analyses_succeeded_has_result CHECK (
        status <> 'succeeded' OR result IS NOT NULL
    ),
    CONSTRAINT analyses_failed_has_error CHECK (
        status <> 'failed' OR error IS NOT NULL
    )
);

CREATE INDEX idx_analyses_status_created_at
    ON analyses (status, created_at DESC);

CREATE INDEX idx_analyses_created_at
    ON analyses (created_at DESC);

CREATE INDEX idx_analyses_user_created_at
    ON analyses (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX idx_analyses_sha256
    ON analyses (file_sha256);

CREATE INDEX idx_analyses_storage_reference
    ON analyses (storage_provider, storage_bucket, storage_key)
    WHERE purged_at IS NULL;
