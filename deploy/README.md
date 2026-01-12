# Deploying behind an existing Caddy

The stack runs next to other services on one server. Caddy already terminates TLS for them, so this project only adds a site block and puts its web container into Caddy's Docker network.

## 1. Server prerequisites

- Docker with the Compose plugin.
- A DNS A record for the domain pointing at the server. Add it before the Caddy block: Caddy asks for a certificate as soon as it sees the site.
- The name of Caddy's Docker network (`docker network ls`). The override assumes `infra_default`.

## 2. Configure

```bash
git clone https://github.com/manch1915/tg-booking-bot.git /opt/brass-blade
cd /opt/brass-blade
cp .env.example .env
chmod 600 .env
```

In `.env` set at least:

```
ENV=prod
PUBLIC_URL=https://booking.example.com
CORS_ORIGINS=["https://booking.example.com"]
JWT_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
BOT_TOKEN=<from BotFather>
BOT_USERNAME=<bot username without @>
PAYMENT_PROVIDER_TOKEN=<Stripe TEST or YooKassa TEST token from BotFather>
DEMO_MODE=true
STARS_FIXED_PRICE=1
```

`STARS_FIXED_PRICE=1` keeps Stars deposits in the public demo at one Star: Stars are real money even in test bots.

## 3. Start

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile bot up -d --build
docker compose logs -f migrate api worker bot
```

The `migrate` container applies migrations and loads the demo shop on the first start.

## 4. Add the Caddy block

Append `deploy/Caddyfile.snippet` with the real domain to the shared Caddyfile, then validate and reload without restarting Caddy:

```bash
cp Caddyfile Caddyfile.bak-$(date +%Y%m%d-%H%M%S)
cat deploy/Caddyfile.snippet >> Caddyfile     # append in place, do not use sed -i
docker exec <caddy> caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec <caddy> caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

`sed -i` and editors that save through a temporary file replace the inode of a bind-mounted Caddyfile, and the container keeps reading the old one. Check that the container sees the new block with `docker exec <caddy> grep booking /etc/caddy/Caddyfile`.

## 5. Telegram

- BotFather → Bot Settings → Menu Button → `https://booking.example.com/app/`.
- BotFather → Bot Settings → Configure Mini App → the same URL, so `t.me/<bot>/app` works.
- The bot sets its own commands and menu button on start once `PUBLIC_URL` is https.

## Checks

```bash
curl -fsS https://booking.example.com/api/health
curl -fsS https://booking.example.com/ | grep -o "<title>[^<]*"
```

Then open the bot, book a visit and pay the deposit with a test card (Stripe: 4242 4242 4242 4242, any future date, any CVC).
