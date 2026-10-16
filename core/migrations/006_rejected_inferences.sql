-- R9: inferred facts the user rejected are never reused (in any job's documents).
CREATE TABLE rejected_inferences (
  id          INTEGER PRIMARY KEY,
  text        TEXT NOT NULL,
  basis       TEXT,
  job_id      INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
  rejected_at TEXT NOT NULL DEFAULT (datetime('now'))
);
