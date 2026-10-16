-- Instaffo job-suggestion mails (user request 2026-10-16; sender seen in the ALERTS inbox).
-- Parsed from the mail text only: Instaffo links carry login (SSO) tokens and are never opened.
UPDATE settings
   SET value = json_insert(value, '$[#]', json('{"board": "instaffo", "from": "notifications@app.instaffo.com"}'))
 WHERE key = 'alert_senders'
   AND NOT EXISTS (SELECT 1 FROM json_each(settings.value) WHERE json_extract(value, '$.from') = 'notifications@app.instaffo.com');
