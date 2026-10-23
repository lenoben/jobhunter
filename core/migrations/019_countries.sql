-- Target countries (user request 2026-10-25, core §16): the project is shared with people outside
-- Germany. search_countries = JSON list of core/countries.py keys, the default for every filter;
-- search_filters.countries (non-empty) replaces it for that filter. Existing installs keep Germany.
ALTER TABLE search_filters ADD COLUMN countries TEXT NOT NULL DEFAULT '[]';
INSERT OR IGNORE INTO settings (key, value) VALUES ('search_countries', '["germany"]');
