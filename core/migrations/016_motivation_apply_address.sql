-- User requests 2026-10-22:
-- * Motivationsschreiben: a third document, written only when the user asks for it
--   (docs_requested = 'motivation'). Its path is kept next to the CV and letter.
-- * Where to apply: a posting may name a link, an email address and a postal address at once;
--   all of them are kept. apply_address holds the postal address (lines separated by \n).
ALTER TABLE applications ADD COLUMN motivation_path TEXT;
ALTER TABLE jobs ADD COLUMN apply_address TEXT;
