# Reach the web UI from anywhere: Cloudflare reverse tunnel

JobHunter's web UI normally only answers on your own PC. With a Cloudflare tunnel you can open it
from your phone anywhere, not only on your home Wi-Fi or the PC's hotspot. Every device must
pair once with a code that only your PC can create; everyone else only sees the login page.

> **Privacy:** while the tunnel runs, your UI is reachable from the internet and its traffic
> passes through Cloudflare. This loosens the "personal data stays local" rule (R4). Close the
> cloudflared window when you don't need it.

## What you need

- **cloudflared**: install it once, e.g. `winget install --id Cloudflare.cloudflared`
  (macOS: `brew install cloudflared`). Check with `cloudflared --version`.
- No Cloudflare account for a quick tunnel (a new address each time). For an address that stays the
  same you need a free account and your own domain (see *A fixed address* below).

## 1. Two lines in `.env`

```
UI_SESSION_SECRET=<a long random string>
UI_TUNNEL_HOSTS=.trycloudflare.com
```

- `UI_SESSION_SECRET` signs the device cookies. If it is still empty, create a value with:
  ```powershell
  pwsh -c "[Convert]::ToBase64String((1..48 | % { Get-Random -Max 256 }))"
  ```
  Changing it later signs out every paired device.
- `UI_TUNNEL_HOSTS=.trycloudflare.com` allows Cloudflare's free quick tunnels. A value starting with
  a dot means "any subdomain".

## 2. Run the production server, not the dev server

The tunnel only works with the production server: the dev server (`npm run dev`) exposes internal
files that the access check doesn't cover, so tunnel hosts are refused there. Stop `npm run dev`,
then build (again after every update) and start:

```powershell
cd ui
npm run build
npm start
```

## 3. Start the tunnel

In a second terminal:

```powershell
cloudflared tunnel --url http://127.0.0.1:5173
```

If `cloudflared` isn't on your PATH: `& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:5173`.

Use `127.0.0.1`, not `localhost`: the server only listens on IPv4. cloudflared prints an address
like `https://random-words.trycloudflare.com`.

## 4. Pair your phone

1. On the PC, open `http://127.0.0.1:5173/settings` → **Pair a device** to get a 6-digit code.
   Codes can only be created on the PC itself. A code is valid for 10 minutes, works once, and is
   burned after 5 wrong tries.
2. Open the tunnel address on your phone. It sends you to `/login`; enter the code there.
3. The phone stays signed in (a secure cookie for 1 year). Anyone else who opens the address only
   sees the login page.

## Good to know

- **New address after each restart:** a quick tunnel gets a new address every time cloudflared
  starts, so your phone has to pair again.
- **A fixed address:** with a free Cloudflare account and your own domain, create a *named tunnel*
  with a fixed hostname (`cloudflared tunnel login`, `cloudflared tunnel create jobhunter`, then
  route a hostname such as `jobs.example.com` to `http://127.0.0.1:5173`; see Cloudflare's docs).
  Put that hostname in `UI_TUNNEL_HOSTS` (e.g. `UI_TUNNEL_HOSTS=jobs.example.com`). Devices then
  stay paired across restarts.
- **Telegram links:** links in Telegram messages use the `ui_base_url` setting. To open job links
  from Telegram on your phone, set it to the tunnel address in Settings. With a quick tunnel you'd
  have to change it after every restart; a fixed address avoids that.
- **Stop it:** close the cloudflared window (or Ctrl+C). The UI is then local-only again.
- **"Forbidden host" on the phone:** the server doesn't see tunnel mode. Check the spelling
  (`UI_TUNNEL_HOSTS`, with S), that each key appears only once in `.env` (the last one wins), that
  the secret has ≥ 32 characters, and restart `npm start` after every `.env` change (it reads
  `.env` only at startup and warns about unknown keys there). Quick test on the PC:
  `curl -s -o NUL -w "%{http_code}\n" -H "Host: test.trycloudflare.com" http://127.0.0.1:5173/`
  → `303` is right, `403` means `.env` isn't right yet.

## How it is protected

cloudflared connects from your own PC, so every tunnel request looks local. JobHunter therefore
recognises tunnel requests by their host name (`UI_TUNNEL_HOSTS`) and treats them like a phone on
the hotspot: a paired device cookie, or `/login`. Write requests must also come from the same site.
Technical details: `ui/CLAUDE.md` → *Reverse tunnel*.
