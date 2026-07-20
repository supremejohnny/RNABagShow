# Pong connectivity probe

Zero-dependency Python HTTP service that responds `pong\n` to
`GET /probe/ping` with `Cache-Control: no-store`. Designed for the tang3
tailnet host as a reachability target for the public-preview bastion Nginx.

## Start

```bash
RNABAG_PONG_BIND_IP=100.113.222.1 RNABAG_PONG_PORT=18080 \
  docker compose -f deploy/compose.pong-probe.yml up -d --build --wait
```

The bind IP is the verified tang3 Tailscale address. Adjust when it changes.

## Status

```bash
docker compose -f deploy/compose.pong-probe.yml ps
docker compose -f deploy/compose.pong-probe.yml logs
```

## Stop

```bash
docker compose -f deploy/compose.pong-probe.yml down
```

## Three-hop verification

From the bastion host:

```bash
# 1 — Nginx responds to the proxied probe path
curl -s -o /dev/null -w '%{http_code}' http://localhost/probe/ping

# 2 — Nginx blocks API paths
curl -s -o /dev/null -w '%{http_code}' http://localhost/api/v1/health/live

# 3 — Direct pong-probe check (from tang3 or through tailnet)
curl -s http://100.113.222.1:18080/probe/ping
```

Expected: `200`, `503`, `pong`.
