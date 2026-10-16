-- Phase 7a (CLAUDE.md §7, §10, §12).
-- R11 project ideas per job: JSON list of {title, scope, days, covers}.
ALTER TABLE jobs ADD COLUMN project_suggestions TEXT;
-- Documents the user asked for regardless of fit score: NULL | 'both' | 'cv' | 'letter'.
ALTER TABLE jobs ADD COLUMN docs_requested TEXT;

-- Two stages, two models: Haiku filters/scores, Sonnet writes. Replaces run_model.
INSERT OR IGNORE INTO settings (key, value)
  SELECT 'model_filter', COALESCE((SELECT value FROM settings WHERE key = 'run_model'), 'haiku');
INSERT OR IGNORE INTO settings (key, value) VALUES ('model_writer', 'sonnet');
INSERT OR IGNORE INTO settings (key, value) VALUES ('min_fit_for_documents', '60');
DELETE FROM settings WHERE key = 'run_model';
