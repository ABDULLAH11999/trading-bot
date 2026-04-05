Plesk / Domain Security Notes

The detections shown under paths like `httpdocs/scalper_bot/venv/lib/python3.10/site-packages/*.so`
are usually compiled Python extension modules inside the virtual environment, not uploaded webshells.
They still create deployment risk when the virtualenv lives inside the public web root.

Recommended fix on the server:

1. Move the app virtualenv out of `httpdocs`.
   Example target: `/var/www/vhosts/<domain>/scalper_bot_venv`

2. Keep only the app files that must be web-accessible inside `httpdocs`.
   Avoid exposing:
   - `venv/`
   - `.env`
   - logs
   - backups
   - raw state files

3. Recreate the environment outside web root and reinstall dependencies there.

4. Point the process manager / passenger / service unit to the external virtualenv Python binary.

5. Re-run the host malware scan after the move.

Useful environment settings for this app on a real HTTPS domain:

- `FORCE_SECURE_COOKIES=true`
- `APP_ALLOWED_HOSTS=["your-domain.com","www.your-domain.com"]`
- `CORS_ALLOWED_ORIGINS=["https://your-domain.com","https://www.your-domain.com"]`
- `ENABLE_API_DOCS=false`

Why this matters:

- A scanner may flag native `.so` files heuristically.
- Keeping `venv` under `httpdocs` makes those files visible to web-root scans and increases attack surface.
- Moving the virtualenv out of web root is the correct remediation even if the detections are false positives.
