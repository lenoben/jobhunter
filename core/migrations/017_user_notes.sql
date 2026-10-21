-- The user's own notes on a job's application process (user request 2026-10-22): calls, contacts,
-- next steps. Written only by the user in the job page; never read into the documents.
ALTER TABLE jobs ADD COLUMN user_notes TEXT;
ALTER TABLE jobs ADD COLUMN user_notes_at TEXT;
