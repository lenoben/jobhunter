-- Shareable setup (user request 2026-10-25): choices that differ per user.
-- * work_permit_checks: the §5a checks (Blue Card salary threshold, "unrestricted work
--   authorization" wording). '1' = on (default, for people who need a permit); '0' = off, e.g. for
--   EU citizens: no such flags and no attention items.
-- * llm_model_filter / llm_model_writer: model ids when LLM_PROVIDER (.env) is not claude-code
--   (core/agent.py). model_filter / model_writer stay the Claude Code models.
INSERT OR IGNORE INTO settings (key, value) VALUES
  ('work_permit_checks', '1'),
  ('llm_model_filter', ''),
  ('llm_model_writer', '');
