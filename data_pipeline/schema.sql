PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS insurers (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  official_url TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY,
  provider_type TEXT NOT NULL,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  medical_license_no TEXT,
  phone TEXT,
  website TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_providers_name ON providers(normalized_name);
CREATE INDEX IF NOT EXISTS idx_providers_type ON providers(provider_type);

CREATE TABLE IF NOT EXISTS locations (
  id INTEGER PRIMARY KEY,
  country TEXT NOT NULL DEFAULT 'ایران',
  province TEXT,
  city TEXT,
  district TEXT,
  address TEXT,
  normalized_address TEXT,
  latitude REAL,
  longitude REAL,
  phone TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_locations_geo ON locations(province, city, district);

CREATE TABLE IF NOT EXISTS provider_locations (
  provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  is_primary INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(provider_id, location_id)
);

CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  parent_id INTEGER REFERENCES services(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_services_name ON services(normalized_name);

CREATE TABLE IF NOT EXISTS provider_services (
  provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  confidence TEXT NOT NULL DEFAULT 'source_claimed',
  source_id INTEGER,
  PRIMARY KEY(provider_id, service_id)
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  source_type TEXT NOT NULL,
  name TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  insurer_id INTEGER REFERENCES insurers(id),
  authority_rank INTEGER NOT NULL DEFAULT 50,
  active INTEGER NOT NULL DEFAULT 1,
  last_checked_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contracts (
  id INTEGER PRIMARY KEY,
  provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
  insurer_id INTEGER NOT NULL REFERENCES insurers(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'reported',
  confidence TEXT NOT NULL DEFAULT 'unverified',
  source_id INTEGER NOT NULL REFERENCES sources(id),
  source_record_key TEXT,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_verified_at TEXT,
  UNIQUE(provider_id, location_id, insurer_id, source_id, source_record_key)
);
CREATE INDEX IF NOT EXISTS idx_contract_search ON contracts(insurer_id, status, confidence);

CREATE TABLE IF NOT EXISTS contract_services (
  contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  coverage_status TEXT NOT NULL DEFAULT 'unknown',
  evidence_text TEXT,
  PRIMARY KEY(contract_id, service_id)
);

CREATE TABLE IF NOT EXISTS raw_records (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  source_record_key TEXT,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE(source_id, payload_hash)
);

CREATE TABLE IF NOT EXISTS verification_log (
  id INTEGER PRIMARY KEY,
  contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  result TEXT NOT NULL,
  method TEXT NOT NULL,
  source_id INTEGER REFERENCES sources(id),
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_verification_contract ON verification_log(contract_id, checked_at DESC);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES sources(id),
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  fetched_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  rejected_count INTEGER NOT NULL DEFAULT 0,
  error_text TEXT
);
