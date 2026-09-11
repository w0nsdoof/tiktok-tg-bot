# Authentik control panel

The control panel is a second service built from the bot image. It uses the existing
`tiktokbot` PostgreSQL database for access records and runtime settings and uses
Authentik OIDC for browser identity.

## Access model

- Authentik group `tiktok-bot-operators`: open the panel and approve, deny, or disable users.
- Authentik group `tiktok-bot-admins`: operator access plus bot-role and runtime-setting changes.
- Bot roles in PostgreSQL remain separate because they govern Telegram actions, such as global
  statistics and receiving access-request notifications.
- `/link` creates a hashed, single-use, ten-minute token that binds a Telegram numeric ID to the
  authenticated Authentik `sub`. Usernames are display data and are never used as identity keys.

The bot refreshes its synchronous authorization cache from PostgreSQL every 15 seconds. This
keeps Telegram filters fast while allowing control-panel changes to take effect without restart.
Browser role claims remain in a signed, HTTPS-only session for at most 15 minutes. The next OIDC
round trip then refreshes Authentik group membership.

## Application configuration

Add these values to the deployment `.env`; secrets must not be committed:

```dotenv
DATABASE_DSN=postgresql://tiktokbot:<password>@postgres:5432/tiktokbot
CONTROL_PANEL_URL=https://bot.w0nsdoof.com
WEB_SESSION_SECRET=<long-random-value>
WEB_SESSION_MAX_AGE=900
AUTHENTIK_ISSUER=https://auth.w0nsdoof.com/application/o/tiktok-bot
AUTHENTIK_CLIENT_ID=tiktok-bot
AUTHENTIK_CLIENT_SECRET=<same-secret-as-provider>
AUTHENTIK_OPERATOR_GROUP=tiktok-bot-operators
AUTHENTIK_ADMIN_GROUP=tiktok-bot-admins
```

`DATABASE_DSN` can be omitted when `ANALYTICS_DSN` already points to the same `tiktokbot`
database. The explicit variable is clearer now that PostgreSQL is an authorization dependency,
not only optional analytics storage.

Generate the session secret with a password generator or `openssl rand -hex 32` and store it
only in the server-side `.env`.

## Authentik configuration

Apply these changes in the `reverse-proxy` repository's existing Authentik blueprints:

1. Add `tiktok-bot-users`, `tiktok-bot-operators`, and `tiktok-bot-admins` groups.
2. Add a confidential OAuth2/OIDC provider:
   - client ID: `tiktok-bot`
   - secret from an environment reference such as `TIKTOK_BOT_OIDC_SECRET`
   - grant types: `authorization_code`, `refresh_token`
   - strict redirect URI: `https://bot.w0nsdoof.com/auth/callback`
   - issuer mode: per-provider
   - signing key: `authentik Self-signed Certificate` (or another persistent certificate-key pair)
   - mappings: managed `openid`, `profile`, and `email`
3. Add an application with slug `tiktok-bot`, then bind all three application groups and
   `infrastructure-admins` to it. Operators and admins should normally also belong to
   `tiktok-bot-users`.
4. Put the same generated OIDC secret in the Authentik stack and bot stack environments without
   printing either value during verification.

The issuer for the per-provider configuration is:

```text
https://auth.w0nsdoof.com/application/o/tiktok-bot
```

Its discovery document must be reachable at:

```text
https://auth.w0nsdoof.com/application/o/tiktok-bot/.well-known/openid-configuration
```

The provider must publish at least one asymmetric key:

```bash
curl -fsS https://auth.w0nsdoof.com/application/o/tiktok-bot/jwks/ | jq '.keys | length'
```

Without a signing key, Authentik signs with the client secret and returns `{}` from the JWKS
endpoint. Authlib then fails the callback while trying to validate the ID token.

## Caddy and DNS

Create the chosen DNS record using the existing reverse-proxy tooling. The control-panel service
joins the external `web` network under the stable container name `tiktok-bot-web`, so the Caddy
upstream is:

```caddyfile
bot.w0nsdoof.com {
    log {
        output file /var/log/caddy/tiktok-bot.log {
            roll_size 10MiB
            roll_keep 5
        }
        format json
    }
    # The path contains a short-lived account-link token.
    log_skip /link/*
    reverse_proxy tiktok-bot-web:8000
}
```

Do not add Authentik forward-auth to this route. The application uses native OIDC so it can read
the stable subject and group claims itself. Caddy must remain the only public path to port 8000;
the Compose service does not publish a host port.

## Database migration behavior

On startup, the bot and web service create the access-control tables if missing. The bot imports
users from the existing `data/allowed_users.json` and merges `ADMIN_USER_IDS` and
`ALLOWED_USER_IDS`. Existing database decisions are not downgraded; seeded admins remain active.

The new tables are:

- `bot_users`
- `access_link_tokens`
- `runtime_settings`
- `access_audit_log`

Keep the old bot-data volume through the first successful deployment so legacy users can be
imported. After validating row counts, PostgreSQL is the source of truth.

## Verification

```bash
docker compose --profile control-panel config --quiet
docker compose --profile control-panel up -d --build
docker compose ps
curl -fsS https://bot.w0nsdoof.com/healthz
```

Browser smoke test:

1. An unauthenticated visit to `/` redirects to Authentik.
2. A user outside the operator/admin groups receives 403 on control pages.
3. An operator can approve a pending user but cannot change roles or settings.
4. An admin can change roles, limits, and group access mode.
5. Send `/link` to the bot, authenticate, and confirm the linked Authentik username appears on
   the Users page.
6. Change group access mode and confirm the bot applies it within 15 seconds.

Database checks:

```sql
SELECT telegram_user_id, status, role, authentik_username FROM bot_users ORDER BY added_at;
SELECT key, value, updated_by FROM runtime_settings ORDER BY key;
SELECT actor, action, telegram_user_id, ts FROM access_audit_log ORDER BY ts DESC LIMIT 20;
```

## Troubleshooting

- Callback fails with `KeyError: 'keys'`: check the provider's JWKS endpoint. Assign a signing
  certificate, reapply the blueprint, verify at least one key is present, and restart the web
  service to clear Authlib's cached empty response.
- Server-side OIDC requests receive a Cloudflare challenge: containers on the external `web`
  network must resolve `auth.w0nsdoof.com` to Caddy's `auth.w0nsdoof.com` network alias. Verify
  the web container's resolved address matches the `reverse-proxy` container's `web` address.
- Bot and web may start concurrently. Access-table DDL is serialized with a PostgreSQL advisory
  transaction lock; a `UniqueViolationError` during schema creation means the deployed revision
  predates that fix.
- Keep `httpx` and `httpcore` below INFO logging. Telegram API URLs contain the bot token in the
  path; rotate the token immediately if such a URL appears in logs.
