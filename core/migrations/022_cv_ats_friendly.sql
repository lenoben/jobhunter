-- ATS-friendly English CVs (user request 2026-11-10, core §16e): '1' lays an English CV out for
-- résumé parsers, '0' keeps the tabular layout. Off where Germany is a target (the tabular
-- Lebenslauf style is the convention there), on otherwise; cli.py setup sets it with the
-- countries. The German Lebenslauf is always tabular.
INSERT OR IGNORE INTO settings (key, value)
SELECT 'cv_ats_friendly', CASE WHEN COALESCE((SELECT value FROM settings WHERE key = 'search_countries'),
                                             '["germany"]') LIKE '%"germany"%' THEN '0' ELSE '1' END;
