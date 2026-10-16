-- Keep a scheduled run within Claude Pro usage limits (CLAUDE.md §10).
INSERT OR IGNORE INTO settings (key, value) VALUES ('search_limit_per_source', '10');
INSERT OR IGNORE INTO settings (key, value) VALUES ('max_evaluated_per_run', '30');
