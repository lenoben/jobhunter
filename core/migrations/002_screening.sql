-- §5a screening: salary normalised to gross EUR/year and its Blue Card flag.
ALTER TABLE jobs ADD COLUMN salary_annual_eur REAL;
ALTER TABLE jobs ADD COLUMN salary_flag TEXT;   -- ok | below_blue_card_threshold | salary_unknown

-- EU Blue Card threshold (shortage occupations incl. IT). Editable; update each January.
INSERT OR IGNORE INTO settings (key, value) VALUES
  ('blue_card_salary_min', '45934.20'),
  ('blue_card_salary_year', '2026');
