CREATE TABLE IF NOT EXISTS implant_cases (
  id UUID PRIMARY KEY,
  case_code TEXT NOT NULL UNIQUE,
  submission_key TEXT NOT NULL UNIQUE,
  patient_name TEXT NOT NULL,
  mobile TEXT NOT NULL,
  city TEXT NOT NULL,
  problem TEXT NOT NULL,
  missing_count TEXT NOT NULL DEFAULT '',
  jaws JSONB NOT NULL DEFAULT '[]'::jsonb,
  jaw_parts JSONB NOT NULL DEFAULT '{}'::jsonb,
  teeth JSONB NOT NULL DEFAULT '[]'::jsonb,
  medical JSONB NOT NULL DEFAULT '{}'::jsonb,
  disease_text TEXT NOT NULL DEFAULT '',
  medication_text TEXT NOT NULL DEFAULT '',
  suggested_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  patient_question TEXT NOT NULL DEFAULT '',
  radiograph_status JSONB NOT NULL DEFAULT '{}'::jsonb,
  photo_status JSONB NOT NULL DEFAULT '{}'::jsonb,
  consent BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'unreviewed'
    CHECK (status IN ('unreviewed', 'needs_more_info', 'ready_for_consult', 'needs_visit_cbct', 'reviewed')),
  doctor_note TEXT NOT NULL DEFAULT '',
  reviewed_at TIMESTAMPTZ,
  patient_access_token_hash TEXT,
  patient_response_draft TEXT NOT NULL DEFAULT '',
  more_info_required_draft BOOLEAN NOT NULL DEFAULT FALSE,
  more_info_message_draft TEXT NOT NULL DEFAULT '',
  patient_response_published TEXT NOT NULL DEFAULT '',
  more_info_required_published BOOLEAN NOT NULL DEFAULT FALSE,
  more_info_message_published TEXT NOT NULL DEFAULT '',
  response_published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS patient_access_token_hash TEXT;
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS patient_response_draft TEXT NOT NULL DEFAULT '';
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS more_info_required_draft BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS more_info_message_draft TEXT NOT NULL DEFAULT '';
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS patient_response_published TEXT NOT NULL DEFAULT '';
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS more_info_required_published BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS more_info_message_published TEXT NOT NULL DEFAULT '';
ALTER TABLE implant_cases ADD COLUMN IF NOT EXISTS response_published_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_implant_cases_created_at
  ON implant_cases(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_implant_cases_status_created_at
  ON implant_cases(status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_implant_cases_patient_access_token_hash
  ON implant_cases(patient_access_token_hash)
  WHERE patient_access_token_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS implant_case_files (
  id UUID PRIMARY KEY,
  case_id UUID NOT NULL REFERENCES implant_cases(id) ON DELETE CASCADE,
  slot TEXT NOT NULL
    CHECK (slot IN ('opg', 'cbct', 'front', 'upper', 'lower', 'right', 'left')),
  original_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  sha256 TEXT NOT NULL,
  storage_name TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(case_id, slot)
);

CREATE INDEX IF NOT EXISTS idx_implant_case_files_case_id
  ON implant_case_files(case_id);
