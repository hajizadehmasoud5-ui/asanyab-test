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
