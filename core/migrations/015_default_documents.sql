-- Which documents a run writes when the user didn't pick any (user request 2026-10-22):
-- 'cv' (default) = CV only, 'both' = CV + cover letter. A per-job docs_requested always wins.
INSERT OR IGNORE INTO settings (key, value) VALUES ('default_documents', 'cv');
