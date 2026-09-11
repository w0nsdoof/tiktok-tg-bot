# Deployment

The full runbook lives in the knowledge vault (canonical):

- **Shared server / infra:** `~/vault/petprojects/infra.md`
- **tiktok-tg-bot deploy, ops, config, access control:** `~/vault/petprojects/tiktok-tg-bot.md`

Quick deploy (this repo is a git checkout on the server):

```bash
ssh hetzner
cd ~/tiktok-tg-bot
git pull
docker compose up -d --build
```

`.env` (`BOT_TOKEN`, `ADMIN_USER_IDS`, …) lives on the server and is never committed.
After a `.env` change use `docker compose up -d` (a plain `restart` does NOT reload it).

The optional web control panel requires an Authentik OIDC application and a Caddy route. Follow
[docs/control-panel.md](docs/control-panel.md) before enabling the `web` service in production:

```bash
docker compose --profile control-panel up -d --build
```

Instagram may occasionally require an authenticated session or rate-limit anonymous
requests. Export a Netscape-format cookies file from an Instagram account that can
view the post, copy it to the persistent bot data volume as
`/app/src/data/instagram-cookies.txt`, and set
`INSTAGRAM_COOKIES_FILE=/app/src/data/instagram-cookies.txt` in `.env`. Keep the file
private; it grants access to that Instagram session. With Compose, the copy step can
be done using `docker compose cp ./instagram-cookies.txt bot:/app/src/data/instagram-cookies.txt`.
