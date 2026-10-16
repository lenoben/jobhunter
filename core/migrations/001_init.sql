PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE search_filters (
  id               INTEGER PRIMARY KEY,
  name             TEXT NOT NULL,
  active           INTEGER NOT NULL DEFAULT 1,
  keywords         TEXT NOT NULL,          -- JSON array, e.g. ["Backend Developer","Python"]
  exclude_keywords TEXT NOT NULL DEFAULT '[]',
  location         TEXT,                   -- e.g. "Mannheim"; NULL = Germany-wide
  radius_km        INTEGER DEFAULT 50,
  work_modes       TEXT NOT NULL DEFAULT '["remote","hybrid","onsite"]',
  employment_types TEXT NOT NULL DEFAULT '["full_time"]',  -- full_time | part_time | minijob | working_student | internship
  exclude_freelance INTEGER NOT NULL DEFAULT 1,
  languages        TEXT NOT NULL DEFAULT '["de","en"]',
  sources          TEXT NOT NULL DEFAULT '["ba_jobsuche","arbeitnow","jobspy"]',
  max_age_days     INTEGER NOT NULL DEFAULT 7,
  min_fit_score    INTEGER NOT NULL DEFAULT 60,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE jobs (
  id               INTEGER PRIMARY KEY,
  source           TEXT NOT NULL,          -- adapter key
  source_job_id    TEXT,                   -- board's own id if available
  url              TEXT NOT NULL,          -- original URL
  canonical_url    TEXT NOT NULL UNIQUE,   -- dedup key 1
  fingerprint      TEXT NOT NULL,          -- dedup key 2 (company|title|city)
  title            TEXT NOT NULL,
  company          TEXT,
  location         TEXT,
  work_mode        TEXT,                   -- remote | hybrid | onsite | unknown (Claude classifies)
  employment_type  TEXT,
  language         TEXT,                   -- de | en (posting language)
  salary_text      TEXT,
  posted_at        TEXT,
  description      TEXT,
  apply_method     TEXT,                   -- portal | email | external_ats | unknown
  apply_email      TEXT,
  fit_score        INTEGER,                -- 0–100, set by Claude
  fit_notes        TEXT,                   -- why it fits / gaps (Markdown)
  status           TEXT NOT NULL DEFAULT 'new',
  attention_reason TEXT,                   -- set when status = needs_attention
  filter_id        INTEGER REFERENCES search_filters(id),
  first_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX idx_jobs_status ON jobs(status);

CREATE TABLE applications (
  id               INTEGER PRIMARY KEY,
  job_id           INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
  cv_path          TEXT,
  letter_path      TEXT,
  doc_language     TEXT,                   -- de | en
  summary          TEXT,                   -- what was emphasised and why
  interview_prep   TEXT,                   -- expected questions, topics to revise (Markdown)
  method           TEXT,                   -- how it was / will be submitted
  email_draft_saved INTEGER NOT NULL DEFAULT 0,
  applied_at       TEXT,                   -- set by the USER via UI
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE status_history (
  id         INTEGER PRIMARY KEY,
  job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  from_status TEXT,
  to_status  TEXT NOT NULL,
  note       TEXT,
  changed_by TEXT NOT NULL,               -- 'claude' | 'user'
  changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE runs (
  id           INTEGER PRIMARY KEY,
  started_at   TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at  TEXT,
  trigger      TEXT NOT NULL,              -- scheduled | manual
  found        INTEGER DEFAULT 0,
  new_jobs     INTEGER DEFAULT 0,
  tailored     INTEGER DEFAULT 0,
  needs_you    INTEGER DEFAULT 0,
  errors       TEXT DEFAULT '[]',          -- JSON array of {source, message}
  status       TEXT NOT NULL DEFAULT 'running'  -- running | ok | partial | failed
);

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT INTO settings (key, value) VALUES
  ('max_tailored_per_run', '5'),
  ('min_hours_between_runs', '4'),
  ('telegram_enabled', '1'),
  ('ui_base_url', 'http://localhost:5173');
