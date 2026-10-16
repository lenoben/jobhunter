-- R5/R9: facts in the documents that are implied by the profile but not stated in it.
-- JSON array of {document, text, where, basis}; the user approves them (needs_attention: inferred_facts).
ALTER TABLE applications ADD COLUMN inferred_facts TEXT NOT NULL DEFAULT '[]';
ALTER TABLE applications ADD COLUMN inferred_approved_at TEXT;
