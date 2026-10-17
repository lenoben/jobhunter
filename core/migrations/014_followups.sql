-- Follow-up reminders (user request 2026-10-19): after followup_after_days without a reply the
-- user gets a Telegram reminder with a ready follow-up text; after followup_no_response_days a
-- second one suggests closing the application. Each reminder is sent once per application.
ALTER TABLE applications ADD COLUMN followup_reminded_at TEXT;
ALTER TABLE applications ADD COLUMN followed_up_at TEXT;          -- set by the user ("I followed up")
ALTER TABLE applications ADD COLUMN no_response_reminded_at TEXT;

INSERT OR IGNORE INTO settings (key, value) VALUES
  ('followup_after_days', '14'),
  ('followup_no_response_days', '42'),
  ('notify_followups', '1');
