-- Recruiting agencies and job reminders (user request 2026-10-28, core §16c).
-- recruiters: the user's own list of agencies / staffing companies. names = JSON list of the
-- spellings to match (name first), compared after dedup.normalise (case, legal forms, punctuation).
CREATE TABLE recruiters (
  id         INTEGER PRIMARY KEY,
  names      TEXT NOT NULL,
  note       TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- jobs.via_recruiter: NULL = no sign of a recruiter; 'list' = company is on the user's list
-- (recruiter_id); 'detected' = the scoring model read it from the posting (recruiter_reason);
-- 'cleared' = the user said "not a recruiter" (never tagged again). A 'list' / 'detected' job
-- gets documents only when the user requests them.
ALTER TABLE jobs ADD COLUMN via_recruiter TEXT;
ALTER TABLE jobs ADD COLUMN recruiter_reason TEXT;
ALTER TABLE jobs ADD COLUMN recruiter_id INTEGER REFERENCES recruiters(id) ON DELETE SET NULL;
ALTER TABLE jobs ADD COLUMN recruiter_seen INTEGER NOT NULL DEFAULT 0;  -- opened since tagged (nav count)

-- Reminders: remind_at is local time 'YYYY-MM-DD HH:MM' (the PC's clock, like the UI input);
-- reminded_at is set once Telegram accepted the message.
ALTER TABLE jobs ADD COLUMN remind_at TEXT;
ALTER TABLE jobs ADD COLUMN remind_note TEXT;
ALTER TABLE jobs ADD COLUMN reminded_at TEXT;
CREATE INDEX idx_jobs_remind_at ON jobs(remind_at) WHERE remind_at IS NOT NULL AND reminded_at IS NULL;

INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_reminders', '1');
