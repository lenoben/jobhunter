-- User requests 2026-10-18:
-- * apply_url: where to apply, when it differs from the posting link (e.g. a company's ATS form).
--   Set when adding a job by hand or later on the job page; the apply kit uses it.
-- * favorite: the user stars jobs and can filter the list to them.
-- * notify_*: which Telegram messages are sent (telegram_enabled stays the master switch).
ALTER TABLE jobs ADD COLUMN apply_url TEXT;
ALTER TABLE jobs ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_jobs_favorite ON jobs(favorite) WHERE favorite = 1;

INSERT OR IGNORE INTO settings (key, value) VALUES
  ('notify_run_summary', '1'),   -- scheduled/manual runs: summary line, new shortlisted jobs, source problems
  ('notify_docs_ready', '1'),    -- every job whose documents were written, with links (all run types)
  ('notify_evaluated', '1'),     -- "Evaluate now": the job's fit score and decision
  ('notify_attention', '1'),     -- jobs that went to needs_attention
  ('notify_failures', '1');      -- runs that failed or couldn't start
