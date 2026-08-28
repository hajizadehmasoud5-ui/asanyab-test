CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS marketplace_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  public_token TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'submitted',
  province TEXT NOT NULL,
  city TEXT NOT NULL,
  location_text TEXT NOT NULL DEFAULT '',
  service_text TEXT NOT NULL,
  normalized_service TEXT NOT NULL,
  insurer TEXT NOT NULL DEFAULT '',
  preferred_time TEXT NOT NULL DEFAULT '',
  budget_min BIGINT,
  budget_max BIGINT,
  contact TEXT NOT NULL DEFAULT '',
  selected_match_id UUID,
  is_test BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT marketplace_request_status CHECK (
    status IN ('submitted','providers_notified','provider_interested','selected','cancelled')
  ),
  CONSTRAINT marketplace_budget_order CHECK (
    budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max
  )
);
CREATE INDEX IF NOT EXISTS idx_marketplace_requests_status
  ON marketplace_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_requests_location_service
  ON marketplace_requests(city, normalized_service, created_at DESC);

CREATE TABLE IF NOT EXISTS marketplace_provider_access (
  provider_id UUID PRIMARY KEY REFERENCES bank_providers(id) ON DELETE CASCADE,
  access_token TEXT NOT NULL UNIQUE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketplace_matches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES marketplace_requests(id) ON DELETE CASCADE,
  provider_id UUID NOT NULL REFERENCES bank_providers(id) ON DELETE CASCADE,
  location_id UUID REFERENCES bank_locations(id) ON DELETE SET NULL,
  score INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'matched',
  estimated_price_min BIGINT,
  estimated_price_max BIGINT,
  earliest_available TEXT NOT NULL DEFAULT '',
  provider_note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(request_id, provider_id),
  CONSTRAINT marketplace_match_status CHECK (
    status IN ('matched','notified','interested','not_available','selected')
  ),
  CONSTRAINT marketplace_match_budget_order CHECK (
    estimated_price_min IS NULL OR estimated_price_max IS NULL
    OR estimated_price_min <= estimated_price_max
  )
);
CREATE INDEX IF NOT EXISTS idx_marketplace_matches_request
  ON marketplace_matches(request_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_matches_provider
  ON marketplace_matches(provider_id, status, created_at DESC);

ALTER TABLE marketplace_requests
  DROP CONSTRAINT IF EXISTS marketplace_requests_selected_match_fk;
ALTER TABLE marketplace_requests
  ADD CONSTRAINT marketplace_requests_selected_match_fk
  FOREIGN KEY (selected_match_id) REFERENCES marketplace_matches(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS marketplace_events (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  CONSTRAINT marketplace_event_status CHECK (status IN ('pending','processed','failed'))
);
CREATE INDEX IF NOT EXISTS idx_marketplace_events_pending
  ON marketplace_events(status, created_at);
