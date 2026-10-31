-- Feedback tickets (user request 2026-11-07, core §16d): issues, improvements and suggestions the
-- user writes for the project's developer. JobHunter never sends them (R1): the user sends the mail,
-- then sets the status by hand. Only 'draft' tickets can be edited or deleted.
CREATE TABLE tickets (
  id              INTEGER PRIMARY KEY,
  ref             TEXT NOT NULL UNIQUE,            -- JH-7F3K2: random, so tickets of different users never clash
  kind            TEXT NOT NULL,                   -- issue | improvement | suggestion
  title           TEXT NOT NULL,
  body            TEXT NOT NULL DEFAULT '',
  reply_to        TEXT,                            -- optional address for an answer
  include_details INTEGER NOT NULL DEFAULT 0,      -- add OS, LLM provider name and commit to the mail
  status          TEXT NOT NULL DEFAULT 'draft',   -- draft | sent | resolved
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  sent_at         TEXT
);
