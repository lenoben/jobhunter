-- Automatic clean-up of old jobs (user request 2026-10-18), setting job_retention_days (0 = off).
-- A deleted job leaves its dedup keys here, so it is never found and processed again (R8).
CREATE TABLE deleted_jobs (
  canonical_url TEXT PRIMARY KEY,
  fingerprint   TEXT,
  deleted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_deleted_jobs_fingerprint ON deleted_jobs(fingerprint);

INSERT OR IGNORE INTO settings (key, value) VALUES ('job_retention_days', '0');
