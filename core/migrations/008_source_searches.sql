-- How often each source was searched in a run ({"ba_jobsuche": 6, "jobspy:linkedin": 6, …}), so
-- errors can be reported as "no results for 2 of 6 filters" instead of "failed".
ALTER TABLE runs ADD COLUMN source_searches TEXT NOT NULL DEFAULT '{}';
