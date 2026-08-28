CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS bank_insurers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  official_url TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_providers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_type TEXT NOT NULL,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  medical_license_no TEXT,
  phone TEXT,
  website TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bank_providers_name ON bank_providers(normalized_name);
CREATE INDEX IF NOT EXISTS idx_bank_providers_type ON bank_providers(provider_type);

CREATE TABLE IF NOT EXISTS bank_locations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  country TEXT NOT NULL DEFAULT 'ایران',
  province TEXT,
  city TEXT,
  district TEXT,
  address TEXT,
  normalized_address TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  phone TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bank_locations_geo ON bank_locations(province, city, district);

CREATE TABLE IF NOT EXISTS geo_provinces (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  normalized_name TEXT NOT NULL UNIQUE,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  source_url TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS geo_cities (
  id BIGSERIAL PRIMARY KEY,
  source_id INTEGER,
  province_id INTEGER NOT NULL REFERENCES geo_provinces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  source_url TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(province_id, normalized_name)
);
CREATE INDEX IF NOT EXISTS idx_geo_cities_province ON geo_cities(province_id, normalized_name);
CREATE INDEX IF NOT EXISTS idx_geo_cities_name ON geo_cities(normalized_name);

CREATE TABLE IF NOT EXISTS bank_provider_locations (
  provider_id UUID NOT NULL REFERENCES bank_providers(id) ON DELETE CASCADE,
  location_id UUID NOT NULL REFERENCES bank_locations(id) ON DELETE CASCADE,
  is_primary BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY(provider_id, location_id)
);

CREATE TABLE IF NOT EXISTS bank_services (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  parent_id UUID REFERENCES bank_services(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bank_services_name ON bank_services(normalized_name);

CREATE TABLE IF NOT EXISTS bank_service_aliases (
  alias TEXT PRIMARY KEY,
  normalized_alias TEXT NOT NULL,
  service_id UUID NOT NULL REFERENCES bank_services(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bank_service_aliases_norm ON bank_service_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS bank_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type TEXT NOT NULL,
  name TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  insurer_id UUID REFERENCES bank_insurers(id) ON DELETE SET NULL,
  authority_rank INTEGER NOT NULL DEFAULT 50,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  last_checked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bank_source_registry (
  slug TEXT PRIMARY KEY,
  insurer_slug TEXT,
  insurer_name TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL DEFAULT 'secondary',
  adapter TEXT NOT NULL DEFAULT 'pending',
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  last_discovered_at TIMESTAMPTZ,
  last_success_at TIMESTAMPTZ,
  last_error TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS bank_provider_services (
  provider_id UUID NOT NULL REFERENCES bank_providers(id) ON DELETE CASCADE,
  service_id UUID NOT NULL REFERENCES bank_services(id) ON DELETE CASCADE,
  confidence TEXT NOT NULL DEFAULT 'source_claimed',
  source_id UUID REFERENCES bank_sources(id) ON DELETE SET NULL,
  PRIMARY KEY(provider_id, service_id)
);

CREATE TABLE IF NOT EXISTS bank_contracts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id UUID NOT NULL REFERENCES bank_providers(id) ON DELETE CASCADE,
  location_id UUID NOT NULL REFERENCES bank_locations(id) ON DELETE CASCADE,
  insurer_id UUID NOT NULL REFERENCES bank_insurers(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'reported',
  confidence TEXT NOT NULL DEFAULT 'unverified',
  source_id UUID NOT NULL REFERENCES bank_sources(id) ON DELETE RESTRICT,
  source_record_key TEXT NOT NULL DEFAULT '',
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_verified_at TIMESTAMPTZ,
  UNIQUE(provider_id, location_id, insurer_id, source_id, source_record_key)
);
CREATE INDEX IF NOT EXISTS idx_bank_contract_search ON bank_contracts(insurer_id, status, confidence);

CREATE TABLE IF NOT EXISTS bank_contract_services (
  contract_id UUID NOT NULL REFERENCES bank_contracts(id) ON DELETE CASCADE,
  service_id UUID NOT NULL REFERENCES bank_services(id) ON DELETE CASCADE,
  coverage_status TEXT NOT NULL DEFAULT 'unknown',
  evidence_text TEXT,
  PRIMARY KEY(contract_id, service_id)
);

CREATE TABLE IF NOT EXISTS bank_raw_records (
  id BIGSERIAL PRIMARY KEY,
  source_id UUID NOT NULL REFERENCES bank_sources(id) ON DELETE CASCADE,
  source_record_key TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload JSONB NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE(source_id, payload_hash)
);

CREATE TABLE IF NOT EXISTS bank_verification_log (
  id BIGSERIAL PRIMARY KEY,
  contract_id UUID NOT NULL REFERENCES bank_contracts(id) ON DELETE CASCADE,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  result TEXT NOT NULL,
  method TEXT NOT NULL,
  source_id UUID REFERENCES bank_sources(id) ON DELETE SET NULL,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_bank_verification_contract ON bank_verification_log(contract_id, checked_at DESC);

CREATE TABLE IF NOT EXISTS bank_ingestion_runs (
  id BIGSERIAL PRIMARY KEY,
  source_id UUID REFERENCES bank_sources(id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'running',
  fetched_count INTEGER NOT NULL DEFAULT 0,
  accepted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  rejected_count INTEGER NOT NULL DEFAULT 0,
  error_text TEXT
);

-- DrLinq marketplace MVP. These tables are additive and intentionally keep the
-- existing provider bank as the source of truth for provider identity, service,
-- geography, insurance and source evidence.
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
