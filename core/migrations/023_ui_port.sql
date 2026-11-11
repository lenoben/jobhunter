-- The UI moved from Vite's well-known 5173 to its own port 5790 (2026-11-16).
-- Only the untouched default changes; a custom ui_base_url (tunnel, LAN address) stays.
UPDATE settings SET value = 'http://localhost:5790' WHERE key = 'ui_base_url' AND value = 'http://localhost:5173';
