-- Job-board bookmarks (user request 2026-10-18): boards and saved searches the scheduled runs don't
-- cover. The user opens them from the UI, finds a job, and adds it with "+ Add a job".
-- Links only: nothing here is ever fetched or scraped.
CREATE TABLE job_boards (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  url          TEXT NOT NULL,
  note         TEXT,
  last_opened_at TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
