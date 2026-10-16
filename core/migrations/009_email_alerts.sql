-- Phase 9: job-alert emails as a source (CLAUDE.md §5b).
CREATE TABLE alert_messages (
  message_id   TEXT PRIMARY KEY,
  board        TEXT NOT NULL,              -- linkedin | stepstone | xing
  received_at  TEXT,
  jobs_found   INTEGER NOT NULL DEFAULT 0,
  status       TEXT NOT NULL,              -- processed | retry | failed
  attempts     INTEGER NOT NULL DEFAULT 1,
  processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Senders confirmed in the user's ALERTS inbox on 2026-10-15 (LinkedIn only; StepStone/XING sent
-- nothing in the last 30 days — add their addresses in /settings once their alerts arrive).
INSERT OR IGNORE INTO settings (key, value) VALUES ('alert_senders',
  '[{"board": "linkedin", "from": "jobalerts-noreply@linkedin.com"},
    {"board": "linkedin", "from": "jobs-noreply@linkedin.com"},
    {"board": "linkedin", "from": "messages-noreply@linkedin.com"}]');
INSERT OR IGNORE INTO settings (key, value) VALUES ('alert_folder', 'INBOX');
INSERT OR IGNORE INTO settings (key, value) VALUES ('email_alerts_last_success', '');

-- Every existing filter also reads the alert emails (jobs matching no filter's keywords are not stored).
UPDATE search_filters
   SET sources = json_insert(sources, '$[#]', 'email_alerts'), updated_at = datetime('now')
 WHERE NOT EXISTS (SELECT 1 FROM json_each(search_filters.sources) WHERE value = 'email_alerts');
