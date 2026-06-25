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
